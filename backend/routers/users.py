"""Candidates & users management (admin)."""
import re
import json
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from core import (
    db, logger, require_admin, require_super, get_current_user, public_user,
    EMERGENT_LLM_KEY, LlmChat, UserMessage,
)

router = APIRouter()


class RoleInput(BaseModel):
    role: str


class SuperInput(BaseModel):
    is_super: bool


async def _rating_map() -> dict:
    agg = await db.applications.aggregate([
        {"$match": {"rating": {"$ne": None}}},
        {"$group": {"_id": "$candidate_id", "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}},
    ]).to_list(5000)
    return {r["_id"]: {"avg": round(r["avg"], 1), "n": r["n"]} for r in agg}


@router.get("/candidates")
async def list_candidates(admin: dict = Depends(require_admin)):
    users = await db.users.find({"role": "candidate"}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    counts = await db.applications.aggregate([{"$group": {"_id": "$candidate_id", "n": {"$sum": 1}}}]).to_list(5000)
    cmap = {c["_id"]: c["n"] for c in counts}
    rmap = await _rating_map()
    for u in users:
        u["application_count"] = cmap.get(u["user_id"], 0)
        r = rmap.get(u["user_id"])
        u["rating"] = r["avg"] if r else None
        u["rating_count"] = r["n"] if r else 0
        u.pop("cv_text", None)
    if not admin.get("is_super"):
        for u in users:
            u.pop("is_super", None)
    return users


def _cv_snippet(cv_text: str, q: str, radius: int = 90) -> Optional[str]:
    if not cv_text or not q:
        return None
    low, ql = cv_text.lower(), q.lower().strip()
    idx = low.find(ql)
    if idx < 0:
        first = ql.split()[0] if ql.split() else ""
        idx = low.find(first) if first else -1
        if idx < 0:
            return None
        ql = first
    start = max(0, idx - radius)
    end = min(len(cv_text), idx + len(ql) + radius)
    snip = cv_text[start:end].strip()
    return ("… " if start > 0 else "") + snip + (" …" if end < len(cv_text) else "")


@router.get("/users")
async def list_users(q: Optional[str] = Query(None), min_rating: Optional[int] = Query(None), admin: dict = Depends(require_admin)):
    proj = {"_id": 0, "password_hash": 0}
    users = None
    if q:
        # Voie rapide : recherche full-text indexée (mots entiers)
        try:
            users = await db.users.find(
                {"$text": {"$search": q}},
                {**proj, "score": {"$meta": "textScore"}},
            ).sort([("score", {"$meta": "textScore"})]).to_list(1000)
        except Exception as e:
            logger.warning(f"text search failed, fallback regex: {e}")
            users = None
        # Repli / complément : regex sous-chaîne (recherche partielle)
        if not users:
            rx = {"$regex": re.escape(q), "$options": "i"}
            users = await db.users.find({"$or": [
                {"name": rx}, {"email": rx}, {"current_position": rx}, {"nationality": rx},
                {"headline": rx}, {"bio": rx}, {"domains": rx}, {"tools": rx},
                {"city": rx}, {"country": rx}, {"cv_text": rx}, {"cv_filename": rx},
            ]}, proj).sort("created_at", -1).to_list(1000)
    else:
        users = await db.users.find({}, proj).sort("created_at", -1).to_list(1000)

    counts = await db.applications.aggregate([{"$group": {"_id": "$candidate_id", "n": {"$sum": 1}}}]).to_list(5000)
    cmap = {c["_id"]: c["n"] for c in counts}
    rmap = await _rating_map()
    for u in users:
        u["application_count"] = cmap.get(u["user_id"], 0)
        r = rmap.get(u["user_id"])
        u["rating"] = r["avg"] if r else None
        u["rating_count"] = r["n"] if r else 0
        if q:
            u["cv_snippet"] = _cv_snippet(u.get("cv_text", ""), q)
        u.pop("cv_text", None)
        u.pop("score", None)
    if min_rating:
        users = [u for u in users if (u.get("rating") or 0) >= min_rating]
    if not admin.get("is_super"):
        for u in users:
            u.pop("is_super", None)
    return users


@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    apps = await db.applications.find({"candidate_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    interviews = await db.interviews.find({"candidate_id": user_id}, {"_id": 0}).sort([("date", 1), ("time", 1)]).to_list(500)
    contracts = await db.contracts.find({"candidate_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    pub = public_user(u)
    if not admin.get("is_super"):
        pub.pop("is_super", None)
    return {"user": pub, "applications": apps, "interviews": interviews, "contracts": contracts}


@router.get("/users/{user_id}/cv-text")
async def get_user_cv_text(user_id: str, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "cv_text": 1, "cv_filename": 1, "cv_file_id": 1})
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return {"cv_text": u.get("cv_text", ""), "cv_filename": u.get("cv_filename"), "cv_file_id": u.get("cv_file_id")}


class AiSearchInput(BaseModel):
    query: str
    history: Optional[list] = None


@router.post("/users/ai-search")
async def ai_search_users(body: AiSearchInput, admin: dict = Depends(require_admin)):
    """Agent IA : interprète une requête en langage naturel et retourne les candidats pertinents (profil + CV)."""
    query = (body.query or "").strip()
    if not query:
        return {"results": []}
    cands = await db.users.find({"role": {"$ne": "admin"}}, {"_id": 0, "password_hash": 0}).to_list(200)
    if not EMERGENT_LLM_KEY or not cands:
        return {"results": []}
    lines = []
    for c in cands[:60]:
        tags = (c.get("domains") or []) + (c.get("ai_domains") or [])
        cv = (c.get("cv_text") or "")[:1500]
        lines.append(
            f"- id={c['user_id']} | nom={c.get('name','')} | poste={c.get('current_position','')} "
            f"| domaines={', '.join(tags)} | outils={', '.join(c.get('tools') or [])} "
            f"| experience={c.get('years_experience','?')} ans | CV: {cv}"
        )
    hist = ""
    for h in (body.history or [])[-8:]:
        role = "Recruteur" if h.get("role") == "user" else "Assistant"
        hist += f"{role}: {h.get('content','')}\n"
    prompt = (
        (f"HISTORIQUE DE LA CONVERSATION:\n{hist}\n" if hist else "") +
        f"NOUVELLE DEMANDE DU RECRUTEUR: {query}\n\nCANDIDATS (profil + extrait reel du CV):\n" + "\n".join(lines) +
        "\n\nAnalyse le CONTENU DES CV et les profils pour repondre precisement."
    )
    system = (
        "Tu es un agent conversationnel de recherche RH. On te donne l'historique de la conversation, une demande, "
        "et des candidats (profil + texte extrait de leur CV). Tu DOIS baser tes reponses sur le CONTENU REEL des CV et des profils. "
        "Reponds UNIQUEMENT par un objet JSON valide, sans texte autour: "
        "{\"answer\":\"<message FR conversationnel, 1-3 phrases, repond au recruteur et peut demander une precision>\","
        "\"results\":[{\"candidate_id\":\"<id>\",\"score\":<0-100>,\"reason\":\"<preuve concrete tiree du CV/profil, FR>\"}]}. "
        "results = uniquement les candidats pertinents (score>=50), tries par score decroissant. Si aucun, results=[]."
    )
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=f"aisearch-{uuid.uuid4().hex[:8]}",
            system_message=system,
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        raw = (resp if isinstance(resp, str) else getattr(resp, "text", str(resp))) or ""
        raw = raw.strip()
        try:
            obj = json.loads(raw)
        except Exception:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            obj = json.loads(m.group(0)) if m else {}
        answer = obj.get("answer", "") if isinstance(obj, dict) else ""
        arr = obj.get("results", []) if isinstance(obj, dict) else (obj if isinstance(obj, list) else [])
    except Exception as e:
        logger.warning(f"ai_search failed: {e}")
        raise HTTPException(status_code=503, detail="Recherche IA momentanement indisponible.")
    by_id = {c["user_id"]: c for c in cands}
    results = []
    for x in arr if isinstance(arr, list) else []:
        c = by_id.get(str(x.get("candidate_id", "")))
        if not c:
            continue
        c.pop("cv_text", None)
        if not admin.get("is_super"):
            c.pop("is_super", None)
        results.append({**c, "ai_score": int(x.get("score", 0)), "ai_reason": x.get("reason", "")})
    return {"answer": answer, "results": results}


@router.get("/admin/nationalities")
async def nationalities(admin: dict = Depends(require_admin)):
    agg = await db.users.aggregate([
        {"$match": {"role": "candidate"}},
        {"$group": {"_id": {"$ifNull": ["$nationality", ""]}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]).to_list(300)
    return [{"nationality": (a["_id"] or "Non renseignée"), "count": a["count"]} for a in agg]


@router.put("/users/{user_id}/role")
async def set_user_role(user_id: str, body: RoleInput, admin: dict = Depends(require_admin)):
    if body.role not in ("admin", "candidate"):
        raise HTTPException(status_code=400, detail="Rôle invalide")
    if user_id == admin["user_id"] and body.role != "admin":
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas retirer votre propre rôle admin")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "is_super": 1})
    if target and target.get("is_super") and not admin.get("is_super"):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    res = await db.users.update_one({"user_id": user_id}, {"$set": {"role": body.role}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})


@router.put("/users/{user_id}/super")
async def set_super(user_id: str, body: SuperInput, admin: dict = Depends(require_super)):
    if user_id == admin["user_id"] and not body.is_super:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas retirer votre propre statut")
    upd = {"is_super": True, "role": "admin"} if body.is_super else {"is_super": False}
    res = await db.users.update_one({"user_id": user_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return {"ok": True, "is_super": body.is_super}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "is_super": 1})
    if target and target.get("is_super"):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    await db.users.delete_one({"user_id": user_id})
    await db.applications.delete_many({"candidate_id": user_id})
    await db.messages.delete_many({"conversation_id": user_id})
    return {"ok": True}


@router.delete("/candidates/{user_id}")
async def delete_candidate(user_id: str, admin: dict = Depends(require_admin)):
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0, "is_super": 1})
    if target and target.get("is_super"):
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    await db.users.delete_one({"user_id": user_id, "role": "candidate"})
    await db.applications.delete_many({"candidate_id": user_id})
    await db.messages.delete_many({"conversation_id": user_id})
    return {"ok": True}

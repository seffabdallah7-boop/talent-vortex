"""Jobs routes + AI suggestions."""
import re
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Header, BackgroundTasks
from pydantic import BaseModel

from core import (
    db, logger, EMERGENT_LLM_KEY, gemini_generate, GEMINI_API_KEY, LlmChat, UserMessage,
    require_admin, resolve_token, notify_user, notify_admins, send_email,
)

router = APIRouter()


class JobInput(BaseModel):
    title: str
    company: str
    location: str
    type: str = "Temps plein"
    category: str = "General"
    description: str
    requirements: Optional[str] = ""
    salary: Optional[str] = ""


class JobDraftInput(BaseModel):
    brief: str


class JobActiveInput(BaseModel):
    is_active: bool


def _job_match_score(job: dict, tags: list) -> int:
    hay = " ".join(filter(None, [job.get("category", ""), job.get("title", ""), job.get("description", ""), job.get("requirements", "")])).lower()
    cat = (job.get("category", "") or "").lower()
    score = 0
    for t in tags:
        tl = (t or "").lower().strip()
        if not tl:
            continue
        if tl and (tl in cat or (cat and cat in tl)):
            score += 3
        elif tl in hay:
            score += 1
    return score


@router.get("/jobs")
async def list_jobs(q: Optional[str] = Query(None), authorization: Optional[str] = Header(None)):
    query = {"is_active": True}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"title": rx}, {"company": rx}, {"location": rx}, {"category": rx}, {"description": rx}]
    jobs = await db.jobs.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    if token:
        u = await resolve_token(token)
        if u and u.get("role") == "candidate":
            tags = (u.get("ai_domains") or []) + (u.get("domains") or [])
            if tags:
                for j in jobs:
                    s = _job_match_score(j, tags)
                    j["match_score"] = s
                    j["match_percent"] = min(96, 55 + s * 12) if s > 0 else None
                jobs.sort(key=lambda j: (j.get("match_score", 0), j.get("created_at", "")), reverse=True)
    return jobs


@router.get("/jobs/all")
async def list_all_jobs(admin: dict = Depends(require_admin)):
    jobs = await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    counts = await db.applications.aggregate([
        {"$group": {"_id": "$job_id", "total": {"$sum": 1}, "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}}}},
    ]).to_list(5000)
    cmap = {c["_id"]: c for c in counts}
    for j in jobs:
        c = cmap.get(j["id"], {})
        j["applicants"] = c.get("total", 0)
        j["pending"] = c.get("pending", 0)
    return jobs


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return job


@router.post("/jobs")
async def create_job(body: JobInput, background: BackgroundTasks, admin: dict = Depends(require_admin)):
    doc = body.model_dump()
    doc.update({
        "id": str(uuid.uuid4()),
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.jobs.insert_one(doc)
    doc.pop("_id", None)
    background.add_task(notify_matching_candidates, doc)
    background.add_task(notify_admin_suggestions, doc)
    return doc


async def notify_matching_candidates(job: dict):
    candidates = await db.users.find(
        {"role": "candidate"},
        {"_id": 0, "user_id": 1, "domains": 1, "ai_domains": 1},
    ).to_list(5000)
    for u in candidates:
        tags = (u.get("ai_domains") or []) + (u.get("domains") or [])
        if not tags:
            continue
        if _job_match_score(job, tags) > 0:
            await notify_user(
                u["user_id"], "job", "Nouvelle offre pour vous",
                f"« {job.get('title', '')} » correspond à votre profil. Postulez dès maintenant !",
                {"job_id": job["id"]},
            )


async def ai_rank_candidates(job: dict, candidates: list) -> dict:
    """Return {candidate_id: {"score": int, "reason": str}} ranked by AI."""
    if not GEMINI_API_KEY or not candidates:
        return {}
    cids = [c["user_id"] for c in candidates]
    cv_rows = await db.cv_data.find(
        {"user_id": {"$in": cids}, "status": "scanned"},
        {"_id": 0, "user_id": 1, "structured": 1},
    ).to_list(5000)
    cvmap = {d["user_id"]: (d.get("structured") or {}) for d in cv_rows}
    lines = []
    for c in candidates:
        tags = (c.get("domains") or []) + (c.get("ai_domains") or [])
        s = cvmap.get(c["user_id"]) or {}
        skills = ", ".join((s.get("skills") or [])[:30])
        exps = "; ".join(
            f"{e.get('title','')}@{e.get('company','')}({e.get('start','')}-{e.get('end','')})"
            for e in (s.get("experiences") or [])[:6] if isinstance(e, dict)
        )
        edu = "; ".join(
            f"{e.get('degree','')}-{e.get('school','')}"
            for e in (s.get("education") or [])[:4] if isinstance(e, dict)
        )
        langs = ", ".join(s.get("languages") or [])
        summary = (s.get("summary") or "")[:300]
        lines.append(
            f"- id={c['user_id']} | nom={c.get('name','')} | poste={s.get('current_position') or c.get('current_position','')} "
            f"| domaines={', '.join(tags)} | outils={', '.join(c.get('tools') or [])} "
            f"| experience={s.get('years_experience') or c.get('years_experience','?')} ans "
            f"| competences_CV={skills} | experiences_CV={exps} | formations={edu} | langues={langs} "
            f"| resume_CV={summary} | bio={(c.get('bio') or '')[:200]}"
        )
    prompt = (
        f"OFFRE:\nTitre: {job.get('title','')}\nCategorie: {job.get('category','')}\n"
        f"Description: {(job.get('description') or '')[:1500]}\n"
        f"Profil recherche: {(job.get('requirements') or '')[:1000]}\n\n"
        f"CANDIDATS:\n" + "\n".join(lines) +
        "\n\nClasse les candidats du plus pertinent au moins pertinent pour cette offre."
    )
    system = (
        "Tu es un expert RH. On te donne une offre d'emploi et une liste de candidats. "
        "Reponds UNIQUEMENT par un tableau JSON valide, sans aucun texte autour. "
        "Chaque element du tableau: {\"candidate_id\": \"<id>\", \"score\": <entier 0-100 de pertinence>, "
        "\"reason\": \"<justification concise en francais, 1 phrase>\"}. "
        "Inclure uniquement les candidats avec un score >= 40, tries par score decroissant."
    )
    try:
        raw = await gemini_generate(system, prompt)
        raw = (raw or "").strip()
        arr = []
        try:
            arr = json.loads(raw)
        except Exception:
            m = re.search(r"\[.*\]", raw, re.DOTALL)
            if m:
                arr = json.loads(m.group(0))
        out = {}
        for x in arr if isinstance(arr, list) else []:
            cid = x.get("candidate_id")
            if cid:
                out[str(cid)] = {"score": int(x.get("score", 0)), "reason": x.get("reason", "")}
        return out
    except Exception as e:
        logger.error(f"ai_rank_candidates: {e}")
        return {}


async def compute_job_suggestions(job: dict, limit: int = 20) -> list:
    candidates = await db.users.find({"role": "candidate"}, {"_id": 0}).to_list(5000)
    ranking = await ai_rank_candidates(job, candidates)
    result = []
    for c in candidates:
        tags = (c.get("ai_domains") or []) + (c.get("domains") or [])
        heuristic = _job_match_score(job, tags)
        ai = ranking.get(c["user_id"])
        if ai and ai["score"] > 0:
            score, reason = ai["score"], ai["reason"] or "Profil pertinent selon l'IA."
        elif heuristic > 0:
            score, reason = min(90, 45 + heuristic * 10), "Correspondance sur les domaines d'expertise."
        else:
            continue
        result.append({
            "candidate_id": c["user_id"], "name": c.get("name", ""), "email": c.get("email", ""),
            "picture": c.get("picture"), "current_position": c.get("current_position", ""),
            "domains": tags, "score": score, "reason": reason,
        })
    result.sort(key=lambda r: r["score"], reverse=True)
    return result[:limit]


def suggestions_email_html(job: dict, top: list) -> str:
    rows = ""
    for c in top:
        pos = c.get("current_position") or ""
        pos_html = f'<br/><span style="color:#888">{pos}</span>' if pos else ""
        rows += (
            f'<tr><td style="padding-top:8px;color:#333">'
            f'<b>{c.get("name","Candidat")}</b> — {c.get("score")}% compatible'
            f'{pos_html}'
            f'<br/><span style="color:#666;font-size:13px">{c.get("reason","")}</span></td></tr>'
        )
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">'
        f'<tr><td align="center"><table width="480" cellpadding="0" cellspacing="0" style="background:#f7f7f8;border-radius:12px;padding:32px">'
        f'<tr><td style="font-size:20px;font-weight:bold;color:#111">Talent Vortex</td></tr>'
        f'<tr><td style="padding-top:12px;color:#333">Votre offre <b>{job.get("title","")}</b> vient d\'être publiée. '
        f'Voici les profils déjà présents qui correspondent le mieux :</td></tr>'
        f'{rows}'
        f'<tr><td style="padding-top:16px;color:#666;font-size:13px">Consultez la section « Suggestions IA » de votre espace administration pour les contacter.</td></tr>'
        f'</table></td></tr></table>'
    )


async def notify_admin_suggestions(job: dict):
    top = await compute_job_suggestions(job, limit=3)
    if not top:
        return
    names = ", ".join(f"{c['name']} ({c['score']}%)" for c in top)
    await notify_admins(
        "suggestion", "Profils suggérés pour votre offre",
        f"« {job.get('title','')} » : {names}.", {"job_id": job["id"]},
    )


@router.get("/jobs/{job_id}/suggestions")
async def job_suggestions(job_id: str, admin: dict = Depends(require_admin)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return await compute_job_suggestions(job)


@router.get("/jobs/{job_id}/applicant-scores")
async def job_applicant_scores(job_id: str, admin: dict = Depends(require_admin)):
    """Score de correspondance IA (0-100) pour chaque candidat ayant postulé a cette offre."""
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    apps = await db.applications.find({"job_id": job_id}, {"_id": 0, "candidate_id": 1}).to_list(2000)
    cand_ids = list({a["candidate_id"] for a in apps if a.get("candidate_id")})
    if not cand_ids:
        return {}
    candidates = await db.users.find({"user_id": {"$in": cand_ids}}, {"_id": 0}).to_list(5000)
    ranking = await ai_rank_candidates(job, candidates)
    result = {}
    for c in candidates:
        tags = (c.get("ai_domains") or []) + (c.get("domains") or [])
        ai = ranking.get(c["user_id"])
        if ai and ai.get("score", 0) > 0:
            result[c["user_id"]] = {"score": ai["score"], "reason": ai.get("reason") or "Profil pertinent selon l'IA."}
        else:
            h = _job_match_score(job, tags)
            result[c["user_id"]] = {
                "score": min(80, 35 + h * 8) if h > 0 else 20,
                "reason": "Correspondance sur les domaines." if h > 0 else "Correspondance faible avec l'offre.",
            }
    return result


def _extract_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


@router.post("/jobs/ai-draft")
async def ai_job_draft(body: JobDraftInput, admin: dict = Depends(require_admin)):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Assistant IA indisponible")
    if not (body.brief or "").strip():
        raise HTTPException(status_code=400, detail="Veuillez fournir une fiche de poste ou une description.")
    system = (
        "Tu es un assistant RH qui rédige des offres d'emploi en français. "
        "À partir d'une fiche de poste ou d'un brief, tu génères une offre structurée. "
        "Réponds UNIQUEMENT par un objet JSON valide, sans texte autour, avec exactement ces clés : "
        "title (intitulé du poste), company (entreprise, laisse vide si inconnu), location (lieu/ville, télétravail si applicable), "
        "type (un parmi: Temps plein, Temps partiel, Stage, Alternance, Freelance, CDD, CDI), "
        "category (un parmi: Tech, Data, Design, Marketing, Finance, Ressources Humaines, Commercial, Juridique, Sante, Ingenierie, General), "
        "salary (fourchette si mentionnée, sinon vide), "
        "description (2 à 4 paragraphes attractifs et professionnels décrivant le poste et les missions), "
        "requirements (le profil recherché sous forme de puces avec des tirets)."
    )
    try:
        raw = await gemini_generate(system, f"Fiche de poste / brief:\n{body.brief}")
    except Exception as e:
        logger.error(f"ai_job_draft: {e}")
        raise HTTPException(status_code=502, detail="La génération par l'IA a échoué. Réessayez.")
    data = _extract_json(raw)
    keys = ["title", "company", "location", "type", "category", "description", "requirements", "salary"]
    out = {k: (str(data.get(k)) if data.get(k) is not None else "") for k in keys}
    if not out["type"]:
        out["type"] = "Temps plein"
    if not out["category"]:
        out["category"] = "General"
    return out


@router.put("/jobs/{job_id}")
async def update_job(job_id: str, body: JobInput, admin: dict = Depends(require_admin)):
    res = await db.jobs.update_one({"id": job_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return await db.jobs.find_one({"id": job_id}, {"_id": 0})


@router.put("/jobs/{job_id}/active")
async def set_job_active(job_id: str, body: JobActiveInput, admin: dict = Depends(require_admin)):
    res = await db.jobs.update_one({"id": job_id}, {"$set": {"is_active": body.is_active}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return {"ok": True, "is_active": body.is_active}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, admin: dict = Depends(require_admin)):
    await db.jobs.delete_one({"id": job_id})
    return {"ok": True}

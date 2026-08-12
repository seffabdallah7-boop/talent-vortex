"""Candidates & users management (admin)."""
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from core import db, require_admin, require_super, get_current_user, public_user

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
    if not admin.get("is_super"):
        for u in users:
            u.pop("is_super", None)
    return users


@router.get("/users")
async def list_users(q: Optional[str] = Query(None), min_rating: Optional[int] = Query(None), admin: dict = Depends(require_admin)):
    query = {}
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [
            {"name": rx}, {"email": rx}, {"current_position": rx}, {"nationality": rx},
            {"headline": rx}, {"bio": rx}, {"domains": rx}, {"tools": rx}, {"city": rx}, {"country": rx},
        ]
    users = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    counts = await db.applications.aggregate([{"$group": {"_id": "$candidate_id", "n": {"$sum": 1}}}]).to_list(5000)
    cmap = {c["_id"]: c["n"] for c in counts}
    rmap = await _rating_map()
    for u in users:
        u["application_count"] = cmap.get(u["user_id"], 0)
        r = rmap.get(u["user_id"])
        u["rating"] = r["avg"] if r else None
        u["rating_count"] = r["n"] if r else 0
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

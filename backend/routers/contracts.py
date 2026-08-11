"""Contracts (admin) + candidate view."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from core import db, get_current_user, require_admin

router = APIRouter()


class ContractInput(BaseModel):
    title: str
    client: Optional[str] = ""
    candidate_id: Optional[str] = None
    candidate_name: Optional[str] = ""
    job_title: Optional[str] = ""
    amount: Optional[str] = ""
    start_date: Optional[str] = ""
    end_date: Optional[str] = ""
    status: str = "en_cours"
    notes: Optional[str] = ""


@router.get("/contracts/me")
async def my_contracts(user: dict = Depends(get_current_user)):
    return await db.contracts.find({"candidate_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/contracts")
async def list_contracts(status: Optional[str] = Query(None), admin: dict = Depends(require_admin)):
    q = {}
    if status and status != "all":
        q["status"] = status
    return await db.contracts.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/contracts")
async def create_contract(body: ContractInput, admin: dict = Depends(require_admin)):
    if body.status not in ("en_cours", "boucle", "resilie"):
        raise HTTPException(status_code=400, detail="Statut de contrat invalide")
    doc = body.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat()})
    await db.contracts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/contracts/{contract_id}")
async def update_contract(contract_id: str, body: ContractInput, admin: dict = Depends(require_admin)):
    res = await db.contracts.update_one({"id": contract_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contrat introuvable")
    return await db.contracts.find_one({"id": contract_id}, {"_id": 0})


@router.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: str, admin: dict = Depends(require_admin)):
    await db.contracts.delete_one({"id": contract_id})
    return {"ok": True}

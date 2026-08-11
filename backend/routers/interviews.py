"""Interviews (admin) + candidate view."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core import (
    db, get_current_user, require_admin, notify_user, send_email, interview_email_html,
)

router = APIRouter()


class InterviewInput(BaseModel):
    title: str
    candidate_id: Optional[str] = None
    candidate_name: Optional[str] = ""
    application_id: Optional[str] = None
    date: str
    time: str
    location: Optional[str] = ""
    notes: Optional[str] = ""
    status: str = "scheduled"


@router.get("/interviews")
async def list_interviews(admin: dict = Depends(require_admin)):
    return await db.interviews.find({}, {"_id": 0}).sort([("date", 1), ("time", 1)]).to_list(2000)


@router.get("/interviews/me")
async def my_interviews(user: dict = Depends(get_current_user)):
    items = await db.interviews.find({"candidate_id": user["user_id"]}, {"_id": 0}).sort([("date", 1), ("time", 1)]).to_list(500)
    return items


@router.post("/interviews")
async def create_interview(body: InterviewInput, admin: dict = Depends(require_admin)):
    doc = body.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat()})
    await db.interviews.insert_one(doc)
    doc.pop("_id", None)
    if doc.get("candidate_id"):
        await notify_user(doc["candidate_id"], "interview", "Entretien planifié",
                          f"{doc.get('title','Entretien')} le {doc.get('date','')} à {doc.get('time','')}.",
                          {"interview_id": doc["id"]})
        cand = await db.users.find_one({"user_id": doc["candidate_id"]}, {"_id": 0})
        if cand and cand.get("email"):
            await send_email(cand["email"], f"Entretien planifié — {doc.get('title','')}",
                             interview_email_html(doc))
    return doc


@router.put("/interviews/{interview_id}")
async def update_interview(interview_id: str, body: InterviewInput, admin: dict = Depends(require_admin)):
    res = await db.interviews.update_one({"id": interview_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entretien introuvable")
    return await db.interviews.find_one({"id": interview_id}, {"_id": 0})


@router.delete("/interviews/{interview_id}")
async def delete_interview(interview_id: str, admin: dict = Depends(require_admin)):
    await db.interviews.delete_one({"id": interview_id})
    return {"ok": True}

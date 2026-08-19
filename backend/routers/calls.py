"""Calls (audio/video signaling) + recordings."""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel

from core import (
    db, logger, APP_NAME, EMERGENT_LLM_KEY, gemini_generate, GEMINI_API_KEY, LlmChat, UserMessage,
    get_current_user, require_admin, put_object, transcribe_audio, notify_user,
)

router = APIRouter()


class CallInitInput(BaseModel):
    callee_id: str
    mode: str = "video"


class CallStatusInput(BaseModel):
    status: str


@router.post("/calls")
async def start_call(body: CallInitInput, admin: dict = Depends(require_admin)):
    callee = await db.users.find_one({"user_id": body.callee_id}, {"_id": 0})
    if not callee:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    room = f"recrutai-call-{uuid.uuid4().hex[:12]}"
    doc = {
        "id": str(uuid.uuid4()), "room": room,
        "mode": body.mode if body.mode in ("audio", "video") else "video",
        "caller_id": admin["user_id"], "caller_name": admin.get("name", "Recruteur"),
        "callee_id": body.callee_id, "callee_name": callee.get("name", ""),
        "status": "ringing", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.calls.insert_one(doc)
    doc.pop("_id", None)
    await notify_user(body.callee_id, "call", "Appel entrant", f"{doc['caller_name']} vous appelle.")
    return doc


@router.get("/calls/incoming")
async def incoming_call(user: dict = Depends(get_current_user)):
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    call = await db.calls.find_one(
        {"callee_id": user["user_id"], "status": "ringing", "created_at": {"$gte": cutoff}},
        {"_id": 0}, sort=[("created_at", -1)],
    )
    return call or {}


@router.get("/calls/{call_id}")
async def get_call(call_id: str, user: dict = Depends(get_current_user)):
    call = await db.calls.find_one({"id": call_id}, {"_id": 0})
    if not call:
        raise HTTPException(status_code=404, detail="Appel introuvable")
    if user["user_id"] not in (call["caller_id"], call["callee_id"]):
        raise HTTPException(status_code=403, detail="Accès refusé")
    return call


@router.put("/calls/{call_id}/status")
async def set_call_status(call_id: str, body: CallStatusInput, user: dict = Depends(get_current_user)):
    if body.status not in ("accepted", "declined", "ended", "cancelled"):
        raise HTTPException(status_code=400, detail="Statut invalide")
    res = await db.calls.update_one({"id": call_id}, {"$set": {"status": body.status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appel introuvable")
    return await db.calls.find_one({"id": call_id}, {"_id": 0})


async def summarize_transcript(transcript: str) -> str:
    try:
        return await gemini_generate(
            "Tu es un assistant RH. A partir de la transcription d'un entretien de recrutement, "
            "redige en francais un compte-rendu structure et concis avec ces sections : "
            "1) Resume (3-4 phrases), 2) Points forts du candidat, 3) Points d'attention, "
            "4) Prochaines etapes recommandees. Reste factuel.",
            f"Transcription de l'entretien:\n{transcript[:12000]}",
        )
    except Exception as e:
        logger.error(f"summarize_transcript: {e}")
        return ""


async def process_recording(rec_id: str, audio_bytes: bytes):
    transcript = await transcribe_audio(audio_bytes, "webm")
    summary = await summarize_transcript(transcript) if transcript else ""
    await db.recordings.update_one(
        {"id": rec_id},
        {"$set": {"transcript": transcript, "summary": summary, "status": "done"}},
    )


@router.post("/recordings")
async def create_recording(
    background: BackgroundTasks,
    title: str = Form(""),
    candidate_id: Optional[str] = Form(None),
    candidate_name: Optional[str] = Form(""),
    interview_id: Optional[str] = Form(None),
    video: UploadFile = File(...),
    audio: Optional[UploadFile] = File(None),
    admin: dict = Depends(require_admin),
):
    vbytes = await video.read()
    v_path = f"{APP_NAME}/recordings/{uuid.uuid4()}.webm"
    put_object(v_path, vbytes, video.content_type or "video/webm")
    video_file_id = str(uuid.uuid4())
    await db.files.insert_one({
        "id": video_file_id, "storage_path": v_path, "original_filename": video.filename or "entretien.webm",
        "content_type": video.content_type or "video/webm", "owner_id": admin["user_id"],
        "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    rec_id = str(uuid.uuid4())
    doc = {
        "id": rec_id, "title": title or "Entretien enregistre",
        "candidate_id": candidate_id, "candidate_name": candidate_name or "",
        "interview_id": interview_id, "video_file_id": video_file_id,
        "transcript": "", "summary": "", "status": "processing",
        "created_by": admin["user_id"], "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.recordings.insert_one(doc)
    doc.pop("_id", None)
    abytes = await audio.read() if audio is not None else b""
    background.add_task(process_recording, rec_id, abytes if abytes else vbytes)
    return doc


@router.get("/recordings")
async def list_recordings(admin: dict = Depends(require_admin)):
    return await db.recordings.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.delete("/recordings/{rec_id}")
async def delete_recording(rec_id: str, admin: dict = Depends(require_admin)):
    await db.recordings.delete_one({"id": rec_id})
    return {"ok": True}


@router.post("/recordings/{rec_id}/share")
async def share_recording(rec_id: str, admin: dict = Depends(require_admin)):
    rec = await db.recordings.find_one({"id": rec_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Enregistrement introuvable")
    token = rec.get("share_token")
    if not token:
        token = uuid.uuid4().hex
        await db.recordings.update_one({"id": rec_id}, {"$set": {"share_token": token}})
    return {"token": token}


@router.get("/recordings/shared/{token}")
async def get_shared_recording(token: str, admin: dict = Depends(require_admin)):
    rec = await db.recordings.find_one({"share_token": token}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Lien invalide")
    return rec

"""Applications, screening, file download."""
import re
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form, Response
from pydantic import BaseModel

from core import (
    db, logger, APP_NAME, EMERGENT_LLM_KEY, LlmChat, UserMessage,
    get_current_user, require_admin, put_object, get_object, transcribe_audio,
    notify_admins, send_email, admin_new_app_email_html, status_email_html,
    extract_cv_text,
)

router = APIRouter()


class StatusInput(BaseModel):
    status: str


class ReviewInput(BaseModel):
    admin_note: Optional[str] = ""
    rating: Optional[int] = None


class ScreeningAnswers(BaseModel):
    answers: list


SCREEN_DEFAULTS = [
    "Décrivez votre expérience la plus pertinente pour ce poste.",
    "Quels outils ou technologies maîtrisez-vous en lien avec cette offre ?",
    "Quelle est votre disponibilité pour débuter ?",
    "Pourquoi ce poste vous intéresse-t-il ?",
]


async def generate_screening_questions(job: dict) -> list:
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=f"screen-{uuid.uuid4().hex[:8]}",
            system_message=(
                "Tu es recruteur. Genere EXACTEMENT 4 questions courtes de pre-qualification en francais "
                "permettant de verifier si un candidat correspond a l'offre. Reponds uniquement par les 4 "
                "questions, une par ligne, sans numerotation ni autre texte."
            ),
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=f"Titre: {job.get('title','')}\nDescription: {job.get('description','')}\nExigences: {job.get('requirements','')}"))
        text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
        qs = [l.strip(" -•\t.") for l in text.splitlines() if l.strip()]
        qs = [q for q in qs if len(q) > 5][:4]
        return qs if len(qs) >= 2 else SCREEN_DEFAULTS
    except Exception as e:
        logger.error(f"generate_screening_questions: {e}")
        return SCREEN_DEFAULTS


async def assess_screening(job: dict, questions: list, answers: list):
    qa = "\n\n".join(f"Q{i+1}: {q}\nRéponse: {answers[i] if i < len(answers) else ''}" for i, q in enumerate(questions))
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=f"assess-{uuid.uuid4().hex[:8]}",
            system_message=(
                "Tu es recruteur senior. Evalue les reponses du candidat au regard de l'offre. "
                'Reponds STRICTEMENT en JSON valide: {"score": <entier 0-100>, '
                '"verdict": "Correspond" | "A verifier" | "Ne correspond pas", '
                '"analyse": "3-4 phrases en francais"}.'
            ),
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=f"OFFRE\nTitre: {job.get('title','')}\nExigences: {job.get('requirements','')}\n\nREPONSES DU CANDIDAT\n{qa}"))
        text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
        m = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(m.group(0)) if m else {}
        try:
            score = int(data.get("score"))
        except (TypeError, ValueError):
            score = None
        return data.get("analyse", text[:500]), data.get("verdict", "A verifier"), score
    except Exception as e:
        logger.error(f"assess_screening: {e}")
        return "", "A verifier", None


@router.post("/applications")
async def create_application(
    job_id: str = Form(...),
    cover_note: str = Form(""),
    salary_expectation: str = Form(""),
    cv: Optional[UploadFile] = File(None),
    voice: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user),
):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    if not (user.get("phone") or "").strip() or not (user.get("domains") or []):
        raise HTTPException(status_code=400, detail="Complétez votre profil (téléphone et domaines d'expertise) avant de postuler.")
    if await db.applications.find_one({"job_id": job_id, "candidate_id": user["user_id"]}):
        raise HTTPException(status_code=400, detail="Vous avez déjà postulé à cette offre.")

    # CV : fichier joint sinon CV du profil (obligatoire pour le matching IA)
    cv_bytes = await cv.read() if cv is not None else b""
    if cv_bytes:
        cv_ext = cv.filename.split(".")[-1] if "." in (cv.filename or "") else "pdf"
        cv_path = f"{APP_NAME}/cv/{user['user_id']}/{uuid.uuid4()}.{cv_ext}"
        put_object(cv_path, cv_bytes, cv.content_type or "application/pdf")
        cv_file_id = str(uuid.uuid4())
        cv_filename = cv.filename
        await db.files.insert_one({
            "id": cv_file_id, "storage_path": cv_path, "original_filename": cv.filename,
            "content_type": cv.content_type or "application/pdf", "owner_id": user["user_id"],
            "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"cv_text": extract_cv_text(cv_bytes, cv.filename or "cv.pdf")}})
    elif user.get("cv_file_id"):
        cv_file_id = user["cv_file_id"]
        cv_filename = user.get("cv_filename") or "cv.pdf"
    else:
        raise HTTPException(status_code=400, detail="Ajoutez un CV à votre profil ou joignez-en un pour postuler.")

    voice_file_id = None
    transcription = ""
    if voice is not None:
        vbytes = await voice.read()
        if vbytes:
            v_ext = "webm"
            if voice.filename and "." in voice.filename:
                v_ext = voice.filename.split(".")[-1]
            v_path = f"{APP_NAME}/voice/{user['user_id']}/{uuid.uuid4()}.{v_ext}"
            put_object(v_path, vbytes, voice.content_type or "audio/webm")
            voice_file_id = str(uuid.uuid4())
            await db.files.insert_one({
                "id": voice_file_id, "storage_path": v_path, "original_filename": voice.filename or "message-vocal.webm",
                "content_type": voice.content_type or "audio/webm", "owner_id": user["user_id"],
                "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat(),
            })
            transcription = await transcribe_audio(vbytes, "webm")

    app_doc = {
        "id": str(uuid.uuid4()),
        "job_id": job_id,
        "job_title": job["title"],
        "candidate_id": user["user_id"],
        "candidate_name": user.get("name", ""),
        "candidate_email": user["email"],
        "cv_file_id": cv_file_id,
        "cv_filename": cv_filename,
        "voice_file_id": voice_file_id,
        "transcription": transcription,
        "cover_note": cover_note,
        "salary_expectation": salary_expectation,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "screening": {
            "questions": await generate_screening_questions(job),
            "answers": [], "completed": False,
            "ai_assessment": "", "ai_verdict": "", "ai_score": None,
        },
    }
    await db.applications.insert_one(app_doc)
    app_doc.pop("_id", None)
    await notify_admins(
        "application", "Nouvelle candidature",
        f"{app_doc['candidate_name']} a postulé à « {app_doc['job_title']} ».",
    )
    return app_doc


@router.get("/applications/me")
async def my_applications(user: dict = Depends(get_current_user)):
    apps = await db.applications.find({"candidate_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for a in apps:
        sc = a.get("screening")
        if sc:
            sc.pop("ai_assessment", None)
            sc.pop("ai_verdict", None)
            sc.pop("ai_score", None)
    return apps


@router.post("/applications/{app_id}/screening")
async def submit_screening(app_id: str, body: ScreeningAnswers, user: dict = Depends(get_current_user)):
    app = await db.applications.find_one({"id": app_id})
    if not app:
        raise HTTPException(status_code=404, detail="Candidature introuvable")
    if app["candidate_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Accès refusé")
    sc = app.get("screening") or {}
    if sc.get("completed"):
        raise HTTPException(status_code=400, detail="Examen déjà complété")
    questions = sc.get("questions", [])
    answers = [str(a) for a in body.answers][:len(questions)]
    job = await db.jobs.find_one({"id": app["job_id"]}, {"_id": 0}) or {}
    assessment, verdict, score = await assess_screening(job, questions, answers)
    await db.applications.update_one({"id": app_id}, {"$set": {
        "screening.answers": answers, "screening.completed": True,
        "screening.ai_assessment": assessment, "screening.ai_verdict": verdict, "screening.ai_score": score,
        "screening.completed_at": datetime.now(timezone.utc).isoformat(),
    }})
    await notify_admins("screening", "Examen de pré-qualification complété",
                        f"{app.get('candidate_name','')} a répondu à l'examen pour « {app.get('job_title','')} ».",
                        {"candidate_id": app.get("candidate_id"), "application_id": app_id})
    return {"ok": True}


@router.get("/applications")
async def all_applications(status: Optional[str] = Query(None), job_id: Optional[str] = Query(None), admin: dict = Depends(require_admin)):
    q = {}
    if status and status != "all":
        q["status"] = status
    if job_id:
        q["job_id"] = job_id
    apps = await db.applications.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    ids = list({a["candidate_id"] for a in apps if a.get("candidate_id")})
    pics = {}
    if ids:
        async for u in db.users.find({"user_id": {"$in": ids}}, {"_id": 0, "user_id": 1, "picture": 1}):
            pics[u["user_id"]] = u.get("picture")
    for a in apps:
        a["candidate_picture"] = pics.get(a.get("candidate_id"))
    return apps


@router.put("/applications/{app_id}/status")
async def update_status(app_id: str, body: StatusInput, admin: dict = Depends(require_admin)):
    if body.status not in ("pending", "accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Statut invalide")
    appdoc = await db.applications.find_one({"id": app_id}, {"_id": 0})
    if not appdoc:
        raise HTTPException(status_code=404, detail="Candidature introuvable")
    await db.applications.update_one(
        {"id": app_id},
        {"$set": {"status": body.status, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    labels = {"accepted": "Acceptee", "rejected": "Refusee", "pending": "En attente"}
    if appdoc.get("candidate_email"):
        await send_email(appdoc["candidate_email"],
                         f"Mise a jour de votre candidature — {appdoc.get('job_title','')}",
                         status_email_html(appdoc, labels[body.status]))
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()), "user_id": appdoc["candidate_id"], "type": "status",
        "title": f"Candidature {labels[body.status].lower()}",
        "body": f"{appdoc.get('job_title','')} : votre candidature est {labels[body.status].lower()}.",
        "read": False, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return await db.applications.find_one({"id": app_id}, {"_id": 0})


@router.put("/applications/{app_id}/review")
async def review_application(app_id: str, body: ReviewInput, admin: dict = Depends(require_admin)):
    upd = {"admin_note": body.admin_note or ""}
    if body.rating is not None:
        upd["rating"] = max(1, min(5, int(body.rating)))
    res = await db.applications.update_one({"id": app_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Candidature introuvable")
    return await db.applications.find_one({"id": app_id}, {"_id": 0})


@router.delete("/applications/{app_id}")
async def delete_application(app_id: str, admin: dict = Depends(require_admin)):
    await db.applications.delete_one({"id": app_id})
    return {"ok": True}


@router.get("/files/public/{file_id}")
async def download_public_file(file_id: str):
    record = await db.files.find_one({"id": file_id, "is_deleted": False, "public": True}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    data, content_type = get_object(record["storage_path"])
    return Response(content=data, media_type=record.get("content_type", content_type))


@router.get("/files/{file_id}")
async def download_file(file_id: str, user: dict = Depends(get_current_user)):
    record = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    if user.get("role") != "admin" and record["owner_id"] != user["user_id"] and record.get("conversation_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Acces refuse")
    data, content_type = get_object(record["storage_path"])
    return Response(content=data, media_type=record.get("content_type", content_type))

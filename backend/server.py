from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
import tempfile
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import jwt
import bcrypt
import requests
import httpx
import secrets
import random
import re
import io
import csv
from fastapi import (
    FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form,
    Header, Query, Response,
)
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr

from emergentintegrations.llm.chat import LlmChat, UserMessage
from emergentintegrations.llm.openai import OpenAISpeechToText

# ---------------------------------------------------------------------------
# Config & clients
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("recruitai")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGO = "HS256"
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

APP_NAME = "recruitai"
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
_storage_key = None

app = FastAPI()
api = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Object storage helpers
# ---------------------------------------------------------------------------
def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_jwt(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def public_user(u: dict) -> dict:
    return {
        "user_id": u["user_id"],
        "email": u["email"],
        "name": u.get("name", ""),
        "role": u.get("role", "candidate"),
        "picture": u.get("picture"),
        "created_at": u.get("created_at"),
    }


async def resolve_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        uid = payload.get("sub")
        if uid:
            u = await db.users.find_one({"user_id": uid}, {"_id": 0})
            if u:
                return u
    except jwt.InvalidTokenError:
        pass
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if sess:
        exp = sess["expires_at"]
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp > datetime.now(timezone.utc):
            u = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
            if u:
                return u
    return None


async def get_current_user(
    authorization: Optional[str] = Header(None),
    auth: Optional[str] = Query(None),
) -> dict:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif auth:
        token = auth
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifie")
    user = await resolve_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session invalide")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acces reserve a l'administrateur")
    return user


# ---------------------------------------------------------------------------
# Email, security & OTP helpers
# ---------------------------------------------------------------------------
EMAIL_BASE_URL = "https://integrations.emergentagent.com"
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "RecrutAI")
ADMIN_ACCESS_CODE = os.environ.get("ADMIN_ACCESS_CODE", "")


async def send_email(to: str, subject: str, html: str):
    if not EMAIL_KEY:
        logger.warning("EMERGENT_EMAIL_KEY absent — email non envoye")
        return
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMAIL_KEY},
                json={"to": [to], "subject": subject, "html": html, "from_name": EMAIL_FROM_NAME},
            )
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Email send error: {e}")


def validate_password(pw: str):
    if len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise HTTPException(status_code=400, detail="Mot de passe trop faible : au moins 8 caracteres, une lettre et un chiffre.")


async def ensure_not_locked(email: str):
    rec = await db.login_attempts.find_one({"identifier": email})
    if rec and rec.get("locked_until"):
        lu = datetime.fromisoformat(rec["locked_until"])
        if lu.tzinfo is None:
            lu = lu.replace(tzinfo=timezone.utc)
        if lu > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Trop de tentatives. Compte bloque 15 minutes.")


async def register_failed(email: str):
    rec = await db.login_attempts.find_one({"identifier": email})
    count = (rec.get("count", 0) if rec else 0) + 1
    upd = {"identifier": email, "count": count}
    if count >= 5:
        upd["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        upd["count"] = 0
    await db.login_attempts.update_one({"identifier": email}, {"$set": upd}, upsert=True)


async def clear_attempts(email: str):
    await db.login_attempts.delete_one({"identifier": email})


async def verify_captcha(captcha_id: str, answer: str):
    if not captcha_id:
        raise HTTPException(status_code=400, detail="Verification anti-robot requise")
    rec = await db.captchas.find_one({"cid": captcha_id})
    if not rec:
        raise HTTPException(status_code=400, detail="Captcha invalide ou expire")
    exp = datetime.fromisoformat(rec["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    expired = exp < datetime.now(timezone.utc)
    ok = (not expired) and verify_password(str(answer).strip(), rec["answer_hash"])
    await db.captchas.delete_one({"cid": captcha_id})
    if not ok:
        raise HTTPException(status_code=400, detail="Verification anti-robot echouee")


def otp_email_html(code: str, name: str) -> str:
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">'
        f'<tr><td align="center"><table width="480" cellpadding="0" cellspacing="0" style="background:#f7f7f8;border-radius:12px;padding:32px">'
        f'<tr><td style="font-size:20px;font-weight:bold;color:#111">RecrutAI</td></tr>'
        f'<tr><td style="padding-top:12px;color:#333">Bonjour {name or ""}, voici votre code de connexion :</td></tr>'
        f'<tr><td align="center" style="padding:24px 0"><span style="font-size:34px;letter-spacing:8px;font-weight:bold;color:#0b3fb5">{code}</span></td></tr>'
        f'<tr><td style="color:#666;font-size:13px">Ce code expire dans 10 minutes. Si vous n\'etes pas a l\'origine de cette connexion, ignorez cet email.</td></tr>'
        f'</table></td></tr></table>'
    )


def status_email_html(appdoc: dict, label: str) -> str:
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">'
        f'<tr><td align="center"><table width="480" cellpadding="0" cellspacing="0" style="background:#f7f7f8;border-radius:12px;padding:32px">'
        f'<tr><td style="font-size:20px;font-weight:bold;color:#111">RecrutAI</td></tr>'
        f'<tr><td style="padding-top:12px;color:#333">Bonjour {appdoc.get("candidate_name","")},</td></tr>'
        f'<tr><td style="padding-top:8px;color:#333">Le statut de votre candidature au poste <b>{appdoc.get("job_title","")}</b> est desormais : <b>{label}</b>.</td></tr>'
        f'<tr><td style="padding-top:16px;color:#666;font-size:13px">Connectez-vous a votre espace candidat pour plus de details.</td></tr>'
        f'</table></td></tr></table>'
    )


def reset_email_html(code: str, name: str) -> str:
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">'
        f'<tr><td align="center"><table width="480" cellpadding="0" cellspacing="0" style="background:#f7f7f8;border-radius:12px;padding:32px">'
        f'<tr><td style="font-size:20px;font-weight:bold;color:#111">RecrutAI</td></tr>'
        f'<tr><td style="padding-top:12px;color:#333">Bonjour {name or ""}, voici votre code de reinitialisation :</td></tr>'
        f'<tr><td align="center" style="padding:24px 0"><span style="font-size:34px;letter-spacing:8px;font-weight:bold;color:#0b3fb5">{code}</span></td></tr>'
        f'<tr><td style="color:#666;font-size:13px">Ce code expire dans 1 heure. Si vous n\'etes pas a l\'origine de cette demande, ignorez cet email.</td></tr>'
        f'</table></td></tr></table>'
    )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class RegisterInput(BaseModel):
    name: str
    email: EmailStr
    password: str
    captcha_id: str
    captcha_answer: str


class LoginInput(BaseModel):
    email: EmailStr
    password: str
    admin_code: Optional[str] = None
    captcha_id: str
    captcha_answer: str


class OtpInput(BaseModel):
    email: EmailStr
    code: str


class GoogleSessionInput(BaseModel):
    session_id: str


class JobInput(BaseModel):
    title: str
    company: str
    location: str
    type: str = "Temps plein"
    category: str = "General"
    description: str
    requirements: Optional[str] = ""
    salary: Optional[str] = ""


class StatusInput(BaseModel):
    status: str


class ChatMessageInput(BaseModel):
    text: str
    candidate_id: Optional[str] = None


class AiChatInput(BaseModel):
    session_id: str
    message: str


class ThemeInput(BaseModel):
    primary: str
    primary_foreground: str
    name: Optional[str] = "Personnalise"


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api.post("/auth/register")
async def register(body: RegisterInput):
    await verify_captcha(body.captcha_id, body.captcha_answer)
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Cet email est deja utilise")
    validate_password(body.password)
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "user_id": user_id,
        "email": email,
        "name": body.name.strip(),
        "role": "candidate",
        "password_hash": hash_password(body.password),
        "auth_provider": "email",
        "picture": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    token = create_jwt(user_id, email)
    return {"token": token, "user": public_user(doc)}


@api.post("/auth/login")
async def login(body: LoginInput):
    await verify_captcha(body.captcha_id, body.captcha_answer)
    email = body.email.lower().strip()
    await ensure_not_locked(email)
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        await register_failed(email)
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    await clear_attempts(email)
    if user.get("role") == "admin" and ADMIN_ACCESS_CODE:
        if (body.admin_code or "").strip() != ADMIN_ACCESS_CODE:
            raise HTTPException(status_code=403, detail="Code administrateur invalide")
    otp = f"{random.randint(0, 999999):06d}"
    await db.otp_codes.update_one(
        {"email": email},
        {"$set": {"email": email, "code_hash": hash_password(otp),
                  "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(), "attempts": 0}},
        upsert=True,
    )
    logger.info(f"OTP {email} = {otp}")
    await send_email(email, "Votre code de connexion RecrutAI", otp_email_html(otp, user.get("name", "")))
    return {"otp_required": True, "email": email}


@api.post("/auth/verify-otp")
async def verify_otp(body: OtpInput):
    email = body.email.lower().strip()
    rec = await db.otp_codes.find_one({"email": email})
    if not rec:
        raise HTTPException(status_code=400, detail="Aucun code en attente. Reconnectez-vous.")
    exp = datetime.fromisoformat(rec["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        await db.otp_codes.delete_one({"email": email})
        raise HTTPException(status_code=400, detail="Code expire. Reconnectez-vous.")
    if rec.get("attempts", 0) >= 5:
        raise HTTPException(status_code=429, detail="Trop de tentatives. Reconnectez-vous.")
    if not verify_password(body.code, rec["code_hash"]):
        await db.otp_codes.update_one({"email": email}, {"$inc": {"attempts": 1}})
        raise HTTPException(status_code=400, detail="Code incorrect")
    await db.otp_codes.delete_one({"email": email})
    user = await db.users.find_one({"email": email})
    token = create_jwt(user["user_id"], email)
    return {"token": token, "user": public_user(user)}


@api.get("/auth/captcha")
async def get_captcha():
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    cid = secrets.token_urlsafe(12)
    await db.captchas.update_one(
        {"cid": cid},
        {"$set": {"cid": cid, "answer_hash": hash_password(str(a + b)),
                  "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}},
        upsert=True,
    )
    return {"captcha_id": cid, "question": f"{a} + {b}"}


class ForgotInput(BaseModel):
    email: EmailStr
    captcha_id: str
    captcha_answer: str


class ResetInput(BaseModel):
    email: EmailStr
    code: str
    new_password: str


@api.post("/auth/forgot-password")
async def forgot_password(body: ForgotInput):
    await verify_captcha(body.captcha_id, body.captcha_answer)
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if user and user.get("password_hash"):
        code = f"{random.randint(0, 999999):06d}"
        await db.password_reset_tokens.update_one(
            {"email": email},
            {"$set": {"email": email, "code_hash": hash_password(code),
                      "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "used": False}},
            upsert=True,
        )
        logger.info(f"RESET {email} = {code}")
        await send_email(email, "Reinitialisation de votre mot de passe RecrutAI", reset_email_html(code, user.get("name", "")))
    return {"ok": True}


@api.post("/auth/reset-password")
async def reset_password(body: ResetInput):
    email = body.email.lower().strip()
    rec = await db.password_reset_tokens.find_one({"email": email})
    if not rec or rec.get("used"):
        raise HTTPException(status_code=400, detail="Aucune demande de reinitialisation valide.")
    exp = datetime.fromisoformat(rec["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Code expire. Refaites une demande.")
    if not verify_password(body.code, rec["code_hash"]):
        raise HTTPException(status_code=400, detail="Code incorrect")
    validate_password(body.new_password)
    await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(body.new_password)}})
    await db.password_reset_tokens.update_one({"email": email}, {"$set": {"used": True}})
    await clear_attempts(email)
    return {"ok": True}


@api.post("/auth/google/session")
async def google_session(body: GoogleSessionInput):
    resp = requests.get(
        "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
        headers={"X-Session-ID": body.session_id}, timeout=30,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Session Google invalide")
    data = resp.json()
    email = data["email"].lower().strip()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        user = {
            "user_id": user_id,
            "email": email,
            "name": data.get("name", email.split("@")[0]),
            "role": "candidate",
            "password_hash": None,
            "auth_provider": "google",
            "picture": data.get("picture"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    else:
        await db.users.update_one({"email": email}, {"$set": {"picture": data.get("picture")}})
    session_token = data["session_token"]
    await db.user_sessions.insert_one({
        "user_id": user["user_id"],
        "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"token": session_token, "user": public_user(user)}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
@api.get("/jobs")
async def list_jobs():
    jobs = await db.jobs.find({"is_active": True}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return jobs


@api.get("/jobs/all")
async def list_all_jobs(admin: dict = Depends(require_admin)):
    jobs = await db.jobs.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for j in jobs:
        j["applicants"] = await db.applications.count_documents({"job_id": j["id"]})
    return jobs


@api.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return job


@api.post("/jobs")
async def create_job(body: JobInput, admin: dict = Depends(require_admin)):
    doc = body.model_dump()
    doc.update({
        "id": str(uuid.uuid4()),
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.jobs.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/jobs/{job_id}")
async def update_job(job_id: str, body: JobInput, admin: dict = Depends(require_admin)):
    res = await db.jobs.update_one({"id": job_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return await db.jobs.find_one({"id": job_id}, {"_id": 0})


@api.delete("/jobs/{job_id}")
async def delete_job(job_id: str, admin: dict = Depends(require_admin)):
    await db.jobs.delete_one({"id": job_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
async def transcribe_audio(data: bytes, ext: str) -> str:
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
        with open(tmp_path, "rb") as af:
            resp = await stt.transcribe(file=af, model="whisper-1", response_format="json", language="fr")
        os.unlink(tmp_path)
        return getattr(resp, "text", "") or ""
    except Exception as e:
        logger.error(f"Transcription echouee: {e}")
        return ""


@api.post("/applications")
async def create_application(
    job_id: str = Form(...),
    cover_note: str = Form(""),
    cv: UploadFile = File(...),
    voice: Optional[UploadFile] = File(None),
    user: dict = Depends(get_current_user),
):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Offre introuvable")

    # CV upload
    cv_bytes = await cv.read()
    cv_ext = cv.filename.split(".")[-1] if "." in (cv.filename or "") else "pdf"
    cv_path = f"{APP_NAME}/cv/{user['user_id']}/{uuid.uuid4()}.{cv_ext}"
    put_object(cv_path, cv_bytes, cv.content_type or "application/pdf")
    cv_file_id = str(uuid.uuid4())
    await db.files.insert_one({
        "id": cv_file_id, "storage_path": cv_path, "original_filename": cv.filename,
        "content_type": cv.content_type or "application/pdf", "owner_id": user["user_id"],
        "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat(),
    })

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
        "cv_filename": cv.filename,
        "voice_file_id": voice_file_id,
        "transcription": transcription,
        "cover_note": cover_note,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.applications.insert_one(app_doc)
    app_doc.pop("_id", None)
    return app_doc


@api.get("/applications/me")
async def my_applications(user: dict = Depends(get_current_user)):
    apps = await db.applications.find({"candidate_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return apps


@api.get("/applications")
async def all_applications(status: Optional[str] = Query(None), admin: dict = Depends(require_admin)):
    q = {}
    if status and status != "all":
        q["status"] = status
    apps = await db.applications.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return apps


@api.put("/applications/{app_id}/status")
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
    return await db.applications.find_one({"id": app_id}, {"_id": 0})


class ReviewInput(BaseModel):
    admin_note: Optional[str] = ""
    rating: Optional[int] = None


@api.put("/applications/{app_id}/review")
async def review_application(app_id: str, body: ReviewInput, admin: dict = Depends(require_admin)):
    upd = {"admin_note": body.admin_note or ""}
    if body.rating is not None:
        upd["rating"] = body.rating
    res = await db.applications.update_one({"id": app_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Candidature introuvable")
    return await db.applications.find_one({"id": app_id}, {"_id": 0})


@api.delete("/applications/{app_id}")
async def delete_application(app_id: str, admin: dict = Depends(require_admin)):
    await db.applications.delete_one({"id": app_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Files (CV download + audio playback)
# ---------------------------------------------------------------------------
@api.get("/files/{file_id}")
async def download_file(file_id: str, user: dict = Depends(get_current_user)):
    record = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    if user.get("role") != "admin" and record["owner_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Acces refuse")
    data, content_type = get_object(record["storage_path"])
    return Response(content=data, media_type=record.get("content_type", content_type))


# ---------------------------------------------------------------------------
# Candidates management (admin)
# ---------------------------------------------------------------------------
@api.get("/candidates")
async def list_candidates(admin: dict = Depends(require_admin)):
    users = await db.users.find({"role": "candidate"}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    for u in users:
        u["application_count"] = await db.applications.count_documents({"candidate_id": u["user_id"]})
    return users


@api.get("/users")
async def list_users(admin: dict = Depends(require_admin)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    for u in users:
        u["application_count"] = await db.applications.count_documents({"candidate_id": u["user_id"]})
    return users


class RoleInput(BaseModel):
    role: str


@api.put("/users/{user_id}/role")
async def set_user_role(user_id: str, body: RoleInput, admin: dict = Depends(require_admin)):
    if body.role not in ("admin", "candidate"):
        raise HTTPException(status_code=400, detail="Rôle invalide")
    if user_id == admin["user_id"] and body.role != "admin":
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas retirer votre propre rôle admin")
    res = await db.users.update_one({"user_id": user_id}, {"$set": {"role": body.role}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})


@api.delete("/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas supprimer votre propre compte")
    await db.users.delete_one({"user_id": user_id})
    await db.applications.delete_many({"candidate_id": user_id})
    await db.messages.delete_many({"conversation_id": user_id})
    return {"ok": True}


@api.delete("/candidates/{user_id}")
async def delete_candidate(user_id: str, admin: dict = Depends(require_admin)):
    await db.users.delete_one({"user_id": user_id, "role": "candidate"})
    await db.applications.delete_many({"candidate_id": user_id})
    await db.messages.delete_many({"conversation_id": user_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Admin <-> Candidate chat (polling based)
# ---------------------------------------------------------------------------
@api.get("/chat/conversations")
async def conversations(admin: dict = Depends(require_admin)):
    pipeline = [
        {"$sort": {"created_at": -1}},
        {"$group": {
            "_id": "$conversation_id",
            "last_text": {"$first": "$text"},
            "last_at": {"$first": "$created_at"},
            "candidate_name": {"$first": "$candidate_name"},
        }},
        {"$sort": {"last_at": -1}},
    ]
    convs = await db.messages.aggregate(pipeline).to_list(1000)
    result = []
    for c in convs:
        unread = await db.messages.count_documents({"conversation_id": c["_id"], "sender_role": "candidate", "read": False})
        result.append({
            "candidate_id": c["_id"], "candidate_name": c.get("candidate_name", ""),
            "last_text": c.get("last_text", ""), "last_at": c.get("last_at"), "unread": unread,
        })
    return result


@api.get("/chat/messages")
async def get_messages(candidate_id: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    if user.get("role") == "admin":
        if not candidate_id:
            raise HTTPException(status_code=400, detail="candidate_id requis")
        conv = candidate_id
        await db.messages.update_many({"conversation_id": conv, "sender_role": "candidate"}, {"$set": {"read": True}})
    else:
        conv = user["user_id"]
        await db.messages.update_many({"conversation_id": conv, "sender_role": "admin"}, {"$set": {"read": True}})
    msgs = await db.messages.find({"conversation_id": conv}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    return msgs


@api.post("/chat/messages")
async def send_message(body: ChatMessageInput, user: dict = Depends(get_current_user)):
    if user.get("role") == "admin":
        if not body.candidate_id:
            raise HTTPException(status_code=400, detail="candidate_id requis")
        conv = body.candidate_id
        cand = await db.users.find_one({"user_id": conv}, {"_id": 0})
        candidate_name = cand.get("name", "") if cand else ""
        sender_role = "admin"
    else:
        conv = user["user_id"]
        candidate_name = user.get("name", "")
        sender_role = "candidate"
    doc = {
        "id": str(uuid.uuid4()),
        "conversation_id": conv,
        "candidate_name": candidate_name,
        "sender_id": user["user_id"],
        "sender_role": sender_role,
        "text": body.text,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# AI assistant (Claude Sonnet 4.6)
# ---------------------------------------------------------------------------
AI_SYSTEM = (
    "Tu es l'assistant virtuel de RecrutAI, une plateforme de recrutement en ligne. "
    "Tu reponds en francais, de maniere concise, chaleureuse et professionnelle. "
    "Tu aides les candidats a comprendre comment postuler (envoi d'un CV et d'un message vocal), "
    "consulter le statut de leurs candidatures (en attente, acceptee, refusee), "
    "et repondre a leurs questions sur les offres d'emploi et le processus de recrutement. "
    "Si une question depasse tes competences, invite poliment le candidat a contacter le support via le chat en direct."
)


@api.post("/ai/chat")
async def ai_chat(body: AiChatInput):
    prev = await db.ai_messages.find({"session_id": body.session_id}, {"_id": 0}).sort("created_at", 1).to_list(20)
    context = ""
    if prev:
        recent = prev[-8:]
        context = "\n".join([f"{m['role']}: {m['text']}" for m in recent])
    user_text = body.message
    if context:
        user_text = f"Historique recent de la conversation:\n{context}\n\nNouvelle question du candidat: {body.message}"

    await db.ai_messages.insert_one({
        "session_id": body.session_id, "role": "user", "text": body.message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    reply = "Desole, je rencontre un souci technique. Reessayez dans un instant."
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=body.session_id,
            system_message=AI_SYSTEM,
        ).with_model("anthropic", "claude-sonnet-4-6")
        response = await chat.send_message(UserMessage(text=user_text))
        reply = response if isinstance(response, str) else getattr(response, "text", str(response))
    except Exception as e:
        logger.error(f"AI chat error: {e}")

    await db.ai_messages.insert_one({
        "session_id": body.session_id, "role": "assistant", "text": reply,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"reply": reply}


@api.get("/ai/history")
async def ai_history(session_id: str = Query(...)):
    msgs = await db.ai_messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return msgs


# ---------------------------------------------------------------------------
# Theme settings
# ---------------------------------------------------------------------------
DEFAULT_THEME = {"primary": "220 100% 33%", "primary_foreground": "0 0% 100%", "name": "Bleu Corporate"}


@api.get("/settings/theme")
async def get_theme():
    doc = await db.settings.find_one({"key": "theme"}, {"_id": 0})
    if not doc:
        return DEFAULT_THEME
    return {"primary": doc["primary"], "primary_foreground": doc["primary_foreground"], "name": doc.get("name")}


@api.put("/settings/theme")
async def set_theme(body: ThemeInput, admin: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"key": "theme"},
        {"$set": {"key": "theme", "primary": body.primary, "primary_foreground": body.primary_foreground, "name": body.name}},
        upsert=True,
    )
    return {"primary": body.primary, "primary_foreground": body.primary_foreground, "name": body.name}


# ---------------------------------------------------------------------------
# Admin stats
# ---------------------------------------------------------------------------
@api.get("/admin/stats")
async def admin_stats(admin: dict = Depends(require_admin)):
    today = datetime.now(timezone.utc).date().isoformat()
    return {
        "jobs": await db.jobs.count_documents({}),
        "active_jobs": await db.jobs.count_documents({"is_active": True}),
        "candidates": await db.users.count_documents({"role": "candidate"}),
        "applications": await db.applications.count_documents({}),
        "pending": await db.applications.count_documents({"status": "pending"}),
        "accepted": await db.applications.count_documents({"status": "accepted"}),
        "rejected": await db.applications.count_documents({"status": "rejected"}),
        "contracts_active": await db.contracts.count_documents({"status": "en_cours"}),
        "contracts_closed": await db.contracts.count_documents({"status": "boucle"}),
        "contracts_terminated": await db.contracts.count_documents({"status": "resilie"}),
        "upcoming_interviews": await db.interviews.count_documents({"date": {"$gte": today}}),
    }


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


@api.get("/contracts")
async def list_contracts(status: Optional[str] = Query(None), admin: dict = Depends(require_admin)):
    q = {}
    if status and status != "all":
        q["status"] = status
    return await db.contracts.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@api.post("/contracts")
async def create_contract(body: ContractInput, admin: dict = Depends(require_admin)):
    if body.status not in ("en_cours", "boucle", "resilie"):
        raise HTTPException(status_code=400, detail="Statut de contrat invalide")
    doc = body.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat()})
    await db.contracts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/contracts/{contract_id}")
async def update_contract(contract_id: str, body: ContractInput, admin: dict = Depends(require_admin)):
    res = await db.contracts.update_one({"id": contract_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Contrat introuvable")
    return await db.contracts.find_one({"id": contract_id}, {"_id": 0})


@api.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: str, admin: dict = Depends(require_admin)):
    await db.contracts.delete_one({"id": contract_id})
    return {"ok": True}


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


@api.get("/interviews")
async def list_interviews(admin: dict = Depends(require_admin)):
    return await db.interviews.find({}, {"_id": 0}).sort([("date", 1), ("time", 1)]).to_list(2000)


@api.post("/interviews")
async def create_interview(body: InterviewInput, admin: dict = Depends(require_admin)):
    doc = body.model_dump()
    doc.update({"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat()})
    await db.interviews.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.put("/interviews/{interview_id}")
async def update_interview(interview_id: str, body: InterviewInput, admin: dict = Depends(require_admin)):
    res = await db.interviews.update_one({"id": interview_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Entretien introuvable")
    return await db.interviews.find_one({"id": interview_id}, {"_id": 0})


@api.delete("/interviews/{interview_id}")
async def delete_interview(interview_id: str, admin: dict = Depends(require_admin)):
    await db.interviews.delete_one({"id": interview_id})
    return {"ok": True}


@api.get("/export/applications")
async def export_applications(admin: dict = Depends(require_admin)):
    apps = await db.applications.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Candidat", "Email", "Offre", "Statut", "Note admin", "Evaluation", "Date"])
    for a in apps:
        w.writerow([a.get("candidate_name", ""), a.get("candidate_email", ""), a.get("job_title", ""),
                    a.get("status", ""), a.get("admin_note", ""), a.get("rating", ""), a.get("created_at", "")])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=candidatures.csv"})


@api.get("/export/contracts")
async def export_contracts(admin: dict = Depends(require_admin)):
    rows = await db.contracts.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Intitule", "Client", "Candidat", "Offre", "Montant", "Debut", "Fin", "Statut"])
    for c in rows:
        w.writerow([c.get("title", ""), c.get("client", ""), c.get("candidate_name", ""), c.get("job_title", ""),
                    c.get("amount", ""), c.get("start_date", ""), c.get("end_date", ""), c.get("status", "")])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=contrats.csv"})


@api.get("/")
async def root():
    return {"message": "RecrutAI API"}


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("user_id")
        await db.login_attempts.create_index("identifier")
        await db.otp_codes.create_index("email", unique=True)
        await db.interviews.create_index("date")
        await db.password_reset_tokens.create_index("email")
        await db.captchas.create_index("cid", unique=True)
    except Exception as e:
        logger.warning(f"Index warning: {e}")
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    # Seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "").lower().strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if admin_email and admin_password:
        existing = await db.users.find_one({"email": admin_email})
        if not existing:
            await db.users.insert_one({
                "user_id": f"user_{uuid.uuid4().hex[:12]}",
                "email": admin_email, "name": "Administrateur", "role": "admin",
                "password_hash": hash_password(admin_password), "auth_provider": "email",
                "picture": None, "created_at": datetime.now(timezone.utc).isoformat(),
            })
            logger.info("Admin seeded")
        else:
            updates = {"role": "admin"}
            if not existing.get("password_hash") or not verify_password(admin_password, existing["password_hash"]):
                updates["password_hash"] = hash_password(admin_password)
            await db.users.update_one({"email": admin_email}, {"$set": updates})


@app.on_event("shutdown")
async def shutdown():
    client.close()


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

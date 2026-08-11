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
import json
from fastapi import (
    FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form,
    Header, Query, Response, BackgroundTasks,
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
        "exp": datetime.now(timezone.utc) + timedelta(days=14),
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
        "phone": u.get("phone", ""),
        "nationality": u.get("nationality", ""),
        "city": u.get("city", ""),
        "country": u.get("country", ""),
        "domains": u.get("domains", []),
        "tools": u.get("tools", []),
        "years_experience": u.get("years_experience"),
        "current_position": u.get("current_position", ""),
        "headline": u.get("headline", ""),
        "bio": u.get("bio", ""),
        "ai_domains": u.get("ai_domains", []),
        "profile_completed": u.get("profile_completed", False),
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
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Talent Vortex")
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
        f'<tr><td style="font-size:20px;font-weight:bold;color:#111">Talent Vortex</td></tr>'
        f'<tr><td style="padding-top:12px;color:#333">Bonjour {name or ""}, voici votre code de connexion :</td></tr>'
        f'<tr><td align="center" style="padding:24px 0"><span style="font-size:34px;letter-spacing:8px;font-weight:bold;color:#0b3fb5">{code}</span></td></tr>'
        f'<tr><td style="color:#666;font-size:13px">Ce code expire dans 10 minutes. Si vous n\'etes pas a l\'origine de cette connexion, ignorez cet email.</td></tr>'
        f'</table></td></tr></table>'
    )


def status_email_html(appdoc: dict, label: str) -> str:
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">'
        f'<tr><td align="center"><table width="480" cellpadding="0" cellspacing="0" style="background:#f7f7f8;border-radius:12px;padding:32px">'
        f'<tr><td style="font-size:20px;font-weight:bold;color:#111">Talent Vortex</td></tr>'
        f'<tr><td style="padding-top:12px;color:#333">Bonjour {appdoc.get("candidate_name","")},</td></tr>'
        f'<tr><td style="padding-top:8px;color:#333">Le statut de votre candidature au poste <b>{appdoc.get("job_title","")}</b> est desormais : <b>{label}</b>.</td></tr>'
        f'<tr><td style="padding-top:16px;color:#666;font-size:13px">Connectez-vous a votre espace candidat pour plus de details.</td></tr>'
        f'</table></td></tr></table>'
    )


def reset_email_html(code: str, name: str) -> str:
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">'
        f'<tr><td align="center"><table width="480" cellpadding="0" cellspacing="0" style="background:#f7f7f8;border-radius:12px;padding:32px">'
        f'<tr><td style="font-size:20px;font-weight:bold;color:#111">Talent Vortex</td></tr>'
        f'<tr><td style="padding-top:12px;color:#333">Bonjour {name or ""}, voici votre code de reinitialisation :</td></tr>'
        f'<tr><td align="center" style="padding:24px 0"><span style="font-size:34px;letter-spacing:8px;font-weight:bold;color:#0b3fb5">{code}</span></td></tr>'
        f'<tr><td style="color:#666;font-size:13px">Ce code expire dans 1 heure. Si vous n\'etes pas a l\'origine de cette demande, ignorez cet email.</td></tr>'
        f'</table></td></tr></table>'
    )


def admin_new_app_email_html(appdoc: dict) -> str:
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">'
        f'<tr><td align="center"><table width="480" cellpadding="0" cellspacing="0" style="background:#f7f7f8;border-radius:12px;padding:32px">'
        f'<tr><td style="font-size:20px;font-weight:bold;color:#111">Talent Vortex</td></tr>'
        f'<tr><td style="padding-top:12px;color:#333">Nouvelle candidature reçue.</td></tr>'
        f'<tr><td style="padding-top:8px;color:#333"><b>{appdoc.get("candidate_name","")}</b> a postulé au poste <b>{appdoc.get("job_title","")}</b>.</td></tr>'
        f'<tr><td style="padding-top:16px;color:#666;font-size:13px">Connectez-vous à l\'espace administration pour consulter le CV et le message vocal.</td></tr>'
        f'</table></td></tr></table>'
    )


def interview_email_html(itw: dict, reminder: bool = False) -> str:
    intro = "Rappel : votre entretien a lieu demain." if reminder else "Un entretien a été planifié pour vous."
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">'
        f'<tr><td align="center"><table width="480" cellpadding="0" cellspacing="0" style="background:#f7f7f8;border-radius:12px;padding:32px">'
        f'<tr><td style="font-size:20px;font-weight:bold;color:#111">Talent Vortex</td></tr>'
        f'<tr><td style="padding-top:12px;color:#333">Bonjour {itw.get("candidate_name","")}, {intro}</td></tr>'
        f'<tr><td style="padding-top:8px;color:#333"><b>{itw.get("title","")}</b><br/>Le <b>{itw.get("date","")}</b> à <b>{itw.get("time","")}</b>{(" — " + itw.get("location","")) if itw.get("location") else ""}</td></tr>'
        f'<tr><td style="padding-top:16px;color:#666;font-size:13px">Connectez-vous à votre espace candidat pour rejoindre l\'entretien en visioconférence.</td></tr>'
        f'</table></td></tr></table>'
    )


async def notify_user(user_id: str, ntype: str, title: str, body: str, extra: dict = None):
    doc = {
        "id": str(uuid.uuid4()), "user_id": user_id, "type": ntype,
        "title": title, "body": body, "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        doc.update(extra)
    await db.notifications.insert_one(doc)


async def notify_admins(ntype: str, title: str, body: str, extra: dict = None):
    admins = await db.users.find({"role": "admin"}, {"_id": 0}).to_list(100)
    for a in admins:
        await notify_user(a["user_id"], ntype, title, body, extra)
    return admins


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


class ChatEditInput(BaseModel):
    text: str


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
    token = create_jwt(user["user_id"], email)
    return {"token": token, "user": public_user(user)}


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


@api.post("/auth/refresh")
async def refresh_token(user: dict = Depends(get_current_user)):
    token = create_jwt(user["user_id"], user["email"])
    return {"token": token, "user": public_user(user)}


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
        await send_email(email, "Reinitialisation de votre mot de passe Talent Vortex", reset_email_html(code, user.get("name", "")))
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


class ProfileInput(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    nationality: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    domains: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    years_experience: Optional[int] = None
    current_position: Optional[str] = None
    headline: Optional[str] = None
    bio: Optional[str] = None


async def detect_profile_domains(profile: dict) -> List[str]:
    text = " | ".join(filter(None, [
        profile.get("current_position"),
        profile.get("headline"),
        profile.get("bio"),
        ", ".join(profile.get("domains") or []),
        ", ".join(profile.get("tools") or []),
    ]))
    if not text.strip() or not EMERGENT_LLM_KEY:
        return []
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=f"domain-{uuid.uuid4().hex[:8]}",
            system_message=(
                "Tu classes un profil candidat. Reponds UNIQUEMENT par 1 a 3 domaines separes par des virgules, "
                "choisis parmi: Tech, Data, Design, Marketing, Finance, Ressources Humaines, Commercial, "
                "Juridique, Sante, Ingenierie, General. Aucune autre phrase."
            ),
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=f"Profil: {text}"))
        raw = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
        return [t.strip() for t in raw.replace("\n", ",").split(",") if t.strip()][:3]
    except Exception as e:
        logger.error(f"detect_profile_domains: {e}")
        return []


async def refresh_user_domains(user_id: str):
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not u:
        return
    tags = await detect_profile_domains(u)
    if tags:
        await db.users.update_one({"user_id": user_id}, {"$set": {"ai_domains": tags}})


@api.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    return public_user(user)


@api.put("/profile")
async def update_profile(body: ProfileInput, background: BackgroundTasks, user: dict = Depends(get_current_user)):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if upd:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    merged = {**user, **upd}
    complete = bool(merged.get("name") and merged.get("phone") and merged.get("nationality") and (merged.get("domains")))
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"profile_completed": complete}})
    background.add_task(refresh_user_domains, user["user_id"])
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return public_user(fresh)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
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


@api.get("/jobs")
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


@api.get("/jobs/all")
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


@api.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return job


@api.post("/jobs")
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
    if not EMERGENT_LLM_KEY or not candidates:
        return {}
    lines = []
    for c in candidates:
        tags = (c.get("domains") or []) + (c.get("ai_domains") or [])
        lines.append(
            f"- id={c['user_id']} | nom={c.get('name','')} | poste={c.get('current_position','')} "
            f"| domaines={', '.join(tags)} | outils={', '.join(c.get('tools') or [])} "
            f"| experience={c.get('years_experience','?')} ans | bio={(c.get('bio') or '')[:200]}"
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
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=f"suggest-{uuid.uuid4().hex[:8]}",
            system_message=system,
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=prompt))
        raw = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
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
    admins = await notify_admins(
        "suggestion", "Profils suggérés pour votre offre",
        f"« {job.get('title','')} » : {names}.", {"job_id": job["id"]},
    )
    for a in admins:
        if a.get("email"):
            await send_email(a["email"], f"Profils suggérés — {job.get('title','')}",
                             suggestions_email_html(job, top))


@api.get("/jobs/{job_id}/suggestions")
async def job_suggestions(job_id: str, admin: dict = Depends(require_admin)):
    job = await db.jobs.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return await compute_job_suggestions(job)


class JobDraftInput(BaseModel):
    brief: str


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


@api.post("/jobs/ai-draft")
async def ai_job_draft(body: JobDraftInput, admin: dict = Depends(require_admin)):
    if not EMERGENT_LLM_KEY:
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
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY, session_id=f"jobdraft-{uuid.uuid4().hex[:8]}",
            system_message=system,
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=f"Fiche de poste / brief:\n{body.brief}"))
        raw = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
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


@api.put("/jobs/{job_id}")
async def update_job(job_id: str, body: JobInput, admin: dict = Depends(require_admin)):
    res = await db.jobs.update_one({"id": job_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return await db.jobs.find_one({"id": job_id}, {"_id": 0})


class JobActiveInput(BaseModel):
    is_active: bool


@api.put("/jobs/{job_id}/active")
async def set_job_active(job_id: str, body: JobActiveInput, admin: dict = Depends(require_admin)):
    res = await db.jobs.update_one({"id": job_id}, {"$set": {"is_active": body.is_active}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return {"ok": True, "is_active": body.is_active}


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
    if await db.applications.find_one({"job_id": job_id, "candidate_id": user["user_id"]}):
        raise HTTPException(status_code=400, detail="Vous avez déjà postulé à cette offre.")

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
        "screening": {
            "questions": await generate_screening_questions(job),
            "answers": [], "completed": False,
            "ai_assessment": "", "ai_verdict": "", "ai_score": None,
        },
    }
    await db.applications.insert_one(app_doc)
    app_doc.pop("_id", None)
    admins = await notify_admins(
        "application", "Nouvelle candidature",
        f"{app_doc['candidate_name']} a postulé à « {app_doc['job_title']} ».",
    )
    for adm in admins:
        if adm.get("email"):
            await send_email(adm["email"], f"Nouvelle candidature — {app_doc['job_title']}",
                             admin_new_app_email_html(app_doc))
    return app_doc


@api.get("/applications/me")
async def my_applications(user: dict = Depends(get_current_user)):
    apps = await db.applications.find({"candidate_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    for a in apps:
        sc = a.get("screening")
        if sc:
            sc.pop("ai_assessment", None)
            sc.pop("ai_verdict", None)
            sc.pop("ai_score", None)
    return apps


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


class ScreeningAnswers(BaseModel):
    answers: list


@api.post("/applications/{app_id}/screening")
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


@api.post("/cron/cleanup-recordings")
async def cleanup_recordings_cron():
    months = int(os.environ.get("RECORDING_RETENTION_MONTHS", "6"))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=months * 30)).isoformat()
    old = await db.recordings.find({"created_at": {"$lt": cutoff}}, {"_id": 0, "id": 1, "video_file_id": 1}).to_list(2000)
    for r in old:
        if r.get("video_file_id"):
            await db.files.update_one({"id": r["video_file_id"]}, {"$set": {"is_deleted": True}})
        await db.recordings.delete_one({"id": r["id"]})
    return {"deleted": len(old)}


@api.get("/contracts/me")
async def my_contracts(user: dict = Depends(get_current_user)):
    return await db.contracts.find({"candidate_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api.get("/applications")
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
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()), "user_id": appdoc["candidate_id"], "type": "status",
        "title": f"Candidature {labels[body.status].lower()}",
        "body": f"{appdoc.get('job_title','')} : votre candidature est {labels[body.status].lower()}.",
        "read": False, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return await db.applications.find_one({"id": app_id}, {"_id": 0})


class ReviewInput(BaseModel):
    admin_note: Optional[str] = ""
    rating: Optional[int] = None


@api.put("/applications/{app_id}/review")
async def review_application(app_id: str, body: ReviewInput, admin: dict = Depends(require_admin)):
    upd = {"admin_note": body.admin_note or ""}
    if body.rating is not None:
        upd["rating"] = max(1, min(5, int(body.rating)))
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
    if user.get("role") != "admin" and record["owner_id"] != user["user_id"] and record.get("conversation_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Acces refuse")
    data, content_type = get_object(record["storage_path"])
    return Response(content=data, media_type=record.get("content_type", content_type))


# ---------------------------------------------------------------------------
# Candidates management (admin)
# ---------------------------------------------------------------------------
@api.get("/candidates")
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
    return users


async def _rating_map() -> dict:
    agg = await db.applications.aggregate([
        {"$match": {"rating": {"$ne": None}}},
        {"$group": {"_id": "$candidate_id", "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}},
    ]).to_list(5000)
    return {r["_id"]: {"avg": round(r["avg"], 1), "n": r["n"]} for r in agg}


@api.get("/users")
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
    return users


@api.get("/users/{user_id}")
async def get_user_detail(user_id: str, admin: dict = Depends(require_admin)):
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    apps = await db.applications.find({"candidate_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    interviews = await db.interviews.find({"candidate_id": user_id}, {"_id": 0}).sort([("date", 1), ("time", 1)]).to_list(500)
    contracts = await db.contracts.find({"candidate_id": user_id}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"user": public_user(u), "applications": apps, "interviews": interviews, "contracts": contracts}


@api.get("/admin/nationalities")
async def nationalities(admin: dict = Depends(require_admin)):
    agg = await db.users.aggregate([
        {"$match": {"role": "candidate"}},
        {"$group": {"_id": {"$ifNull": ["$nationality", ""]}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]).to_list(300)
    return [{"nationality": (a["_id"] or "Non renseignée"), "count": a["count"]} for a in agg]


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
PRESENCE_WINDOW = 90


def _is_online(last_seen: Optional[str]) -> bool:
    if not last_seen:
        return False
    try:
        ts = datetime.fromisoformat(last_seen)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() <= PRESENCE_WINDOW
    except Exception:
        return False


@api.post("/presence/ping")
async def presence_ping(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"last_seen": now}})
    return {"ok": True, "last_seen": now}


@api.get("/presence/admin")
async def admin_presence(user: dict = Depends(get_current_user)):
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "last_seen": 1}).to_list(100)
    seens = [a.get("last_seen") for a in admins if a.get("last_seen")]
    return {"online": any(_is_online(s) for s in seens), "last_seen": max(seens) if seens else None}


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
        cand = await db.users.find_one({"user_id": c["_id"]}, {"_id": 0, "last_seen": 1, "picture": 1})
        ls = cand.get("last_seen") if cand else None
        result.append({
            "candidate_id": c["_id"], "candidate_name": c.get("candidate_name", ""),
            "last_text": c.get("last_text", ""), "last_at": c.get("last_at"), "unread": unread,
            "last_seen": ls, "online": _is_online(ls), "picture": cand.get("picture") if cand else None,
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


def _msg_email_html(sender_name: str, text: str) -> str:
    safe = (text or "").strip()[:500]
    return (
        f'<div style="font-family:Arial,sans-serif;color:#222">'
        f'<h2 style="color:#4f46e5">Nouveau message sur Talent Vortex</h2>'
        f'<p><b>{sender_name}</b> vous a envoyé un message :</p>'
        f'<blockquote style="border-left:3px solid #4f46e5;padding-left:12px;color:#444">{safe}</blockquote>'
        f'<p>Connectez-vous à Talent Vortex pour répondre.</p></div>'
    )


async def _deliver_chat(doc, sender_role, conv, cand, preview):
    # On ne crée PAS de notification in-app par message (évite de saturer la cloche).
    # Les messages non lus sont signalés par le badge du chat. On garde l'email hors-ligne.
    if sender_role == "candidate":
        admins = await db.users.find({"role": "admin"}, {"_id": 0, "email": 1, "last_seen": 1}).to_list(50)
        for a in admins:
            if not _is_online(a.get("last_seen")) and a.get("email"):
                await send_email(a["email"], "Nouveau message — Talent Vortex",
                                 _msg_email_html(doc.get('candidate_name') or "Un candidat", preview))
    else:
        if cand and not _is_online(cand.get("last_seen")) and cand.get("email"):
            await send_email(cand["email"], "Nouveau message du recruteur — Talent Vortex",
                             _msg_email_html("Le recruteur", preview))


def _attach_kind(content_type: str) -> str:
    ct = (content_type or "").lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("audio/"):
        return "audio"
    return "file"


async def _resolve_conv(body_candidate_id, user):
    if user.get("role") == "admin":
        if not body_candidate_id:
            raise HTTPException(status_code=400, detail="candidate_id requis")
        conv = body_candidate_id
        cand = await db.users.find_one({"user_id": conv}, {"_id": 0})
        return conv, (cand.get("name", "") if cand else ""), "admin", cand
    return user["user_id"], user.get("name", ""), "candidate", None


@api.post("/chat/messages")
async def send_message(body: ChatMessageInput, user: dict = Depends(get_current_user)):
    conv, candidate_name, sender_role, cand = await _resolve_conv(body.candidate_id, user)
    doc = {
        "id": str(uuid.uuid4()),
        "conversation_id": conv,
        "candidate_name": candidate_name,
        "sender_id": user["user_id"],
        "sender_role": sender_role,
        "text": body.text,
        "attachment": None,
        "edited": False,
        "deleted": False,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(doc)
    doc.pop("_id", None)
    await _deliver_chat(doc, sender_role, conv, cand, body.text)
    return doc


@api.post("/chat/attachments")
async def send_attachment(
    candidate_id: Optional[str] = Form(None),
    text: str = Form(""),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    conv, candidate_name, sender_role, cand = await _resolve_conv(candidate_id, user)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 25 Mo)")
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "bin"
    path = f"{APP_NAME}/chat/{conv}/{uuid.uuid4()}.{ext}"
    put_object(path, data, file.content_type or "application/octet-stream")
    file_id = str(uuid.uuid4())
    await db.files.insert_one({
        "id": file_id, "storage_path": path, "original_filename": file.filename or "fichier",
        "content_type": file.content_type or "application/octet-stream", "owner_id": user["user_id"],
        "conversation_id": conv, "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    kind = _attach_kind(file.content_type)
    doc = {
        "id": str(uuid.uuid4()),
        "conversation_id": conv,
        "candidate_name": candidate_name,
        "sender_id": user["user_id"],
        "sender_role": sender_role,
        "text": text or "",
        "attachment": {"file_id": file_id, "filename": file.filename or "fichier",
                       "content_type": file.content_type or "application/octet-stream", "kind": kind},
        "edited": False,
        "deleted": False,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.messages.insert_one(doc)
    doc.pop("_id", None)
    labels = {"image": "🖼️ Image", "audio": "🎤 Message vocal", "file": "📎 Pièce jointe"}
    await _deliver_chat(doc, sender_role, conv, cand, text or labels.get(kind, "Pièce jointe"))
    return doc


@api.put("/chat/messages/{msg_id}")
async def edit_message(msg_id: str, body: ChatEditInput, user: dict = Depends(get_current_user)):
    msg = await db.messages.find_one({"id": msg_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message introuvable")
    if msg.get("sender_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Vous ne pouvez modifier que vos propres messages")
    if msg.get("attachment"):
        raise HTTPException(status_code=400, detail="Les pièces jointes ne sont pas modifiables")
    await db.messages.update_one({"id": msg_id}, {"$set": {"text": body.text, "edited": True}})
    return await db.messages.find_one({"id": msg_id}, {"_id": 0})


@api.delete("/chat/messages/{msg_id}")
async def delete_message(msg_id: str, user: dict = Depends(get_current_user)):
    msg = await db.messages.find_one({"id": msg_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message introuvable")
    if msg.get("sender_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que vos propres messages")
    await db.messages.update_one({"id": msg_id}, {"$set": {"text": "", "attachment": None, "deleted": True}})
    return {"ok": True}


@api.get("/chat/unread")
async def chat_unread(user: dict = Depends(get_current_user)):
    conv = user["user_id"]
    total_admin = await db.messages.count_documents({"conversation_id": conv, "sender_role": "admin"})
    unread = await db.messages.count_documents({"conversation_id": conv, "sender_role": "admin", "read": False})
    return {"has_admin": total_admin > 0, "unread": unread}


# ---------------------------------------------------------------------------
# Calls (audio/video signaling via polling) + Recordings
# ---------------------------------------------------------------------------
class CallInitInput(BaseModel):
    callee_id: str
    mode: str = "video"


@api.post("/calls")
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


@api.get("/calls/incoming")
async def incoming_call(user: dict = Depends(get_current_user)):
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    call = await db.calls.find_one(
        {"callee_id": user["user_id"], "status": "ringing", "created_at": {"$gte": cutoff}},
        {"_id": 0}, sort=[("created_at", -1)],
    )
    return call or {}


@api.get("/calls/{call_id}")
async def get_call(call_id: str, user: dict = Depends(get_current_user)):
    call = await db.calls.find_one({"id": call_id}, {"_id": 0})
    if not call:
        raise HTTPException(status_code=404, detail="Appel introuvable")
    if user["user_id"] not in (call["caller_id"], call["callee_id"]):
        raise HTTPException(status_code=403, detail="Accès refusé")
    return call


class CallStatusInput(BaseModel):
    status: str


@api.put("/calls/{call_id}/status")
async def set_call_status(call_id: str, body: CallStatusInput, user: dict = Depends(get_current_user)):
    if body.status not in ("accepted", "declined", "ended", "cancelled"):
        raise HTTPException(status_code=400, detail="Statut invalide")
    res = await db.calls.update_one({"id": call_id}, {"$set": {"status": body.status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appel introuvable")
    return await db.calls.find_one({"id": call_id}, {"_id": 0})


async def summarize_transcript(transcript: str) -> str:
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"rec-{uuid.uuid4().hex[:8]}",
            system_message=(
                "Tu es un assistant RH. A partir de la transcription d'un entretien de recrutement, "
                "redige en francais un compte-rendu structure et concis avec ces sections : "
                "1) Resume (3-4 phrases), 2) Points forts du candidat, 3) Points d'attention, "
                "4) Prochaines etapes recommandees. Reste factuel."
            ),
        ).with_model("anthropic", "claude-sonnet-4-6")
        resp = await chat.send_message(UserMessage(text=f"Transcription de l'entretien:\n{transcript[:12000]}"))
        return resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
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


@api.post("/recordings")
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


@api.get("/recordings")
async def list_recordings(admin: dict = Depends(require_admin)):
    return await db.recordings.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)


@api.delete("/recordings/{rec_id}")
async def delete_recording(rec_id: str, admin: dict = Depends(require_admin)):
    await db.recordings.delete_one({"id": rec_id})
    return {"ok": True}


@api.post("/recordings/{rec_id}/share")
async def share_recording(rec_id: str, admin: dict = Depends(require_admin)):
    rec = await db.recordings.find_one({"id": rec_id}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Enregistrement introuvable")
    token = rec.get("share_token")
    if not token:
        token = uuid.uuid4().hex
        await db.recordings.update_one({"id": rec_id}, {"$set": {"share_token": token}})
    return {"token": token}


@api.get("/recordings/shared/{token}")
async def get_shared_recording(token: str, admin: dict = Depends(require_admin)):
    rec = await db.recordings.find_one({"share_token": token}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Lien invalide")
    return rec


# ---------------------------------------------------------------------------
# AI assistant (Claude Sonnet 4.6)
# ---------------------------------------------------------------------------
AI_SYSTEM = (
    "Tu es l'assistant virtuel de Talent Vortex, une plateforme de recrutement en ligne. "
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


@api.get("/interviews/me")
async def my_interviews(user: dict = Depends(get_current_user)):
    items = await db.interviews.find({"candidate_id": user["user_id"]}, {"_id": 0}).sort([("date", 1), ("time", 1)]).to_list(500)
    return items


@api.post("/interviews")
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


@api.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user)):
    # Nettoyage: supprime les notifications déjà lues et vieilles de plus d'une semaine.
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    await db.notifications.delete_many({"user_id": user["user_id"], "read": True, "created_at": {"$lt": cutoff}})
    items = await db.notifications.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    unread = await db.notifications.count_documents({"user_id": user["user_id"], "read": False})
    is_admin = user.get("role") == "admin"
    admin_cache = None
    for it in items:
        actor_id = it.get("candidate_id") if is_admin else None
        if actor_id:
            u = await db.users.find_one({"user_id": actor_id}, {"_id": 0, "name": 1, "picture": 1})
            if u:
                it["actor_name"] = u.get("name") or ""
                it["actor_picture"] = u.get("picture")
        elif not is_admin and it.get("type") in ("message", "interview", "status"):
            if admin_cache is None:
                admin_cache = await db.users.find_one({"role": "admin"}, {"_id": 0, "name": 1, "picture": 1}) or {}
            it["actor_name"] = admin_cache.get("name") or "Recruteur"
            it["actor_picture"] = admin_cache.get("picture")
    return {"items": items, "unread": unread}


@api.post("/notifications/read-all")
async def read_all_notifications(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["user_id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}


@api.delete("/notifications/{notif_id}")
async def delete_notification(notif_id: str, user: dict = Depends(get_current_user)):
    await db.notifications.delete_one({"id": notif_id, "user_id": user["user_id"]})
    return {"ok": True}


@api.delete("/notifications")
async def clear_notifications(user: dict = Depends(get_current_user)):
    await db.notifications.delete_many({"user_id": user["user_id"]})
    return {"ok": True}


@api.post("/cron/cleanup-notifications")
async def cron_cleanup_notifications():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    res = await db.notifications.delete_many({"read": True, "created_at": {"$lt": cutoff}})
    return {"ok": True, "deleted": res.deleted_count}


@api.get("/")
async def root():
    return {"message": "Talent Vortex API"}


# ---------------------------------------------------------------------------
# Cron: interview reminders (day before)
# ---------------------------------------------------------------------------
WEBHOOK_CRON_SECRET = os.environ.get("WEBHOOK_CRON_SECRET", "")


async def send_interview_reminders():
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    itws = await db.interviews.find({"date": tomorrow, "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(1000)
    for itw in itws:
        if not itw.get("candidate_id"):
            continue
        cand = await db.users.find_one({"user_id": itw["candidate_id"]}, {"_id": 0})
        if cand and cand.get("email"):
            await send_email(cand["email"], f"Rappel : entretien demain — {itw.get('title','')}",
                             interview_email_html(itw, reminder=True))
        await notify_user(itw["candidate_id"], "interview", "Rappel d'entretien",
                          f"{itw.get('title','Entretien')} demain à {itw.get('time','')}.",
                          {"interview_id": itw["id"]})


@api.post("/cron/interview-reminders")
async def cron_interview_reminders(background: BackgroundTasks, authorization: Optional[str] = Header(None)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    token = (authorization or "").replace("Bearer ", "").strip()
    if not WEBHOOK_CRON_SECRET or not secrets.compare_digest(token, WEBHOOK_CRON_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")
    background.add_task(send_interview_reminders)
    return {"ok": True}


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

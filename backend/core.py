"""Cross-cutting infrastructure: config, db, storage, security, email, notifications."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
import tempfile
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import jwt
import bcrypt
import requests
import httpx
from fastapi import HTTPException, Depends, Header, Query
from motor.motor_asyncio import AsyncIOMotorClient

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
        "cv_file_id": u.get("cv_file_id"),
        "cv_filename": u.get("cv_filename"),
        "picture_file_id": u.get("picture_file_id"),
        "is_super": u.get("is_super", False),
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


async def require_super(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_super"):
        raise HTTPException(status_code=403, detail="Action non autorisee")
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
# Shared AI utility
# ---------------------------------------------------------------------------
def extract_cv_text(data: bytes, filename: str = "") -> str:
    """Extract plain text from a CV file (PDF / DOCX / TXT) for full-text search."""
    import io
    name = (filename or "").lower()
    text = ""
    try:
        if name.endswith(".pdf") or data[:4] == b"%PDF":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        elif name.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
        elif name.endswith(".txt"):
            text = data.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.warning(f"extract_cv_text failed for {filename}: {e}")
    if not text:
        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
    return re.sub(r"[ \t]+", " ", text).strip()[:200000]


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

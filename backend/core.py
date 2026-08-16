"""Cross-cutting infrastructure: config, db, storage, security, email, notifications."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import json
import asyncio
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
        "whatsapp": u.get("whatsapp", ""),
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


# ---------------------------------------------------------------------------
# CV parsing — structured extraction (Gemini vision for PDF/images/text)
# ---------------------------------------------------------------------------
CV_PARSE_SYSTEM = (
    "Tu es un expert en analyse de CV. On te fournit un CV (PDF, image scannee, ou texte). "
    "Extrais TOUTES les informations et reponds UNIQUEMENT par un objet JSON valide, sans texte autour, "
    "au format exact suivant: "
    "{\"full_name\":\"\",\"first_name\":\"\",\"last_name\":\"\",\"email\":\"\",\"phone\":\"\","
    "\"current_position\":\"\",\"years_experience\":0,"
    "\"skills\":[],"
    "\"experiences\":[{\"title\":\"\",\"company\":\"\",\"start\":\"\",\"end\":\"\",\"description\":\"\"}],"
    "\"education\":[{\"degree\":\"\",\"school\":\"\",\"year\":\"\"}],"
    "\"languages\":[],\"summary\":\"\","
    "\"raw_text\":\"<tout le texte lisible du CV, complet>\"}. "
    "Si une information est absente: chaine vide, 0, ou liste vide. "
    "years_experience = nombre ENTIER d'annees d'experience professionnelle (estime si necessaire). "
    "raw_text doit contenir l'INTEGRALITE du texte du CV (fais de l'OCR si c'est une image)."
)


def _cv_mime(filename: str, data: bytes) -> Optional[str]:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        return "application/pdf"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if name.endswith(".webp"):
        return "image/webp"
    return None


async def parse_cv_structured(data: bytes, filename: str = "", content_type: str = "") -> dict:
    """Extract structured CV fields via Gemini (vision for PDF/images, text otherwise)."""
    if not EMERGENT_LLM_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY manquant")
    mime = _cv_mime(filename, data)
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY, session_id=f"cvparse-{uuid.uuid4().hex[:8]}",
        system_message=CV_PARSE_SYSTEM,
    ).with_model("gemini", "gemini-2.5-flash")
    tmp_path = None
    try:
        if mime:
            from emergentintegrations.llm.chat import FileContentWithMimeType
            ext = mime.split("/")[-1]
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            msg = UserMessage(
                text="Analyse ce CV et renvoie le JSON structure demande.",
                file_contents=[FileContentWithMimeType(file_path=tmp_path, mime_type=mime)],
            )
        else:
            txt = extract_cv_text(data, filename)
            if not txt:
                raise ValueError("Aucun texte exploitable dans le CV")
            msg = UserMessage(text="Analyse ce CV et renvoie le JSON structure demande.\n\nCONTENU DU CV:\n" + txt[:60000])
        resp = await chat.send_message(msg)
        raw = (resp if isinstance(resp, str) else getattr(resp, "text", str(resp))) or ""
        raw = raw.strip()
        try:
            obj = json.loads(raw)
        except Exception:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            obj = json.loads(m.group(0)) if m else {}
        return obj if isinstance(obj, dict) else {}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


async def scan_user_cv(user_id: str, force: bool = False) -> dict:
    """Scan one user's CV, extract structured data, persist to cv_data collection."""
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "cv_file_id": 1, "cv_filename": 1})
    if not u or not u.get("cv_file_id"):
        return {"user_id": user_id, "status": "skipped", "reason": "no_cv"}
    cv_file_id = u["cv_file_id"]
    existing = await db.cv_data.find_one({"user_id": user_id})
    if (not force and existing and existing.get("status") == "scanned"
            and existing.get("cv_file_id") == cv_file_id):
        return {"user_id": user_id, "status": "already"}
    f = await db.files.find_one({"id": cv_file_id})
    now = datetime.now(timezone.utc).isoformat()
    if not f:
        await db.cv_data.update_one({"user_id": user_id}, {"$set": {
            "user_id": user_id, "cv_file_id": cv_file_id, "status": "error",
            "error": "Fichier CV introuvable", "scanned_at": now,
        }}, upsert=True)
        await db.users.update_one({"user_id": user_id}, {"$set": {"cv_scanned": False}})
        return {"user_id": user_id, "status": "error", "error": "file_not_found"}
    try:
        data, ct = await asyncio.to_thread(get_object, f["storage_path"])
        structured = await parse_cv_structured(data, f.get("original_filename") or u.get("cv_filename") or "cv.pdf", ct)
        raw_text = (structured.pop("raw_text", "") or "").strip()
        if not raw_text:
            raw_text = extract_cv_text(data, f.get("original_filename") or "cv.pdf")
        doc = {
            "user_id": user_id, "cv_file_id": cv_file_id,
            "cv_filename": f.get("original_filename") or u.get("cv_filename"),
            "raw_text": raw_text[:200000], "structured": structured,
            "status": "scanned", "error": None, "scanned_at": now,
        }
        await db.cv_data.update_one({"user_id": user_id}, {"$set": doc}, upsert=True)
        await db.users.update_one({"user_id": user_id}, {"$set": {
            "cv_scanned": True, "cv_text": raw_text[:200000],
        }})
        return {"user_id": user_id, "status": "scanned"}
    except Exception as e:
        logger.warning(f"scan_user_cv failed for {user_id}: {e}")
        await db.cv_data.update_one({"user_id": user_id}, {"$set": {
            "user_id": user_id, "cv_file_id": cv_file_id, "status": "error",
            "error": str(e)[:500], "scanned_at": now,
        }}, upsert=True)
        await db.users.update_one({"user_id": user_id}, {"$set": {"cv_scanned": False}})
        return {"user_id": user_id, "status": "error", "error": str(e)[:200]}


_scan_lock = {"running": False}


async def scan_all_cvs(force: bool = False) -> dict:
    """Batch-scan every user whose CV is not yet scanned (cv_scanned != True)."""
    if _scan_lock["running"]:
        return {"status": "busy"}
    _scan_lock["running"] = True
    scanned = errors = 0
    try:
        query = {"cv_file_id": {"$exists": True, "$nin": [None, ""]}}
        if not force:
            query["cv_scanned"] = {"$ne": True}
        users = await db.users.find(query, {"_id": 0, "user_id": 1}).to_list(5000)
        sem = asyncio.Semaphore(3)

        async def _one(uid):
            nonlocal scanned, errors
            async with sem:
                r = await scan_user_cv(uid, force=force)
                if r.get("status") == "scanned":
                    scanned += 1
                elif r.get("status") == "error":
                    errors += 1

        await asyncio.gather(*[_one(u["user_id"]) for u in users])
        logger.info(f"scan_all_cvs done: {scanned} scanned / {errors} errors / {len(users)} total")
        return {"status": "done", "scanned": scanned, "errors": errors, "total": len(users)}
    finally:
        _scan_lock["running"] = False


def _deaccent(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower().strip()


async def normalize_nationalities() -> int:
    """Migration douce : convertit les nationalités libres vers la liste standard (adjectif féminin FR)."""
    from data.countries import COUNTRIES
    canon = {}

    def add(key, val):
        k = _deaccent(key)
        if k and k not in canon:
            canon[k] = val

    for _code, name, fem in COUNTRIES:
        add(fem, fem)
        add(name, fem)
        for suf_f, suf_m in (("éenne", "éen"), ("ienne", "ien"), ("aine", "ain"),
                             ("aise", "ais"), ("oise", "ois"), ("ane", "an"),
                             ("ine", "in"), ("elle", "el")):
            if fem.endswith(suf_f):
                add(fem[:-len(suf_f)] + suf_m, fem)
                break
        else:
            if fem.endswith("e"):
                add(fem[:-1], fem)
    valid = set(canon.values())
    users = await db.users.find(
        {"nationality": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "user_id": 1, "nationality": 1},
    ).to_list(20000)
    fixed = 0
    for u in users:
        nat = (u.get("nationality") or "").strip()
        if nat in valid:
            continue
        target = canon.get(_deaccent(nat))
        if target and target != nat:
            await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"nationality": target}})
            fixed += 1
    if fixed:
        logger.info(f"normalize_nationalities: {fixed} nationalité(s) normalisée(s)")
    return fixed

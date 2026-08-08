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
# Pydantic models
# ---------------------------------------------------------------------------
class RegisterInput(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginInput(BaseModel):
    email: EmailStr
    password: str


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
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Cet email est deja utilise")
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
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = create_jwt(user["user_id"], email)
    return {"token": token, "user": public_user(user)}


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
    res = await db.applications.update_one(
        {"id": app_id},
        {"$set": {"status": body.status, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
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
    return {
        "jobs": await db.jobs.count_documents({}),
        "active_jobs": await db.jobs.count_documents({"is_active": True}),
        "candidates": await db.users.count_documents({"role": "candidate"}),
        "applications": await db.applications.count_documents({}),
        "pending": await db.applications.count_documents({"status": "pending"}),
        "accepted": await db.applications.count_documents({"status": "accepted"}),
        "rejected": await db.applications.count_documents({"status": "rejected"}),
    }


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

"""Auth & profile routes."""
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import requests
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, EmailStr

from core import (
    db, logger, APP_NAME, EMERGENT_LLM_KEY, gemini_generate, GEMINI_API_KEY, LlmChat, UserMessage, put_object,
    hash_password, verify_password, create_jwt, public_user,
    get_current_user, send_email, validate_password, ensure_not_locked,
    register_failed, clear_attempts, verify_captcha, reset_email_html,
    extract_cv_text, scan_user_cv, purge_user_data,
)

router = APIRouter()


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


class ForgotInput(BaseModel):
    email: EmailStr
    captcha_id: str
    captcha_answer: str


class ResetInput(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class ProfileInput(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    nationality: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    domains: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    years_experience: Optional[int] = None
    current_position: Optional[str] = None
    headline: Optional[str] = None
    bio: Optional[str] = None


@router.post("/auth/register")
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


@router.post("/auth/login")
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


@router.post("/auth/verify-otp")
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


@router.get("/auth/captcha")
async def get_captcha():
    a = secrets.randbelow(9) + 1
    b = secrets.randbelow(9) + 1
    cid = secrets.token_urlsafe(12)
    await db.captchas.update_one(
        {"cid": cid},
        {"$set": {"cid": cid, "answer_hash": hash_password(str(a + b)),
                  "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}},
        upsert=True,
    )
    return {"captcha_id": cid, "question": f"{a} + {b}"}


@router.post("/auth/refresh")
async def refresh_token(user: dict = Depends(get_current_user)):
    token = create_jwt(user["user_id"], user["email"])
    return {"token": token, "user": public_user(user)}


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotInput):
    await verify_captcha(body.captcha_id, body.captcha_answer)
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if user and user.get("password_hash"):
        code = f"{secrets.randbelow(1000000):06d}"
        await db.password_reset_tokens.update_one(
            {"email": email},
            {"$set": {"email": email, "code_hash": hash_password(code),
                      "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "used": False}},
            upsert=True,
        )
        logger.info(f"Password reset requested for {email}")
        await send_email(email, "Reinitialisation de votre mot de passe Talent Vortex", reset_email_html(code, user.get("name", "")))
    return {"ok": True}


@router.post("/auth/reset-password")
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


@router.post("/auth/google/session")
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


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


async def detect_profile_domains(profile: dict) -> List[str]:
    text = " | ".join(filter(None, [
        profile.get("current_position"),
        profile.get("headline"),
        profile.get("bio"),
        ", ".join(profile.get("domains") or []),
        ", ".join(profile.get("tools") or []),
    ]))
    if not text.strip() or not GEMINI_API_KEY:
        return []
    try:
        raw = await gemini_generate(
            "Tu classes un profil candidat. Reponds UNIQUEMENT par 1 a 3 domaines separes par des virgules, "
            "choisis parmi: Tech, Data, Design, Marketing, Finance, Ressources Humaines, Commercial, "
            "Juridique, Sante, Ingenierie, General. Aucune autre phrase.",
            f"Profil: {text}",
        )
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


@router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    return public_user(user)


@router.put("/profile")
async def update_profile(body: ProfileInput, background: BackgroundTasks, user: dict = Depends(get_current_user)):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    merged = {**user, **upd}
    missing = []
    if not (merged.get("name") or "").strip(): missing.append("nom")
    if not (merged.get("phone") or "").strip(): missing.append("téléphone")
    if not (merged.get("nationality") or "").strip(): missing.append("nationalité")
    if not (merged.get("domains") or []): missing.append("domaine d'expertise")
    if missing:
        raise HTTPException(status_code=400, detail=f"Champs obligatoires manquants : {', '.join(missing)}")
    if upd:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    complete = bool(merged.get("name") and merged.get("phone") and merged.get("nationality") and merged.get("domains") and merged.get("cv_file_id"))
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"profile_completed": complete}})
    background.add_task(refresh_user_domains, user["user_id"])
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return public_user(fresh)


@router.delete("/account")
async def delete_my_account(user: dict = Depends(get_current_user)):
    uid = user["user_id"]
    await db.users.delete_one({"user_id": uid})
    await purge_user_data(uid)
    return {"ok": True}


@router.post("/profile/cv")
async def upload_profile_cv(background: BackgroundTasks, cv: UploadFile = File(...), user: dict = Depends(get_current_user)):
    data = await cv.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 15 Mo)")
    raw_ext = cv.filename.split(".")[-1].lower() if cv.filename and "." in cv.filename else "pdf"
    ext = "".join(c for c in raw_ext if c.isalnum())[:8] or "pdf"
    allowed_ct = {"application/pdf", "application/msword",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if ext not in {"pdf", "doc", "docx"} and (cv.content_type or "") not in allowed_ct:
        raise HTTPException(status_code=400, detail="Format de CV non autorisé (PDF, DOC ou DOCX uniquement).")
    path = f"{APP_NAME}/cv/{user['user_id']}/{uuid.uuid4()}.{ext}"
    put_object(path, data, cv.content_type or "application/pdf")
    file_id = str(uuid.uuid4())
    await db.files.insert_one({
        "id": file_id, "storage_path": path, "original_filename": cv.filename or "cv.pdf",
        "content_type": cv.content_type or "application/pdf", "owner_id": user["user_id"],
        "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    cv_text = extract_cv_text(data, cv.filename or "cv.pdf")
    complete = bool(user.get("name") and user.get("phone") and user.get("nationality") and user.get("domains") and file_id)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {
        "cv_file_id": file_id, "cv_filename": cv.filename or "cv.pdf",
        "cv_text": cv_text, "profile_completed": complete, "cv_scanned": False,
    }})
    background.add_task(scan_user_cv, user["user_id"], True)
    return {"cv_file_id": file_id, "cv_filename": cv.filename or "cv.pdf"}


@router.post("/profile/photo")
async def upload_profile_photo(photo: UploadFile = File(...), user: dict = Depends(get_current_user)):
    data = await photo.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image trop volumineuse (max 8 Mo)")
    ct = photo.content_type or "image/jpeg"
    if not ct.startswith("image/"):
        raise HTTPException(status_code=400, detail="Veuillez sélectionner une image")
    raw_ext = photo.filename.split(".")[-1].lower() if photo.filename and "." in photo.filename else "jpg"
    ext = "".join(c for c in raw_ext if c.isalnum())[:8] or "jpg"
    path = f"{APP_NAME}/photos/{user['user_id']}/{uuid.uuid4()}.{ext}"
    put_object(path, data, ct)
    file_id = str(uuid.uuid4())
    await db.files.insert_one({
        "id": file_id, "storage_path": path, "original_filename": photo.filename or "photo",
        "content_type": ct, "owner_id": user["user_id"], "public": True,
        "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    picture = f"/api/files/public/{file_id}"
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"picture": picture, "picture_file_id": file_id}})
    return {"picture": picture}

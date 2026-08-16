"""Talent Vortex API — application entrypoint. Wires routers and startup."""
import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from core import db, client, logger, init_storage, hash_password, verify_password, normalize_nationalities
from routers import (
    auth, jobs, applications, users, chat, calls, interviews, contracts, misc, cv_scan,
)

app = FastAPI()
api = APIRouter(prefix="/api")

api.include_router(auth.router)
api.include_router(jobs.router)
api.include_router(applications.router)
api.include_router(users.router)
api.include_router(chat.router)
api.include_router(calls.router)
api.include_router(interviews.router)
api.include_router(contracts.router)
api.include_router(misc.router)
api.include_router(cv_scan.router)


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
        await db.users.create_index([
            ("cv_text", "text"), ("name", "text"), ("email", "text"),
            ("current_position", "text"), ("headline", "text"), ("bio", "text"),
            ("domains", "text"), ("tools", "text"), ("nationality", "text"),
            ("city", "text"), ("country", "text"),
        ], name="users_fulltext")
        await db.cv_data.create_index("user_id", unique=True)
        await db.cv_data.create_index("status")
    except Exception as e:
        logger.warning(f"Index warning: {e}")
    try:
        await normalize_nationalities()
    except Exception as e:
        logger.warning(f"normalize_nationalities warning: {e}")
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
    super_email = (os.environ.get("SUPER_ADMIN_EMAIL") or admin_email).lower().strip()
    if super_email:
        await db.users.update_one({"email": super_email}, {"$set": {"is_super": True, "role": "admin"}})


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

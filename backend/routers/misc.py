"""AI assistant, theme, stats, exports, notifications, crons, root."""
import os
import io
import csv
import uuid
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Response, Header, BackgroundTasks
from pydantic import BaseModel

from core import (
    db, logger, EMERGENT_LLM_KEY, LlmChat, UserMessage,
    get_current_user, require_admin, notify_user, send_email, interview_email_html,
)

router = APIRouter()


class AiChatInput(BaseModel):
    session_id: str
    message: str


class ThemeInput(BaseModel):
    primary: str
    primary_foreground: str
    name: Optional[str] = "Personnalise"


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


@router.post("/ai/chat")
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


@router.get("/ai/history")
async def ai_history(session_id: str = Query(...)):
    msgs = await db.ai_messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return msgs


# ---------------------------------------------------------------------------
# Theme settings
# ---------------------------------------------------------------------------
DEFAULT_THEME = {"primary": "220 100% 33%", "primary_foreground": "0 0% 100%", "name": "Bleu Corporate"}


@router.get("/settings/theme")
async def get_theme():
    doc = await db.settings.find_one({"key": "theme"}, {"_id": 0})
    if not doc:
        return DEFAULT_THEME
    return {"primary": doc["primary"], "primary_foreground": doc["primary_foreground"], "name": doc.get("name")}


@router.put("/settings/theme")
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
@router.get("/admin/stats")
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


@router.get("/export/applications")
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


@router.get("/export/contracts")
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


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
@router.get("/notifications")
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


@router.post("/notifications/read-all")
async def read_all_notifications(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["user_id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}


@router.delete("/notifications/{notif_id}")
async def delete_notification(notif_id: str, user: dict = Depends(get_current_user)):
    await db.notifications.delete_one({"id": notif_id, "user_id": user["user_id"]})
    return {"ok": True}


@router.delete("/notifications")
async def clear_notifications(user: dict = Depends(get_current_user)):
    await db.notifications.delete_many({"user_id": user["user_id"]})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Crons
# ---------------------------------------------------------------------------
@router.post("/cron/cleanup-recordings")
async def cleanup_recordings_cron():
    months = int(os.environ.get("RECORDING_RETENTION_MONTHS", "6"))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=months * 30)).isoformat()
    old = await db.recordings.find({"created_at": {"$lt": cutoff}}, {"_id": 0, "id": 1, "video_file_id": 1}).to_list(2000)
    for r in old:
        if r.get("video_file_id"):
            await db.files.update_one({"id": r["video_file_id"]}, {"$set": {"is_deleted": True}})
        await db.recordings.delete_one({"id": r["id"]})
    return {"deleted": len(old)}


@router.post("/cron/cleanup-notifications")
async def cron_cleanup_notifications():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    res = await db.notifications.delete_many({"read": True, "created_at": {"$lt": cutoff}})
    return {"ok": True, "deleted": res.deleted_count}


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


@router.post("/cron/interview-reminders")
async def cron_interview_reminders(background: BackgroundTasks, authorization: Optional[str] = Header(None)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    token = (authorization or "").replace("Bearer ", "").strip()
    if not WEBHOOK_CRON_SECRET or not secrets.compare_digest(token, WEBHOOK_CRON_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")
    background.add_task(send_interview_reminders)
    return {"ok": True}


@router.get("/countries")
async def list_countries():
    from data.countries import COUNTRIES
    return sorted(
        [{"code": c, "name": n, "nationality": d} for c, n, d in COUNTRIES],
        key=lambda x: x["name"],
    )


@router.get("/")
async def root():
    return {"message": "Talent Vortex API"}

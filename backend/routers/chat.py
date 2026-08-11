"""Presence + admin<->candidate chat (polling based)."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from pydantic import BaseModel

from core import (
    db, APP_NAME, get_current_user, require_admin, put_object,
    notify_user, send_email,
)

router = APIRouter()

PRESENCE_WINDOW = 90


class ChatMessageInput(BaseModel):
    text: str
    candidate_id: Optional[str] = None


class ChatEditInput(BaseModel):
    text: str


class TypingInput(BaseModel):
    candidate_id: Optional[str] = None


class ConvActiveInput(BaseModel):
    active: bool


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


@router.post("/presence/ping")
async def presence_ping(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"last_seen": now}})
    return {"ok": True, "last_seen": now}


@router.get("/presence/admin")
async def admin_presence(user: dict = Depends(get_current_user)):
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "last_seen": 1}).to_list(100)
    seens = [a.get("last_seen") for a in admins if a.get("last_seen")]
    return {"online": any(_is_online(s) for s in seens), "last_seen": max(seens) if seens else None}


async def _conv_active(conv_id: str) -> bool:
    doc = await db.conversations.find_one({"conversation_id": conv_id}, {"_id": 0, "active": 1})
    if doc is not None and "active" in doc:
        return bool(doc["active"])
    return (await db.messages.count_documents({"conversation_id": conv_id, "sender_role": "admin"})) > 0


@router.get("/chat/conversations")
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
    seen = set()
    result = []
    for c in convs:
        cid = c["_id"]
        seen.add(cid)
        unread = await db.messages.count_documents({"conversation_id": cid, "sender_role": "candidate", "read": False})
        cand = await db.users.find_one({"user_id": cid}, {"_id": 0, "last_seen": 1, "picture": 1})
        ls = cand.get("last_seen") if cand else None
        result.append({
            "candidate_id": cid, "candidate_name": c.get("candidate_name", ""),
            "last_text": c.get("last_text", ""), "last_at": c.get("last_at"), "unread": unread,
            "last_seen": ls, "online": _is_online(ls), "picture": cand.get("picture") if cand else None,
            "active": await _conv_active(cid),
        })
    # Conversations activées par l'admin mais sans message
    async for d in db.conversations.find({"active": True}, {"_id": 0, "conversation_id": 1}):
        cid = d["conversation_id"]
        if cid in seen:
            continue
        cand = await db.users.find_one({"user_id": cid}, {"_id": 0, "last_seen": 1, "picture": 1, "name": 1})
        if not cand:
            continue
        result.append({
            "candidate_id": cid, "candidate_name": cand.get("name", ""),
            "last_text": "", "last_at": None, "unread": 0,
            "last_seen": cand.get("last_seen"), "online": _is_online(cand.get("last_seen")),
            "picture": cand.get("picture"), "active": True,
        })
    return result


def _invite_email_html(name: str) -> str:
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" style="font-family:Arial,sans-serif">'
        f'<tr><td align="center"><table width="480" cellpadding="0" cellspacing="0" style="background:#f7f7f8;border-radius:12px;padding:32px">'
        f'<tr><td style="font-size:20px;font-weight:bold;color:#111">Talent Vortex</td></tr>'
        f'<tr><td style="padding-top:12px;color:#333">Bonjour {name or ""},<br/><br/>'
        f'Le recruteur vient d\'ouvrir une discussion avec vous. Connectez-vous à votre espace candidat '
        f'et cliquez sur « Messagerie recruteur » depuis votre tableau de bord pour échanger.</td></tr>'
        f'<tr><td style="padding-top:16px;color:#666;font-size:13px">À très vite sur Talent Vortex.</td></tr>'
        f'</table></td></tr></table>'
    )


@router.put("/chat/conversations/{candidate_id}/active")
async def set_conversation_active(candidate_id: str, body: ConvActiveInput, admin: dict = Depends(require_admin)):
    await db.conversations.update_one(
        {"conversation_id": candidate_id},
        {"$set": {"active": body.active, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    if body.active:
        await notify_user(candidate_id, "message", "Messagerie activée",
                          "Le recruteur a ouvert une discussion avec vous.", {"candidate_id": candidate_id})
        cand = await db.users.find_one({"user_id": candidate_id}, {"_id": 0, "email": 1, "name": 1})
        if cand and cand.get("email"):
            await send_email(cand["email"], "Le recruteur souhaite échanger avec vous — Talent Vortex",
                             _invite_email_html(cand.get("name", "")))
    return {"ok": True, "active": body.active}


@router.delete("/chat/conversations/{candidate_id}")
async def delete_conversation(candidate_id: str, admin: dict = Depends(require_admin)):
    await db.messages.delete_many({"conversation_id": candidate_id})
    await db.files.update_many({"conversation_id": candidate_id}, {"$set": {"is_deleted": True}})
    await db.conversations.delete_one({"conversation_id": candidate_id})
    return {"ok": True}


@router.get("/chat/messages")
async def get_messages(candidate_id: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    if user.get("role") == "admin":
        if not candidate_id:
            raise HTTPException(status_code=400, detail="candidate_id requis")
        conv = candidate_id
        other_role = "candidate"
    else:
        conv = user["user_id"]
        other_role = "admin"
    first = await db.messages.find_one(
        {"conversation_id": conv, "sender_role": other_role, "read": False},
        {"_id": 0, "id": 1}, sort=[("created_at", 1)],
    )
    first_unread = first["id"] if first else None
    await db.messages.update_many({"conversation_id": conv, "sender_role": other_role, "read": False}, {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}})
    msgs = await db.messages.find({"conversation_id": conv}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    # Indicateur de frappe : l'autre partie tape si son timestamp est récent (< 6 s)
    other_typing = False
    cdoc = await db.conversations.find_one({"conversation_id": conv}, {"_id": 0})
    if cdoc:
        ts = cdoc.get("typing_candidate_at" if other_role == "candidate" else "typing_admin_at")
        if ts:
            try:
                other_typing = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds() < 6
            except Exception:
                other_typing = False
    return {"messages": msgs, "first_unread": first_unread, "other_typing": other_typing}


@router.post("/chat/typing")
async def chat_typing(body: TypingInput, user: dict = Depends(get_current_user)):
    if user.get("role") == "admin":
        if not body.candidate_id:
            return {"ok": False}
        conv = body.candidate_id
        field = "typing_admin_at"
    else:
        conv = user["user_id"]
        field = "typing_candidate_at"
    await db.conversations.update_one(
        {"conversation_id": conv},
        {"$set": {field: datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True}


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


@router.post("/chat/messages")
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


@router.post("/chat/attachments")
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


@router.put("/chat/messages/{msg_id}")
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


@router.delete("/chat/messages/{msg_id}")
async def delete_message(msg_id: str, user: dict = Depends(get_current_user)):
    msg = await db.messages.find_one({"id": msg_id}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message introuvable")
    if msg.get("sender_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que vos propres messages")
    await db.messages.update_one({"id": msg_id}, {"$set": {"text": "", "attachment": None, "deleted": True}})
    return {"ok": True}


@router.get("/chat/unread")
async def chat_unread(user: dict = Depends(get_current_user)):
    conv = user["user_id"]
    total_admin = await db.messages.count_documents({"conversation_id": conv, "sender_role": "admin"})
    unread = await db.messages.count_documents({"conversation_id": conv, "sender_role": "admin", "read": False})
    active = await _conv_active(conv)
    return {"has_admin": total_admin > 0, "active": active, "unread": unread}

"""CV scanning & structured extraction (admin)."""
from fastapi import APIRouter, Depends, BackgroundTasks, Query

from core import db, require_admin, scan_user_cv, scan_all_cvs, _scan_lock

router = APIRouter()


@router.get("/cv-scan/status")
async def cv_scan_status(admin: dict = Depends(require_admin)):
    total_cv = await db.users.count_documents({"cv_file_id": {"$exists": True, "$nin": [None, ""]}})
    scanned = await db.cv_data.count_documents({"status": "scanned"})
    errors = await db.cv_data.count_documents({"status": "error"})
    pending = max(0, total_cv - scanned)
    return {"total_cv": total_cv, "scanned": scanned, "errors": errors,
            "pending": pending, "running": _scan_lock["running"]}


@router.post("/cv-scan/all")
async def cv_scan_all(background: BackgroundTasks, force: bool = Query(False), admin: dict = Depends(require_admin)):
    if _scan_lock["running"]:
        return {"status": "busy", "message": "Un scan est déjà en cours."}
    background.add_task(scan_all_cvs, force)
    return {"status": "started", "message": "Scan lancé en arrière-plan."}


@router.post("/cv-scan/{user_id}")
async def cv_scan_one(user_id: str, force: bool = Query(True), admin: dict = Depends(require_admin)):
    return await scan_user_cv(user_id, force=force)


@router.get("/cv-scan/{user_id}/data")
async def cv_scan_data(user_id: str, admin: dict = Depends(require_admin)):
    doc = await db.cv_data.find_one({"user_id": user_id}, {"_id": 0})
    return doc or {"status": "pending", "structured": None}

"""One-off backfill: extract text from existing CVs and store on user.cv_text.

Run: python /app/backend/backfill_cv_text.py
"""
import asyncio
from core import db, get_object, extract_cv_text, logger


async def main():
    users = await db.users.find(
        {"cv_file_id": {"$ne": None}},
        {"_id": 0, "user_id": 1, "cv_file_id": 1, "cv_text": 1},
    ).to_list(10000)
    done = skipped = failed = 0
    for u in users:
        if u.get("cv_text"):
            skipped += 1
            continue
        f = await db.files.find_one({"id": u["cv_file_id"]}, {"_id": 0, "storage_path": 1, "original_filename": 1})
        if not f or not f.get("storage_path"):
            failed += 1
            continue
        try:
            data, _ = get_object(f["storage_path"])
            text = extract_cv_text(data, f.get("original_filename") or "cv.pdf")
            await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"cv_text": text}})
            done += 1
        except Exception as e:
            logger.warning(f"backfill cv_text failed for {u['user_id']}: {e}")
            failed += 1
    print(f"backfill done: updated={done} skipped={skipped} failed={failed} total={len(users)}")


if __name__ == "__main__":
    asyncio.run(main())

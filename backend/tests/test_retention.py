"""Retention test: expired raw-audio chunks + temp files are deleted; fresh ones are kept.
Structured data (transcripts/notes) is never touched by cleanup. Cleans up after itself.
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import retention  # noqa: E402
from db import db  # noqa: E402


async def _run():
    old_id = f"rt-old-{uuid.uuid4().hex[:8]}"
    new_id = f"rt-new-{uuid.uuid4().hex[:8]}"
    old_iso = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    new_iso = datetime.now(timezone.utc).isoformat()
    try:
        # Expired upload with raw chunks.
        await db.uploads.insert_one({"id": old_id, "user_id": "rt-user", "created_at": old_iso})
        await db.upload_chunks.insert_many([
            {"upload_id": old_id, "index": 0, "data": b"x"},
            {"upload_id": old_id, "index": 1, "data": b"y"}])
        # Fresh upload that must be kept.
        await db.uploads.insert_one({"id": new_id, "user_id": "rt-user", "created_at": new_iso})
        await db.upload_chunks.insert_one({"upload_id": new_id, "index": 0, "data": b"z"})
        # Expired temp file.
        await db.temp_files.insert_one({"id": "tf-old", "user_id": "rt-user", "created_at": old_iso})
        await db.temp_files.insert_one({"id": "tf-new", "user_id": "rt-user", "created_at": new_iso})

        res = await retention.cleanup_once()

        old_chunks = await db.upload_chunks.count_documents({"upload_id": old_id})
        new_chunks = await db.upload_chunks.count_documents({"upload_id": new_id})
        old_upload = await db.uploads.find_one({"id": old_id})
        old_tf = await db.temp_files.count_documents({"id": "tf-old"})
        new_tf = await db.temp_files.count_documents({"id": "tf-new"})

        assert old_chunks == 0, "expired raw audio chunks must be deleted"
        assert new_chunks == 1, "fresh raw audio must be kept"
        assert old_upload.get("raw_deleted") is True, "expired upload must be marked raw_deleted"
        assert old_tf == 0 and new_tf == 1, "expired temp file deleted, fresh kept"
        print(f"PASS — retention deleted expired raw audio + temp files, kept fresh. counts={res}")
    finally:
        await db.uploads.delete_many({"id": {"$in": [old_id, new_id]}})
        await db.upload_chunks.delete_many({"upload_id": {"$in": [old_id, new_id]}})
        await db.temp_files.delete_many({"id": {"$in": ["tf-old", "tf-new"]}})


def test_retention_deletes_expired_media():
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


if __name__ == "__main__":
    test_retention_deletes_expired_media()

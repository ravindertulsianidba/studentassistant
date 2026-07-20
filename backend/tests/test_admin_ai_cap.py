"""Administrative cost-control authorization tests.

Proves (per spec A):
  - A normal authenticated user CANNOT read the administrative AI cap (HTTP 403).
  - A normal authenticated user CANNOT change the administrative AI cap (HTTP 403).
  - An authorized administrator retains read + write access.
  - The consumer preferences endpoint silently ignores daily_ai_limit (cannot change the cap).
  - Server-side cap ENFORCEMENT remains active (429 when exceeded; 0 = unlimited).

Runs against the modules + DB directly (isolated event loop; no live server / dev-login needed).
"""
import os
import sys
import uuid
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import reliability as rel  # noqa: E402
from db import db  # noqa: E402
from routers import monetization as mroute  # noqa: E402
from routers import planner as proute  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class _FakeReq:
    client = None  # rate_limit falls back to "unknown"


async def _seed_user(email: str) -> str:
    uid = f"captest-{uuid.uuid4().hex[:8]}"
    await db.users.insert_one({"id": uid, "email": email, "email_verified": True})
    return uid


async def _cleanup(uids):
    for uid in uids:
        await db.users.delete_many({"id": uid})
        await db.prefs.delete_many({"user_id": uid})
        await db.ai_usage.delete_many({"user_id": uid})


async def _run():
    admin_email = f"admin.captest+{uuid.uuid4().hex[:6]}@decisivlabs.dev"
    user_email = f"user.captest+{uuid.uuid4().hex[:6]}@example.com"
    admin_uid = await _seed_user(admin_email)
    user_uid = await _seed_user(user_email)
    saved_admins = config.ADMIN_EMAILS
    config.ADMIN_EMAILS = [admin_email.lower()]
    # Clear any admin override so we start from the env default.
    await db.app_config.delete_one({"_id": "ai_cap"})
    try:
        # --- Normal user is FORBIDDEN from reading the admin cap ---
        got_403 = False
        try:
            await mroute.admin_get_ai_cap(uid=user_uid)
        except HTTPException as e:
            got_403 = e.status_code == 403
        assert got_403, "normal user must get 403 reading the admin cap"

        # --- Normal user is FORBIDDEN from changing the admin cap ---
        got_403 = False
        try:
            await mroute.admin_set_ai_cap(mroute.AiCapIn(daily_ai_limit=1), _FakeReq(), uid=user_uid)
        except HTTPException as e:
            got_403 = e.status_code == 403
        assert got_403, "normal user must get 403 changing the admin cap"

        # --- Authorized admin CAN read + write ---
        cap = await mroute.admin_get_ai_cap(uid=admin_uid)
        assert cap["daily_ai_limit"] == config.DEFAULT_DAILY_AI_LIMIT and cap["source"] == "env_default", cap

        r = await mroute.admin_set_ai_cap(mroute.AiCapIn(daily_ai_limit=2), _FakeReq(), uid=admin_uid)
        assert r["ok"] and r["daily_ai_limit"] == 2, r
        cap2 = await mroute.admin_get_ai_cap(uid=admin_uid)
        assert cap2["daily_ai_limit"] == 2 and cap2["source"] == "admin_override", cap2

        # --- get_effective_ai_limit reflects the admin override ---
        assert await rel.get_effective_ai_limit(db) == 2

        # --- Consumer prefs endpoint silently IGNORES daily_ai_limit (cannot change cap) ---
        await proute.write_prefs({"daily_ai_limit": 9999, "morning_time": "08:15"}, uid=user_uid)
        prefs = await db.prefs.find_one({"user_id": user_uid}, {"_id": 0})
        assert prefs.get("morning_time") == "08:15", "legit prefs must still save"
        assert "daily_ai_limit" not in prefs, "daily_ai_limit must never be stored from consumer prefs"
        assert await rel.get_effective_ai_limit(db) == 2, "consumer prefs must not change the admin cap"

        # --- Server-side ENFORCEMENT still works (cap=2 -> 3rd call blocked with 429) ---
        await db.ai_usage.delete_many({"user_id": user_uid})
        await rel.enforce_ai_cap(db, user_uid)   # 1
        await rel.enforce_ai_cap(db, user_uid)   # 2
        blocked = False
        try:
            await rel.enforce_ai_cap(db, user_uid)  # 3 -> over cap
        except HTTPException as e:
            blocked = e.status_code == 429
        assert blocked, "cap enforcement must raise 429 when exceeded"

        # --- 0 = unlimited (no enforcement) ---
        await mroute.admin_set_ai_cap(mroute.AiCapIn(daily_ai_limit=0), _FakeReq(), uid=admin_uid)
        await db.ai_usage.delete_many({"user_id": user_uid})
        for _ in range(5):
            await rel.enforce_ai_cap(db, user_uid)  # must never raise when unlimited

        # --- negative value rejected (400) ---
        bad = False
        try:
            await mroute.admin_set_ai_cap(mroute.AiCapIn(daily_ai_limit=-3), _FakeReq(), uid=admin_uid)
        except HTTPException as e:
            bad = e.status_code == 400
        assert bad, "negative cap must be rejected"

        print("PASS — admin cost-control auth: normal user 403 (read+write), admin retains access, "
              "consumer prefs cannot change cap, server-side enforcement + unlimited work")
    finally:
        config.ADMIN_EMAILS = saved_admins
        await db.app_config.delete_one({"_id": "ai_cap"})
        await db.admin_audit.delete_many({"action": "set_ai_cap"})
        await _cleanup([admin_uid, user_uid])


def test_admin_ai_cap():
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


if __name__ == "__main__":
    test_admin_ai_cap()

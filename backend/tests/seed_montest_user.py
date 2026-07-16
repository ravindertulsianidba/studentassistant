"""Seed a verified test user (known password) for authenticated UI smoke tests + grant Starter Pack."""
import os, sys, uuid, asyncio
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import security  # noqa
import monetization as mon  # noqa
from db import db  # noqa

EMAIL = "montest.user@decisivlabs.dev"
PASSWORD = "StarterPack#2026!"

async def main():
    u = await db.users.find_one({"email": EMAIL})
    if not u:
        uid = str(uuid.uuid4())
        await db.users.insert_one({
            "id": uid, "email": EMAIL, "password_hash": security.hash_password(PASSWORD),
            "name": "Monetization Tester", "email_verified": True, "token_version": 0,
            "auth_provider": "password", "failed_login_count": 0, "lockout_until": None,
            "created_at": datetime.now(timezone.utc).isoformat()})
    else:
        uid = u["id"]
        await db.users.update_one({"id": uid}, {"$set": {
            "password_hash": security.hash_password(PASSWORD), "email_verified": True,
            "failed_login_count": 0, "lockout_until": None}})
    granted = await mon.grant_starter_pack(uid)
    print(f"seeded uid={uid} starter_granted_now={granted} email={EMAIL}")

if __name__ == "__main__":
    asyncio.run(main())

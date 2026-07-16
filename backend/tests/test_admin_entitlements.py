"""Complimentary/admin entitlement tests: verified-only grants, idempotency, source
coexistence (Google Play + admin), revoke/expiry isolation, no fabricated Play records,
and no public grant endpoint. Direct module/DB level (no dev-login). Cleans up after itself.
"""
import os, sys, uuid, asyncio
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import admin_entitlements as adm  # noqa: E402
import monetization as mon  # noqa: E402
from db import db  # noqa: E402


def _now():
    return datetime.now(timezone.utc)


async def _mk_user(verified=True):
    uid = f"cmp-{uuid.uuid4().hex[:8]}"
    email = f"{uid}@decisivlabs.dev"
    await db.users.insert_one({"id": uid, "email": email, "email_verified": verified,
                               "password_hash": "x", "token_version": 0,
                               "created_at": _now().isoformat()})
    return uid, email


async def _grant(uid, email, source="admin_grant", expires=None):
    now = _now().isoformat()
    await db.entitlement_grants.update_one({"user_id": uid, "source": source}, {"$set": {
        "grant_id": str(uuid.uuid4()), "user_id": uid, "email": email, "plan": "premium",
        "source": source, "status": "active", "granted_by": "test", "grant_reason": "t",
        "starts_at": now, "expires_at": expires, "revoked_at": None, "created_at": now,
        "updated_at": now, "usage_cycle_anchor": now}}, upsert=True)


async def _cleanup(uid):
    for c in ["users", "entitlement_grants", "entitlements", "usage_cycles", "purchase_tokens"]:
        await db[c].delete_many({"user_id": uid})
    await db.users.delete_many({"id": uid})


async def _run():
    uid, email = await _mk_user(verified=True)
    vid, vemail = await _mk_user(verified=False)
    try:
        # Verified user gets premium via admin grant.
        await _grant(uid, email)
        ent = await mon.resolve_entitlement(uid)
        assert ent["plan"] == "premium" and ent["source"] == "admin_grant", ent
        assert ent["allowances"]["audio_minutes"] == mon.config.PREMIUM_AUDIO_MINUTES_PER_CYCLE == 240

        # Unverified + unknown rejected by CLI resolver.
        for bad_email in (vemail, "no-such@nowhere.dev"):
            raised = False
            try:
                await adm._resolve_verified_user(bad_email, "test", "grant", "admin_grant")
            except SystemExit:
                raised = True
            assert raised, f"grant to {bad_email} must be rejected"

        # Coexistence: add a Google Play entitlement; revoke admin grant -> still premium via Play.
        await db.entitlements.insert_one({"user_id": uid, "plan": "premium", "state": "active",
            "test_override": True, "billing_anchor": _now().isoformat(), "current_period_end": None})
        await db.entitlement_grants.update_one({"user_id": uid, "source": "admin_grant"},
            {"$set": {"status": "revoked", "revoked_at": _now().isoformat()}})
        ent = await mon.resolve_entitlement(uid)
        assert ent["plan"] == "premium" and ent["source"] == "google_play", ("play survives admin revoke", ent)

        # Expire Google Play -> re-grant admin -> premium via admin (admin survives play expiry).
        await db.entitlements.update_one({"user_id": uid}, {"$set": {"state": "expired"}})
        await _grant(uid, email)
        ent = await mon.resolve_entitlement(uid)
        assert ent["plan"] == "premium" and ent["source"] == "admin_grant", ("admin survives play expiry", ent)

        # Expired admin grant + expired play -> back to Free.
        await db.entitlement_grants.update_one({"user_id": uid, "source": "admin_grant"},
            {"$set": {"expires_at": (_now() - timedelta(days=1)).isoformat()}})
        ent = await mon.resolve_entitlement(uid)
        assert ent["plan"] == "free" and ent["source"] == "free", ("expiry -> free", ent)

        # No fabricated Google Play purchase record created by an admin grant.
        assert await db.purchase_tokens.count_documents({"user_id": uid}) == 0, "no Play token fabricated"

        print("PASS — complimentary: verified-only, coexistence, revoke/expiry isolation, "
              "free fallback, no fabricated Play record")
    finally:
        await _cleanup(uid)
        await _cleanup(vid)


def test_no_public_grant_endpoint():
    # Ensure no route path exposes a grant endpoint publicly.
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "routers"
    for f in root.glob("*.py"):
        txt = f.read_text()
        assert "/entitlement/grant" not in txt and "admin/grant" not in txt, f"public grant route in {f.name}"
    print("PASS — no public grant endpoint exists")


def test_complimentary_entitlement():
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()
    test_no_public_grant_endpoint()


if __name__ == "__main__":
    test_complimentary_entitlement()

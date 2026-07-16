"""VPS-only complimentary/admin Premium entitlement management.

Runs ONLY inside the backend environment (no public HTTP endpoint):
    python -m admin_entitlements <grant|extend|revoke|status|list> [options]

Grants are stored in `entitlement_grants` and coexist independently with Google Play
entitlements (`entitlements`). Effective access is the max of all valid sources
(see monetization.resolve_entitlement). Every action writes an immutable audit event
to `entitlement_audit`. No Google Play purchase token / order / RTDN is ever fabricated.
"""
import os
import sys
import uuid
import asyncio
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import db  # noqa: E402
import monetization as mon  # noqa: E402

VALID_SOURCES = {"admin_grant", "promotional", "internal_test"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(s: str):
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


async def _audit(action: str, user_id: str, source: str, actor: str, reason: str, details: dict = None):
    await db.entitlement_audit.insert_one({
        "audit_id": str(uuid.uuid4()), "action": action, "user_id": user_id,
        "source": source, "granted_by": actor, "reason": reason,
        "details": details or {}, "ts": _now()})


async def _resolve_verified_user(email: str, actor: str, action: str, source: str):
    u = await db.users.find_one({"email": email.strip().lower()}, {"id": 1, "email_verified": 1})
    if not u:
        await _audit(f"{action}_rejected_unknown", email, source, actor, "unknown_email")
        raise SystemExit(f"ERROR: no account found for {email}")
    if not u.get("email_verified"):
        await _audit(f"{action}_rejected_unverified", u["id"], source, actor, "unverified_email")
        raise SystemExit(f"ERROR: account {email} is not email-verified; grant refused")
    return u["id"]


async def cmd_grant(a):
    if a.source not in VALID_SOURCES:
        raise SystemExit(f"ERROR: --source must be one of {sorted(VALID_SOURCES)}")
    if a.plan != "premium":
        raise SystemExit("ERROR: only --plan premium is supported")
    uid = await _resolve_verified_user(a.email, a.by, "grant", a.source)
    expires = None
    if a.expires_at and not a.no_expiry:
        expires = _parse_iso(a.expires_at).isoformat()
    if a.no_expiry:
        expires = None

    existing = await db.entitlement_grants.find_one(
        {"user_id": uid, "source": a.source, "status": "active", "revoked_at": None})
    # Sanitized confirmation.
    print(f"About to grant: email={a.email} user_id={uid} plan=premium source={a.source} "
          f"reason={a.reason} expires_at={expires or 'never'}")
    if existing and existing.get("expires_at") == expires:
        print("Idempotent: identical active grant already exists. No change.")
        await _audit("grant_idempotent", uid, a.source, a.by, a.reason)
        return
    now = _now()
    doc = {
        "grant_id": existing["grant_id"] if existing else str(uuid.uuid4()),
        "user_id": uid, "email": a.email.strip().lower(), "plan": "premium", "source": a.source,
        "status": "active", "granted_by": a.by, "grant_reason": a.reason,
        "starts_at": now, "expires_at": expires, "revoked_at": None,
        "created_at": existing["created_at"] if existing else now, "updated_at": now,
        "usage_cycle_anchor": existing.get("usage_cycle_anchor") if existing else now,
    }
    await db.entitlement_grants.update_one(
        {"user_id": uid, "source": a.source}, {"$set": doc}, upsert=True)
    await _audit("grant" if not existing else "grant_update", uid, a.source, a.by, a.reason,
                 {"expires_at": expires})
    print(f"OK: granted complimentary Premium ({a.source}) to {a.email}. expires_at={expires or 'never'}")


async def cmd_extend(a):
    uid = await _resolve_verified_user(a.email, a.by, "extend", a.source)
    g = await db.entitlement_grants.find_one({"user_id": uid, "source": a.source, "status": "active"})
    if not g:
        raise SystemExit(f"ERROR: no active {a.source} grant for {a.email}")
    expires = _parse_iso(a.expires_at).isoformat()
    await db.entitlement_grants.update_one({"user_id": uid, "source": a.source},
        {"$set": {"expires_at": expires, "updated_at": _now()}})
    await _audit("extend", uid, a.source, a.by, a.reason or "extend", {"expires_at": expires})
    print(f"OK: extended {a.source} grant for {a.email} to {expires}")


async def cmd_revoke(a):
    uid = await _resolve_verified_user(a.email, a.by, "revoke", a.source)
    g = await db.entitlement_grants.find_one({"user_id": uid, "source": a.source, "status": "active"})
    if not g:
        raise SystemExit(f"ERROR: no active {a.source} grant for {a.email}")
    await db.entitlement_grants.update_one({"user_id": uid, "source": a.source},
        {"$set": {"status": "revoked", "revoked_at": _now(), "updated_at": _now()}})
    await _audit("revoke", uid, a.source, a.by, a.reason or "revoked")
    print(f"OK: revoked {a.source} grant for {a.email}. Other entitlement sources are untouched.")


async def cmd_status(a):
    u = await db.users.find_one({"email": a.email.strip().lower()}, {"id": 1, "email_verified": 1})
    if not u:
        raise SystemExit(f"ERROR: no account found for {a.email}")
    grants = await db.entitlement_grants.find({"user_id": u["id"]}, {"_id": 0}).to_list(50)
    ent = await mon.resolve_entitlement(u["id"])
    print(f"email={a.email} user_id={u['id']} verified={u.get('email_verified')}")
    print(f"effective_plan={ent['plan']} state={ent['state']} source={ent['source']} "
          f"cycle_end={ent['cycle_end']}")
    for g in grants:
        print(f"  grant source={g['source']} status={g['status']} expires_at={g.get('expires_at')} "
              f"reason={g.get('grant_reason')}")


async def cmd_list(a):
    q = {"status": "active"}
    if a.source:
        q["source"] = a.source
    grants = await db.entitlement_grants.find(q, {"_id": 0}).to_list(200)
    print(f"active complimentary grants: {len(grants)}")
    for g in grants:
        print(f"  {g.get('email')} source={g['source']} expires_at={g.get('expires_at') or 'never'} "
              f"reason={g.get('grant_reason')} granted_by={g.get('granted_by')}")


def build_parser():
    p = argparse.ArgumentParser(prog="admin_entitlements")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("grant", "extend", "revoke", "status", "list"):
        sp = sub.add_parser(name)
        sp.add_argument("--email")
        sp.add_argument("--plan", default="premium")
        sp.add_argument("--source", default="admin_grant")
        sp.add_argument("--reason", default="")
        sp.add_argument("--expires-at", dest="expires_at", default="")
        sp.add_argument("--no-expiry", dest="no_expiry", action="store_true")
        sp.add_argument("--by", default=os.environ.get("ADMIN_ACTOR", "vps_admin"))
    return p


async def _main(a):
    if a.cmd == "grant":
        await cmd_grant(a)
    elif a.cmd == "extend":
        await cmd_extend(a)
    elif a.cmd == "revoke":
        await cmd_revoke(a)
    elif a.cmd == "status":
        await cmd_status(a)
    elif a.cmd == "list":
        await cmd_list(a)


if __name__ == "__main__":
    args = build_parser().parse_args()
    asyncio.run(_main(args))

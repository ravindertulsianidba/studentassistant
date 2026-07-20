"""Google Play billing verification, entitlement, acknowledgement, lifecycle & reconciliation.

Proves (per spec C/D/E/G) against the modules + DB directly with a MOCKED Google Play API
(no real credentials). Isolated event loop.

Covered:
  - Verified ACTIVE purchase grants Premium; acknowledgement happens ONLY after the grant.
  - PENDING purchase never grants Premium.
  - EXPIRED / ACCOUNT-HOLD do not grant Premium (documented policy).
  - GRACE PERIOD retains Premium (documented policy).
  - Wrong product is rejected (client-supplied product/base plan never trusted).
  - A purchase token cannot be reassigned to another user (409).
  - Duplicate processing is idempotent (single entitlement record).
  - Revoked/voided purchase removes entitlement (idempotent).
  - Reconciliation re-queries Google Play and is idempotent.
  - Missing credentials fail closed (503); provider errors are sanitized (502, generic).
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import monetization as mon  # noqa: E402
from db import db  # noqa: E402
from routers import billing as bmod  # noqa: E402
from fastapi import HTTPException  # noqa: E402

PRODUCT = config.GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _sub(state, product=PRODUCT, ack="ACKNOWLEDGEMENT_STATE_PENDING", base="monthly", days=30):
    now = datetime.now(timezone.utc)
    return {
        "subscriptionState": state,
        "startTime": _iso(now),
        "acknowledgementState": ack,
        "lineItems": [{"productId": product, "expiryTime": _iso(now + timedelta(days=days)),
                       "offerDetails": {"basePlanId": base}}],
    }


async def _cleanup(uids, tokens):
    for uid in uids:
        for c in ["entitlements", "purchase_events", "subscription_audit"]:
            await db[c].delete_many({"user_id": uid})
    for t in tokens:
        await db.purchase_tokens.delete_many({"purchase_token": t})


async def _run():
    uidA = f"buytest-{uuid.uuid4().hex[:8]}"
    uidB = f"buytest-{uuid.uuid4().hex[:8]}"
    tok = f"tok-{uuid.uuid4().hex}"
    tok2 = f"tok-{uuid.uuid4().hex}"

    ack_calls = []

    async def fake_ack(purchase_token, sub):
        # Assert the entitlement was persisted BEFORE acknowledgement (ack only after grant).
        import token_crypto
        ent = await db.entitlements.find_one({"user_id": uidA, "purchase_token_hash": token_crypto.token_hash(purchase_token)})
        ack_calls.append({"token": purchase_token, "ent_exists": bool(ent),
                          "plan": (ent or {}).get("plan")})
        return "acknowledged"

    saved_ack = bmod._maybe_acknowledge
    bmod._maybe_acknowledge = fake_ack
    try:
        # --- ACTIVE -> Premium granted; ack attempted only after grant ---
        ent = await bmod._apply_entitlement(uidA, tok, _sub("SUBSCRIPTION_STATE_ACTIVE"), "verify")
        assert ent["plan"] == "premium" and ent["state"] == "active", ent
        assert ent["base_plan"] == "monthly" and ent["product_id"] == PRODUCT
        assert ent["purchase_token_hash"] and ent["purchase_token_hash"] != tok, "token must be hashed"
        resolved = await mon.resolve_entitlement(uidA)
        assert resolved["plan"] == "premium", resolved
        assert len(ack_calls) == 1 and ack_calls[0]["ent_exists"] and ack_calls[0]["plan"] == "premium", ack_calls

        # --- Duplicate processing is idempotent (single entitlement doc) ---
        await bmod._apply_entitlement(uidA, tok, _sub("SUBSCRIPTION_STATE_ACTIVE"), "verify")
        assert await db.entitlements.count_documents({"user_id": uidA}) == 1

        # --- Token cannot be reassigned to another user ---
        reassigned_blocked = False
        try:
            await bmod._apply_entitlement(uidB, tok, _sub("SUBSCRIPTION_STATE_ACTIVE"), "verify")
        except HTTPException as e:
            reassigned_blocked = e.status_code == 409
        assert reassigned_blocked, "token reassignment must be rejected (409)"

        # --- Wrong product rejected; client-supplied product/base plan never trusted ---
        wrong_product_blocked = False
        try:
            await bmod._apply_entitlement(uidB, tok2, _sub("SUBSCRIPTION_STATE_ACTIVE", product="other.product"), "verify")
        except HTTPException as e:
            wrong_product_blocked = e.status_code == 409
        assert wrong_product_blocked, "wrong product must be rejected"
        assert await db.entitlements.count_documents({"user_id": uidB}) == 0, "nothing persisted on mismatch"

        # --- GRACE PERIOD retains Premium ---
        ack_calls.clear()
        ent = await bmod._apply_entitlement(uidA, tok, _sub("SUBSCRIPTION_STATE_IN_GRACE_PERIOD"), "rtdn")
        assert ent["plan"] == "premium" and ent["state"] == "grace_period", ent

        # --- ACCOUNT HOLD removes Premium (documented policy) ---
        ent = await bmod._apply_entitlement(uidA, tok, _sub("SUBSCRIPTION_STATE_ON_HOLD"), "rtdn")
        assert ent["plan"] == "free" and ent["state"] == "account_hold", ent
        assert (await mon.resolve_entitlement(uidA))["plan"] == "free"

        # --- CANCELED but unexpired keeps Premium until period end ---
        ent = await bmod._apply_entitlement(uidA, tok, _sub("SUBSCRIPTION_STATE_CANCELED"), "rtdn")
        assert ent["plan"] == "premium" and ent["state"] == "cancelled_active_until_period_end", ent
        assert ent["auto_renewing"] is False

        # --- EXPIRED -> Free ---
        ent = await bmod._apply_entitlement(uidA, tok, _sub("SUBSCRIPTION_STATE_EXPIRED"), "rtdn")
        assert ent["plan"] == "free" and ent["state"] == "expired", ent

        # --- Reactivate then REVOKE (voided) removes entitlement; idempotent ---
        await bmod._apply_entitlement(uidA, tok, _sub("SUBSCRIPTION_STATE_ACTIVE"), "verify")
        assert (await mon.resolve_entitlement(uidA))["plan"] == "premium"
        await bmod._revoke_entitlement(uidA, tok, "rtdn_voided")
        await bmod._revoke_entitlement(uidA, tok, "rtdn_voided")  # idempotent
        rev = await db.entitlements.find_one({"user_id": uidA})
        assert rev["plan"] == "free" and rev["state"] == "revoked", rev
        assert (await mon.resolve_entitlement(uidA))["plan"] == "free"

        # --- PENDING never grants Premium (fresh user + token, ack NOT attempted) ---
        uidC = f"buytest-{uuid.uuid4().hex[:8]}"
        tokC = f"tok-{uuid.uuid4().hex}"
        ack_calls.clear()

        async def fake_ack_c(purchase_token, sub):
            ack_calls.append(purchase_token)
            return "acknowledged"
        bmod._maybe_acknowledge = fake_ack_c
        entc = await bmod._apply_entitlement(uidC, tokC, _sub("SUBSCRIPTION_STATE_PENDING"), "verify")
        assert entc["plan"] == "free" and entc["state"] == "pending", entc
        assert (await mon.resolve_entitlement(uidC))["plan"] == "free"
        assert len(ack_calls) == 0, "pending purchases must not be acknowledged"
        await _cleanup([uidC], [tokC])

        # --- Reconciliation re-queries Google Play; idempotent ---
        recon_tokens = []

        async def fake_verify(token):
            recon_tokens.append(token)
            return _sub("SUBSCRIPTION_STATE_ACTIVE")
        saved_verify = bmod._play_verify_token
        bmod._play_verify_token = fake_verify
        try:
            await bmod._apply_entitlement(uidA, tok, _sub("SUBSCRIPTION_STATE_ACTIVE"), "verify")
            r1 = await bmod.reconcile_once()
            r2 = await bmod.reconcile_once()
            assert r1.get("checked", 0) >= 1 and len(recon_tokens) >= 1, r1
            assert await db.entitlements.count_documents({"user_id": uidA}) == 1, "reconcile must not duplicate"
            assert r2 is not None
        finally:
            bmod._play_verify_token = saved_verify

        print("PASS — billing: active grants+ack-after-grant, pending/expired/hold no grant, "
              "grace/cancel retain, wrong-product+reassign rejected, revoke removes, reconcile idempotent")
    finally:
        bmod._maybe_acknowledge = saved_ack
        await _cleanup([uidA, uidB], [tok, tok2])


async def _run_failclosed():
    """Missing credentials fail closed (503); provider errors are sanitized (502, generic)."""
    saved_client = bmod._play_client
    # No credentials -> _play_client returns None -> 503, never a grant.
    bmod._play_client = lambda: None
    got_503 = False
    try:
        await bmod._play_verify_token("sometoken")
    except HTTPException as e:
        got_503 = e.status_code == 503
    assert got_503, "missing credentials must fail closed (503)"

    class _BadClient:
        def purchases(self):
            raise RuntimeError("raw google internal error with secret-ish detail")
    bmod._play_client = lambda: _BadClient()
    sanitized = False
    try:
        await bmod._play_verify_token("sometoken")
    except HTTPException as e:
        sanitized = (e.status_code == 502 and "raw google" not in str(e.detail).lower()
                     and "secret" not in str(e.detail).lower())
    assert sanitized, "provider errors must be sanitized (502, generic message)"
    bmod._play_client = saved_client
    print("PASS — billing fail-closed: 503 without credentials, 502 sanitized on provider error")


async def _run_encryption():
    """Purchase tokens are encrypted at rest; hash used for ownership; missing key fails closed."""
    import token_crypto
    uid = f"enctest-{uuid.uuid4().hex[:8]}"
    tok = f"tok-{uuid.uuid4().hex}"
    saved_ack = bmod._maybe_acknowledge

    async def fake_ack(purchase_token, sub):
        return "already_acknowledged"
    bmod._maybe_acknowledge = fake_ack
    try:
        await bmod._apply_entitlement(uid, tok, _sub("SUBSCRIPTION_STATE_ACTIVE"), "verify")

        ent = await db.entitlements.find_one({"user_id": uid})
        pt = await db.purchase_tokens.find_one({"purchase_token_hash": token_crypto.token_hash(tok)})
        # DB records must NOT contain the raw token in any plaintext field.
        assert "purchase_token" not in ent, "entitlements must not store raw token"
        assert "purchase_token" not in pt, "purchase_tokens must not store raw token"
        assert ent.get("encrypted_purchase_token"), "entitlements must store encrypted token"
        assert pt.get("encrypted_purchase_token"), "purchase_tokens must store encrypted token"
        # Encrypted token differs from plaintext; decryption restores it.
        assert ent["encrypted_purchase_token"] != tok, "ciphertext must differ from plaintext"
        assert token_crypto.decrypt_token(ent["encrypted_purchase_token"]) == tok, "decrypt restores token"
        # Ownership/replay checks use the hash.
        assert ent["purchase_token_hash"] == token_crypto.token_hash(tok)
        assert pt["purchase_token_hash"] == token_crypto.token_hash(tok)

        # RTDN ownership lookup (by hash) + reconcile (decrypts) still work.
        recon_tokens = []

        async def fake_verify(t):
            recon_tokens.append(t)
            return _sub("SUBSCRIPTION_STATE_ACTIVE")
        saved_verify = bmod._play_verify_token
        bmod._play_verify_token = fake_verify
        try:
            r = await bmod.reconcile_once()
            assert r.get("reconciled", 0) >= 1, r
            assert tok in recon_tokens, "reconcile must decrypt and re-query the real token"
        finally:
            bmod._play_verify_token = saved_verify

        # Missing encryption key fails closed (503), never stores plaintext / grants.
        uid2 = f"enctest-{uuid.uuid4().hex[:8]}"
        tok2 = f"tok-{uuid.uuid4().hex}"
        saved_key = os.environ.get("GOOGLE_PLAY_TOKEN_ENCRYPTION_KEY", "")
        os.environ["GOOGLE_PLAY_TOKEN_ENCRYPTION_KEY"] = ""
        try:
            failed_closed = False
            try:
                await bmod._apply_entitlement(uid2, tok2, _sub("SUBSCRIPTION_STATE_ACTIVE"), "verify")
            except HTTPException as e:
                failed_closed = e.status_code == 503
            assert failed_closed, "missing encryption key must fail closed (503)"
            assert await db.entitlements.count_documents({"user_id": uid2}) == 0, "no record without encryption"
        finally:
            os.environ["GOOGLE_PLAY_TOKEN_ENCRYPTION_KEY"] = saved_key
        await _cleanup([uid2], [tok2])

        print("PASS — token encryption: no plaintext at rest, ciphertext!=plaintext, decrypt restores, "
              "hash-based ownership, reconcile decrypts, missing key fails closed")
    finally:
        bmod._maybe_acknowledge = saved_ack
        await _cleanup([uid], [tok])


def test_billing_verify():
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
        loop.run_until_complete(_run_failclosed())
        loop.run_until_complete(_run_encryption())
    finally:
        loop.close()


if __name__ == "__main__":
    test_billing_verify()

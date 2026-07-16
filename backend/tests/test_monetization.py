"""Monetization core tests: entitlements, Starter Pack, usage metering (transactional +
concurrency-safe), refunds, premium cycles and cost projection. Runs against the module +
DB directly (no dev-login needed). Uses throwaway user ids and cleans up after itself.
"""
import os
import sys
import uuid
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import monetization as mon  # noqa: E402
from db import db  # noqa: E402


async def _cleanup(uid):
    for c in ["usage_cycles", "entitlements", "cost_ledger", "usage_ledger", "monetization_alerts"]:
        await db[c].delete_many({"user_id": uid})


async def _run():
    uid = f"montest-{uuid.uuid4().hex[:8]}"
    await _cleanup(uid)
    try:
        # --- Free defaults to Starter Pack, non-renewing (no cycle window) ---
        ent = await mon.resolve_entitlement(uid)
        assert ent["plan"] == "free" and ent["cycle_type"] == "starter", ent
        assert ent["allowances"]["memory_question"] == mon.config.FREE_STARTER_MEMORY_QUESTIONS

        # --- Starter Pack granted exactly once ---
        assert await mon.grant_starter_pack(uid) is True
        assert await mon.grant_starter_pack(uid) is False, "Starter Pack must grant only once"

        # --- Reserve decrements; failed op refunded; exhaustion raises 402 ---
        allow = mon.free_allowances()["memory_question"]  # 5
        h = await mon.reserve(uid, "memory_question", 1)
        await mon.refund(h)  # simulate failed op -> should NOT consume
        st = await mon.get_usage_status(uid)
        assert st["features"]["memory_question"]["used"] == 0, st["features"]["memory_question"]

        handles = []
        for _ in range(allow):
            handles.append(await mon.reserve(uid, "memory_question", 1))
        # Next reserve must be blocked with structured detail.
        blocked = False
        try:
            await mon.reserve(uid, "memory_question", 1)
        except mon.UsageBlocked as e:
            blocked = True
            d = e.detail
            assert d["error"] == "limit_reached" and d["allowance"] == allow, d
            assert d["consumed"] == allow and "reset_date" in d, d
        assert blocked, "Exhausted allowance must raise UsageBlocked"

        # Previously created data (usage doc) still present after limit reached.
        st2 = await mon.get_usage_status(uid)
        assert st2["features"]["memory_question"]["remaining"] == 0

        # --- Concurrency: cannot exceed allowance under parallel reserves ---
        uid2 = f"montest-{uuid.uuid4().hex[:8]}"
        await _cleanup(uid2)
        await mon.grant_starter_pack(uid2)
        n = mon.free_allowances()["ai_import"]  # 2
        results = await asyncio.gather(
            *[mon.reserve(uid2, "ai_import", 1) for _ in range(n + 4)],
            return_exceptions=True)
        ok = sum(1 for r in results if isinstance(r, dict))
        blocked_n = sum(1 for r in results if isinstance(r, mon.UsageBlocked))
        assert ok == n, f"concurrent reserves granted {ok}, expected {n}"
        assert blocked_n == 4, f"expected 4 blocked, got {blocked_n}"
        await _cleanup(uid2)

        # --- Premium via test_override: premium allowances + 30-day cycle window ---
        uid3 = f"montest-{uuid.uuid4().hex[:8]}"
        await _cleanup(uid3)
        from datetime import datetime, timezone
        await db.entitlements.insert_one({
            "user_id": uid3, "plan": "premium", "state": "active",
            "test_override": True, "billing_anchor": datetime.now(timezone.utc).isoformat(),
            "current_period_end": None})
        pe = await mon.resolve_entitlement(uid3)
        assert pe["plan"] == "premium" and pe["cycle_type"] == "premium", pe
        assert pe["allowances"]["audio_minutes"] == mon.config.PREMIUM_AUDIO_MINUTES_PER_CYCLE
        assert pe["cycle_start"] and pe["cycle_end"], "premium cycle window must be set"
        # Cancelled retains access until period end.
        await db.entitlements.update_one({"user_id": uid3},
            {"$set": {"state": "cancelled_active_until_period_end"}})
        pe2 = await mon.resolve_entitlement(uid3)
        assert pe2["plan"] == "premium" and pe2["renews"] is False, pe2
        await _cleanup(uid3)

        # --- Cost projection sane + starter within alert ---
        proj = mon.project_costs()
        assert proj["starter_within_alert"] is True, proj
        assert proj["full_quota_premium_usd"] > 0 and proj["typical_premium_usd"] > 0

        print("PASS — monetization core: starter once, transactional+concurrent limits, "
              "refund, premium cycle, cancel-retains, cost projection")
        print(f"  full_quota_premium=${proj['full_quota_premium_usd']} "
              f"typical=${proj['typical_premium_usd']} starter=${proj['starter_pack_full_usd']} "
              f"annual_ratio={proj['full_quota_ratio_annual']} flag>35%={proj['flag_full_quota_over_35pct_annual']}")
    finally:
        await _cleanup(uid)


def test_monetization_core():
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()


if __name__ == "__main__":
    test_monetization_core()

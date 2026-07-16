"""E2E monetization tests against the public preview URL using the seeded montest user.
Covers billing.status, usage.status, plan.config, metering enforcement (import + memory),
billing.google.verify=503, monetization events, admin 403 for non-admins, and regression.

Prerequisite: run `python backend/tests/seed_montest_user.py` and then delete the user's
usage_cycles doc to reset allowances before running this suite.
"""
import os
import sys
import uuid
import time
import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = os.environ.get(
    "EXPO_BACKEND_URL",
    os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://semester-sync-7.preview.emergentagent.com"),
).rstrip("/")

EMAIL = "montest.user@decisivlabs.dev"
PASSWORD = "StarterPack#2026!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    tok = body.get("token") or body.get("access_token")
    assert tok, f"no token in response: {body}"
    return tok


@pytest.fixture(scope="module")
def hdrs(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def reset_usage_before_all():
    """Reset usage counters (delete usage_cycles doc) so the Starter Pack allowances are
    fresh for this test module. Also purge any lingering entitlement."""
    import asyncio
    from db import db as _db
    import monetization as _mon

    async def _reset():
        u = await _db.users.find_one({"email": EMAIL}, {"id": 1})
        assert u, "montest user must be seeded first"
        uid = u["id"]
        await _db.usage_cycles.delete_many({"user_id": uid})
        await _db.entitlements.delete_many({"user_id": uid})
        await _db.imports.delete_many({"user_id": uid})
        await _db.source_docs.delete_many({"user_id": uid})
        await _db.chunks.delete_many({"user_id": uid})
        await _db.review.delete_many({"user_id": uid})
        await _mon.grant_starter_pack(uid)
        return uid

    uid = asyncio.new_event_loop().run_until_complete(_reset())
    print(f"[reset] uid={uid} usage/entitlements/imports/chunks/review purged and Starter Pack re-granted")
    yield


# -------------------- Test group 1: read-only status endpoints --------------------
class TestStatusEndpoints:
    def test_billing_status_shape_free(self, hdrs):
        r = requests.get(f"{BASE_URL}/api/billing/status", headers=hdrs, timeout=20)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["plan"] == "free", b
        assert b["state"] == "free", b
        assert b["billing_enabled"] is False
        # Feature map (per spec: audio_minutes, ai_import, import_pages, memory_question, ai_briefing)
        for key in ("audio_minutes", "ai_import", "import_pages", "memory_question", "ai_briefing"):
            assert key in b["features"], f"missing feature bucket: {key}"
            f = b["features"][key]
            for sub in ("used", "allowance", "remaining", "pct"):
                assert sub in f, f"feature {key} missing {sub}"
        # Product block present
        assert "product" in b and b["product"]["product_id"], b.get("product")

    def test_usage_status_matches_billing_shape(self, hdrs):
        r = requests.get(f"{BASE_URL}/api/usage/status", headers=hdrs, timeout=20)
        assert r.status_code == 200, r.text
        b = r.json()
        for key in ("audio_minutes", "ai_import", "import_pages", "memory_question", "ai_briefing"):
            assert key in b["features"], f"missing bucket {key}"
            assert set(b["features"][key].keys()) >= {"used", "allowance", "remaining", "pct"}

    def test_plan_config(self, hdrs):
        r = requests.get(f"{BASE_URL}/api/plan/config", headers=hdrs, timeout=20)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["billing_enabled"] is False
        assert isinstance(b["free_starter"], dict) and b["free_starter"]
        assert isinstance(b["premium"], dict) and b["premium"]
        # Spec allowances
        assert b["free_starter"]["ai_import"] == 2
        assert b["free_starter"]["memory_question"] == 5
        assert b["premium"]["audio_minutes"] == 300
        assert b["premium"]["memory_question"] == 100


# -------------------- Test group 2: billing verify + monetization events --------------------
class TestBillingVerify:
    def test_verify_returns_503_when_billing_disabled(self, hdrs):
        r = requests.post(f"{BASE_URL}/api/billing/google/verify",
                          headers=hdrs, json={"purchase_token": "fake_token"}, timeout=20)
        assert r.status_code == 503, f"expected 503 got {r.status_code}: {r.text}"

    def test_verify_never_grants_premium(self, hdrs):
        # After the failed verify, plan must still be free.
        r = requests.get(f"{BASE_URL}/api/billing/status", headers=hdrs, timeout=20)
        assert r.status_code == 200
        assert r.json()["plan"] == "free"


class TestMonetizationEvent:
    def test_valid_kind_ok(self, hdrs):
        r = requests.post(f"{BASE_URL}/api/monetization/event",
                          headers=hdrs, json={"kind": "paywall_impression"}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_unknown_kind_400(self, hdrs):
        r = requests.post(f"{BASE_URL}/api/monetization/event",
                          headers=hdrs, json={"kind": "bogus_kind_xyz"}, timeout=20)
        assert r.status_code == 400, r.text


class TestAdminGating:
    def test_admin_monetization_forbidden(self, hdrs):
        r = requests.get(f"{BASE_URL}/api/admin/monetization", headers=hdrs, timeout=20)
        assert r.status_code == 403, r.text

    def test_admin_cost_projection_forbidden(self, hdrs):
        r = requests.get(f"{BASE_URL}/api/admin/cost-projection", headers=hdrs, timeout=20)
        assert r.status_code == 403, r.text


# -------------------- Test group 3: metering enforcement (uses OpenAI) --------------------
class TestImportMetering:
    """Consume 2 imports; 3rd must be blocked with a structured 402 detail."""

    def test_import_1_consumes(self, hdrs):
        r = requests.post(f"{BASE_URL}/api/import", headers=hdrs, timeout=90, json={
            "text": "Course: MATH 101 lecture on integrals. Reading: chapter 4 due Friday Feb 12 2026.",
            "kind": "syllabus", "filename": "test1.txt",
        })
        assert r.status_code == 200, f"import1 failed: {r.status_code} {r.text}"
        # Verify consumption
        s = requests.get(f"{BASE_URL}/api/usage/status", headers=hdrs, timeout=20).json()
        assert s["features"]["ai_import"]["used"] == 1, s["features"]["ai_import"]
        assert s["features"]["import_pages"]["used"] == 1, s["features"]["import_pages"]

    def test_import_2_consumes(self, hdrs):
        r = requests.post(f"{BASE_URL}/api/import", headers=hdrs, timeout=90, json={
            "text": "History HIST 210. Midterm essay due March 3 2026 on the Cold War.",
            "kind": "assignment", "filename": "test2.txt",
        })
        assert r.status_code == 200, f"import2 failed: {r.status_code} {r.text}"
        s = requests.get(f"{BASE_URL}/api/usage/status", headers=hdrs, timeout=20).json()
        assert s["features"]["ai_import"]["used"] == 2

    def test_import_3_blocked_with_structured_402(self, hdrs):
        r = requests.post(f"{BASE_URL}/api/import", headers=hdrs, timeout=30, json={
            "text": "This third import must be rejected because Starter Pack allowance = 2.",
            "kind": "document", "filename": "test3.txt",
        })
        assert r.status_code == 402, f"expected 402 got {r.status_code}: {r.text}"
        body = r.json()
        det = body.get("detail") if isinstance(body, dict) else None
        assert det, f"missing detail: {body}"
        assert det.get("error") == "limit_reached", det
        assert det.get("feature") == "ai_import", det
        assert det.get("consumed") == 2, det
        assert det.get("allowance") == 2, det
        assert "reset_date" in det


class TestMemoryQuestionMetering:
    """After 5 grounded /search answers, the 6th must 402. An empty-grounding query
    should NOT 402 (returns early without consuming)."""

    def test_search_no_grounding_returns_early_no_consume(self, hdrs):
        # First measure current memory_question usage
        s0 = requests.get(f"{BASE_URL}/api/usage/status", headers=hdrs, timeout=20).json()
        used_before = s0["features"]["memory_question"]["used"]
        r = requests.post(f"{BASE_URL}/api/search", headers=hdrs, timeout=30,
                          json={"query": "zzznobodycaresxyz42 gibberish nonexistent term"})
        # Should not 402; either 200 with an empty citations early-return OR 200 with citations if it matches
        assert r.status_code == 200, r.text
        s1 = requests.get(f"{BASE_URL}/api/usage/status", headers=hdrs, timeout=20).json()
        used_after = s1["features"]["memory_question"]["used"]
        # If the answer had no citations, memory_question must NOT have been consumed
        if r.json().get("citations") == []:
            assert used_after == used_before, f"empty-grounding search wrongly consumed: {used_before}->{used_after}"

    def test_search_grounded_meters_and_exhausts(self, hdrs):
        """Fire grounded queries until either the allowance is exhausted (402) or all
        5 memory questions are consumed. Verify usage counter reaches allowance."""
        s0 = requests.get(f"{BASE_URL}/api/usage/status", headers=hdrs, timeout=20).json()
        used_before = int(s0["features"]["memory_question"]["used"])
        allowance = int(s0["features"]["memory_question"]["allowance"])
        remaining = max(0, allowance - used_before)
        queries = [
            "When is the reading for chapter 4 due?",
            "What course covers integrals?",
            "When is the History midterm essay due?",
            "What is HIST 210 about?",
            "Which class discusses the Cold War?",
            "Tell me about the MATH 101 lecture on integrals.",
            "Give a summary of my history midterm.",
        ]
        ok_count = 0
        for i, q in enumerate(queries[:remaining], 1):
            r = requests.post(f"{BASE_URL}/api/search", headers=hdrs, timeout=60, json={"query": q})
            assert r.status_code == 200, f"grounded search #{i} unexpectedly failed: {r.status_code} {r.text}"
            ok_count += 1
        s1 = requests.get(f"{BASE_URL}/api/usage/status", headers=hdrs, timeout=20).json()
        # Used should have advanced by the number of successful grounded calls
        assert s1["features"]["memory_question"]["used"] == used_before + ok_count, s1["features"]["memory_question"]
        # And after burning `remaining`, the bucket should be at allowance
        assert s1["features"]["memory_question"]["used"] == allowance, s1["features"]["memory_question"]

    def test_search_6_blocked_402(self, hdrs):
        r = requests.post(f"{BASE_URL}/api/search", headers=hdrs, timeout=30,
                          json={"query": "Cold War Cold War Cold War Cold War Cold War"})
        assert r.status_code == 402, f"expected 402 got {r.status_code}: {r.text}"
        det = r.json().get("detail", {})
        assert det.get("error") == "limit_reached", det
        assert det.get("feature") == "memory_question", det


# -------------------- Test group 4: regression + read after limits --------------------
class TestRegressionAfterLimits:
    def test_tasks_get_200(self, hdrs):
        r = requests.get(f"{BASE_URL}/api/tasks", headers=hdrs, timeout=20)
        assert r.status_code == 200, r.text

    def test_events_get_200(self, hdrs):
        r = requests.get(f"{BASE_URL}/api/events", headers=hdrs, timeout=20)
        assert r.status_code == 200, r.text

    def test_briefing_get_200(self, hdrs):
        r = requests.get(f"{BASE_URL}/api/briefing", headers=hdrs, timeout=20)
        assert r.status_code == 200, r.text

    def test_review_get_200(self, hdrs):
        r = requests.get(f"{BASE_URL}/api/review", headers=hdrs, timeout=20)
        assert r.status_code == 200, r.text

    def test_manual_task_create_not_blocked_by_paywall(self, hdrs):
        payload = {"title": f"TEST_manual_task_{uuid.uuid4().hex[:6]}", "kind": "task"}
        r = requests.post(f"{BASE_URL}/api/tasks", headers=hdrs, json=payload, timeout=20)
        # Manual task creation must succeed even after AI limits are reached
        assert r.status_code in (200, 201), f"manual task create blocked: {r.status_code} {r.text}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))

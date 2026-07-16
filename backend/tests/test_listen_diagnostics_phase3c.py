"""Phase 3C — Active Listening + Diagnostics backend tests.

Runs against the public preview URL from frontend/.env.
Uses /api/auth/dev-login for tokens (ALLOW_INSECURE_DEV=true).
"""
import os
import uuid
import time
import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set in frontend/.env"

TIMEOUT = 30


def _client(email_prefix="TEST_p3c"):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/dev-login", json={"email": email}, timeout=TIMEOUT)
    if r.status_code == 429:
        pytest.skip("rate limited on dev-login")
    r.raise_for_status()
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return s, email


@pytest.fixture(scope="module")
def api():
    s, email = _client()
    yield s
    # No teardown needed; dev accounts are throwaway.


@pytest.fixture(scope="module")
def api_b():
    s, email = _client("TEST_p3c_b")
    yield s


# ----------------------------- Active Listening -----------------------------

class TestActiveListening:
    def test_start_returns_listening_and_active_matches(self, api):
        r = api.post(f"{BASE_URL}/api/listen/start", json={"course": "CS101"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["status"] == "listening"
        assert s.get("course") == "CS101"
        assert s.get("id")
        pytest.session_id_1 = s["id"]

        r2 = api.get(f"{BASE_URL}/api/listen/active", timeout=TIMEOUT)
        assert r2.status_code == 200
        active = r2.json()
        assert active.get("id") == s["id"]
        assert active.get("status") == "listening"

    def test_start_again_returns_same_session(self, api):
        r = api.post(f"{BASE_URL}/api/listen/start", json={"course": "OTHER"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("id") == pytest.session_id_1
        # Course must NOT change since it's the same active session
        assert r.json().get("course") == "CS101"

    def test_pause_and_resume(self, api):
        sid = pytest.session_id_1
        r = api.post(f"{BASE_URL}/api/listen/{sid}/pause", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("status") == "paused"

        r = api.post(f"{BASE_URL}/api/listen/{sid}/resume", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("status") == "listening"

    def test_append_accumulates_transcript(self, api):
        sid = pytest.session_id_1
        r1 = api.post(f"{BASE_URL}/api/listen/{sid}/append",
                      json={"text": "Hello class."}, timeout=TIMEOUT)
        assert r1.status_code == 200 and r1.json().get("ok") is True
        r2 = api.post(f"{BASE_URL}/api/listen/{sid}/append",
                      json={"text": "Second sentence."}, timeout=TIMEOUT)
        assert r2.status_code == 200
        # Fetch session and verify accumulation
        r3 = api.get(f"{BASE_URL}/api/listen/{sid}", timeout=TIMEOUT)
        assert r3.status_code == 200
        tx = r3.json().get("transcript", "")
        assert "Hello class." in tx
        assert "Second sentence." in tx

    def test_stop_with_real_transcript_produces_items(self, api):
        # Baseline inbox count
        r0 = api.get(f"{BASE_URL}/api/review", timeout=TIMEOUT)
        assert r0.status_code == 200
        pytest.baseline_review_count = len(r0.json())

        sid = pytest.session_id_1
        transcript = (
            "Alright everyone, our next Physics assignment is due next Friday at 11:59 PM. "
            "Also, the midterm exam will be held on March 15th at 10 AM in Hall 2. "
            "Don't forget to submit your lab report by Wednesday."
        )
        r = api.post(f"{BASE_URL}/api/listen/{sid}/stop",
                     json={"transcript": transcript}, timeout=120)
        # AI cap could hit; still expect 200 with ai_error string
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "done"
        assert body.get("summary") is not None
        summary = body["summary"]
        assert "items_detected" in summary
        assert summary.get("chars", 0) >= len(transcript) - 5
        if summary.get("ai_error"):
            pytest.skip(f"AI provider error/cap: {summary['ai_error']}")
        assert summary["items_detected"] > 0, f"Expected >0 items detected. summary={summary}"

        # Detected items must appear in AI Inbox and/or as committed entities
        review = api.get(f"{BASE_URL}/api/review", timeout=TIMEOUT).json()
        created = body.get("created") or {}
        auto_created_ids = [c.get("id") for c in created.get("committed", [])]
        review_ids = created.get("review_ids", [])
        assert (len(review) > pytest.baseline_review_count) or len(auto_created_ids) > 0, \
            f"Expected either inbox growth or auto-created items. review={len(review)} vs {pytest.baseline_review_count}"
        pytest.review_ids_created = review_ids
        pytest.auto_created = created.get("committed", [])
        pytest.baseline_after_stop = len(review)

    def test_undo_removes_items_and_marks_undone(self, api):
        sid = pytest.session_id_1
        r = api.post(f"{BASE_URL}/api/listen/{sid}/undo", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert "removed" in body

        # Session status is undone
        rs = api.get(f"{BASE_URL}/api/listen/{sid}", timeout=TIMEOUT).json()
        assert rs["status"] == "undone"
        assert rs.get("created", {}).get("review_ids") == []

        # Review count should return to baseline
        review_now = api.get(f"{BASE_URL}/api/review", timeout=TIMEOUT).json()
        assert len(review_now) == pytest.baseline_review_count, \
            f"Expected inbox back to {pytest.baseline_review_count}, got {len(review_now)}"

        # Committed items also removed
        for c in pytest.auto_created:
            cid = c.get("id")
            kind = c.get("kind")
            coll = "tasks" if kind == "task" else "events"
            got = api.get(f"{BASE_URL}/api/{coll}", timeout=TIMEOUT).json()
            assert not any(x.get("id") == cid for x in got), f"{coll} {cid} not removed after undo"

    def test_stop_empty_transcript_no_crash(self, api):
        # Start a fresh session (previous was undone)
        r = api.post(f"{BASE_URL}/api/listen/start", json={"course": "EMPTY"}, timeout=TIMEOUT)
        assert r.status_code == 200
        sid = r.json()["id"]
        r2 = api.post(f"{BASE_URL}/api/listen/{sid}/stop", json={"transcript": ""}, timeout=TIMEOUT)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["status"] == "done"
        assert body["summary"]["items_detected"] == 0
        assert body["summary"]["chars"] == 0


# ----------------------------- Diagnostics -----------------------------

DIAG_KEYS = {"auth", "backend", "ai_provider", "notifications", "calendar", "microphone",
             "active_listening", "recording", "uploads", "processing",
             "last_transcription", "last_study_notes", "timezone"}


class TestDiagnostics:
    def test_diagnostics_has_all_keys_and_tz_echo(self, api):
        r = api.get(f"{BASE_URL}/api/diagnostics", params={"tz": "America/New_York"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        body = r.json()
        missing = DIAG_KEYS - set(body.keys())
        assert not missing, f"Missing keys: {missing}"
        assert body["timezone"] == "America/New_York"
        assert body["auth"]["ok"] is True
        assert body["backend"]["ok"] is True
        assert "provider" in body["ai_provider"]

    def test_device_state_reflected(self, api):
        r = api.post(f"{BASE_URL}/api/diagnostics/device-state",
                     json={"mic_permission": "granted", "notif_permission": "granted",
                           "recording": True}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("ok") is True

        d = api.get(f"{BASE_URL}/api/diagnostics", timeout=TIMEOUT).json()
        assert d["recording"]["active"] is True
        assert d["notifications"]["permission"] == "granted"
        assert d["microphone"]["permission"] == "granted"

    def test_test_backend(self, api):
        r = api.post(f"{BASE_URL}/api/diagnostics/test-backend", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_test_ai_live(self, api):
        r = api.post(f"{BASE_URL}/api/diagnostics/test-ai", timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        if body.get("ok") is False and "cap" in str(body.get("error", "")).lower():
            pytest.skip(f"AI daily cap: {body.get('error')}")
        assert body.get("ok") is True, f"AI test failed: {body}"
        assert isinstance(body.get("latency_ms"), int)
        assert body["latency_ms"] >= 0

    def test_test_calendar_read(self, api):
        r = api.post(f"{BASE_URL}/api/diagnostics/test-calendar-read", timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert "connected" in body
        assert "external_events_mirrored" in body
        assert isinstance(body["external_events_mirrored"], int)

    def test_retry_jobs(self, api):
        r = api.post(f"{BASE_URL}/api/diagnostics/retry-jobs", timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert "uploads_requeued" in body
        assert "reminders_requeued" in body

    def test_report_includes_recent_ledger(self, api):
        r = api.get(f"{BASE_URL}/api/diagnostics/report", timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        assert "recent_ledger" in body
        assert isinstance(body["recent_ledger"], list)
        # This user did listen_start/pause/resume/stop/undo -> should have ledger entries
        actions = [e.get("action") for e in body["recent_ledger"]]
        assert any(a and a.startswith("listen_") for a in actions), f"No listen_* in ledger. actions={actions}"


# ----------------------------- Two-user isolation -----------------------------

class TestIsolation:
    def test_user_b_cannot_see_user_a_sessions(self, api, api_b):
        # Ensure user A has at least one session (from prior tests it does)
        listA = api.get(f"{BASE_URL}/api/listen", timeout=TIMEOUT).json()
        assert isinstance(listA, list)
        a_ids = {s["id"] for s in listA}
        assert len(a_ids) >= 1

        listB = api_b.get(f"{BASE_URL}/api/listen", timeout=TIMEOUT).json()
        assert isinstance(listB, list)
        b_ids = {s["id"] for s in listB}
        assert a_ids.isdisjoint(b_ids), "User B sees User A's listen sessions"

        # User B active session should be empty (they never started one)
        r = api_b.get(f"{BASE_URL}/api/listen/active", timeout=TIMEOUT)
        assert r.status_code == 200
        # empty dict expected
        active = r.json()
        assert not active or active.get("id") not in a_ids

    def test_user_b_diagnostics_isolated(self, api, api_b):
        # User A had recording set to True
        dA = api.get(f"{BASE_URL}/api/diagnostics", timeout=TIMEOUT).json()
        dB = api_b.get(f"{BASE_URL}/api/diagnostics", timeout=TIMEOUT).json()
        assert dA["auth"]["user_id"] != dB["auth"]["user_id"]
        # User B never posted device-state -> recording.active False
        assert dB["recording"]["active"] is False
        # Notifications permission should be None for B
        assert dB["notifications"]["permission"] in (None, "")

    def test_user_b_cannot_read_a_session_by_id(self, api, api_b):
        listA = api.get(f"{BASE_URL}/api/listen", timeout=TIMEOUT).json()
        assert listA, "Precondition: user A has sessions"
        sid = listA[0]["id"]
        r = api_b.get(f"{BASE_URL}/api/listen/{sid}", timeout=TIMEOUT)
        assert r.status_code == 404


# ----------------------------- Regression -----------------------------

class TestRegression:
    def test_dev_login_200(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        r = s.post(f"{BASE_URL}/api/auth/dev-login",
                   json={"email": f"TEST_reg_{uuid.uuid4().hex[:6]}@example.com"}, timeout=TIMEOUT)
        if r.status_code == 429:
            pytest.skip("rate limited")
        assert r.status_code == 200

    def test_core_endpoints_200(self, api):
        for path in ("/api/review", "/api/events", "/api/tasks"):
            r = api.get(f"{BASE_URL}{path}", timeout=TIMEOUT)
            assert r.status_code == 200, f"{path} returned {r.status_code}"

    def test_briefing_200(self, api):
        r = api.get(f"{BASE_URL}/api/briefing", timeout=TIMEOUT)
        assert r.status_code == 200

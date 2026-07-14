"""Phase-2 reliability-layer backend tests (AI_PROVIDER=fixture).

Covers:
- Commitment state machine + reliability ledger
- AI Inbox / review path (approve, ignore -> dismissed)
- Idempotency-Key on POST /api/capture
- Per-user daily AI cap (429 + reset)
- Reminder lifecycle (delivered, failed retries, snoozed, sync, health)
- Chunked resumable audio upload (init/chunk/complete + 409 + idempotent chunks)
- Native calendar sync mapping (pending / sync / unlink)
- Source-grounded search (mode=keyword, citations)
- Cross-user data isolation across new collections
"""
import io
import os
import time
import uuid

import pytest
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
assert BASE, "EXPO_PUBLIC_BACKEND_URL must be set"


def _login(email: str | None = None):
    email = email or f"TEST_phase2_{uuid.uuid4().hex[:8]}@uni.edu"
    r = requests.post(f"{BASE}/api/auth/dev-login", json={"email": email}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    return {"Authorization": f"Bearer {j['access_token']}", "Content-Type": "application/json"}, j["user"]


@pytest.fixture(scope="module")
def user_a():
    hdrs, u = _login()
    return hdrs, u


@pytest.fixture(scope="module")
def user_b():
    hdrs, u = _login()
    return hdrs, u


# --------------------------------------------------------------------------
# 1. Commitment state machine + ledger
# --------------------------------------------------------------------------
class TestCommitmentPipeline:
    def test_capture_high_conf_creates_event_and_ledger(self, user_a):
        h, _ = user_a
        r = requests.post(f"{BASE}/api/capture",
                          json={"text": "I have a lab Tuesday at 2pm in room B12"},
                          headers=h, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body.get("committed"), list)
        assert len(body["committed"]) >= 1, f"expected auto-commit, got {body}"
        rec = body["committed"][0]
        assert rec["type"] == "event", rec
        assert rec.get("id")

        # commitments list contains it in scheduled state
        r2 = requests.get(f"{BASE}/api/commitments", headers=h, timeout=30)
        assert r2.status_code == 200
        commits = r2.json()
        scheduled = [c for c in commits if c["state"] == "scheduled"]
        assert scheduled, f"no scheduled commitments: {commits}"
        assert any(c.get("ref_id") == rec["id"] for c in scheduled), scheduled

        # ledger has full chain
        r3 = requests.get(f"{BASE}/api/ledger", headers=h, timeout=30)
        assert r3.status_code == 200
        actions = {e["action"] for e in r3.json()}
        for a in ("commitment_detected", "commitment_confirmed",
                  "commitment_scheduled", "reminder_created"):
            assert a in actions, f"missing ledger action {a}: {actions}"

        # a reminder exists for the event
        r4 = requests.get(f"{BASE}/api/reminders", headers=h, timeout=30)
        assert r4.status_code == 200
        rems = r4.json()
        m = [x for x in rems if x.get("ref_id") == rec["id"]]
        assert m, f"no reminder for event {rec['id']}: {rems}"
        assert m[0]["status"] == "pending"
        assert m[0]["remind_at"] < rec["start"], m[0]


# --------------------------------------------------------------------------
# 2. Review / AI Inbox path
# --------------------------------------------------------------------------
class TestReviewPath:
    def test_ambiguous_goes_to_review_then_approve(self, user_a):
        h, _ = user_a
        r = requests.post(f"{BASE}/api/capture",
                          json={"text": "maybe study sometime next week"},
                          headers=h, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["committed"] == [] or all(x.get("auto") for x in body["committed"])
        assert len(body["review"]) >= 1, body
        rid = body["review"][0]["id"]
        cid = body["review"][0].get("commitment_id")
        assert cid, body["review"][0]

        # approve -> should commit and transition to scheduled
        ra = requests.post(f"{BASE}/api/review/{rid}/action",
                           json={"action": "approve"}, headers=h, timeout=30)
        assert ra.status_code == 200, ra.text
        assert ra.json()["ok"] is True
        assert ra.json().get("committed") is not None

        # verify state == scheduled
        rc = requests.get(f"{BASE}/api/commitments", headers=h, timeout=30).json()
        found = [c for c in rc if c["id"] == cid]
        assert found and found[0]["state"] == "scheduled", found

    def test_ignore_dismisses_commitment(self, user_a):
        h, _ = user_a
        r = requests.post(f"{BASE}/api/capture",
                          json={"text": "possibly a study group later this week"},
                          headers=h, timeout=60)
        assert r.status_code == 200
        review = r.json()["review"]
        assert review, r.json()
        rid = review[0]["id"]
        cid = review[0]["commitment_id"]

        ra = requests.post(f"{BASE}/api/review/{rid}/action",
                           json={"action": "ignore"}, headers=h, timeout=30)
        assert ra.status_code == 200

        dis = requests.get(f"{BASE}/api/commitments",
                           params={"state": "dismissed"}, headers=h, timeout=30).json()
        assert any(c["id"] == cid for c in dis), dis


# --------------------------------------------------------------------------
# 3. Idempotency
# --------------------------------------------------------------------------
class TestIdempotency:
    def test_same_key_returns_cached(self):
        h, _ = _login()
        key = f"idem-{uuid.uuid4().hex[:8]}"
        text = "I have a physics quiz Friday at 10am"

        r1 = requests.post(f"{BASE}/api/capture", json={"text": text},
                           headers={**h, "Idempotency-Key": key}, timeout=60)
        assert r1.status_code == 200
        first = r1.json()

        r2 = requests.post(f"{BASE}/api/capture", json={"text": text},
                           headers={**h, "Idempotency-Key": key}, timeout=60)
        assert r2.status_code == 200
        second = r2.json()

        # identical cached response
        assert first == second, "cached response differs on replay"

        # no duplicate commitments
        commits = requests.get(f"{BASE}/api/commitments", headers=h, timeout=30).json()
        first_ids = {rec["id"] for rec in first.get("committed", [])}
        matching = [c for c in commits if c.get("ref_id") in first_ids]
        # one commitment per committed record, not two
        assert len(matching) == len(first_ids)

        # ai-usage incremented once
        usage = requests.get(f"{BASE}/api/ai-usage", headers=h, timeout=30).json()
        assert usage["used"] == 1, usage


# --------------------------------------------------------------------------
# 4. Daily AI cap
# --------------------------------------------------------------------------
class TestAICap:
    def test_daily_cap_returns_429(self):
        h, _ = _login()

        # set daily limit to 1
        pr = requests.put(f"{BASE}/api/prefs", json={"daily_ai_limit": 1},
                          headers=h, timeout=30)
        assert pr.status_code == 200
        assert pr.json()["daily_ai_limit"] == 1

        # 1st AI call — success
        s1 = requests.post(f"{BASE}/api/search", json={"query": "lab"},
                           headers=h, timeout=30)
        assert s1.status_code == 200, s1.text

        # 2nd AI call with different endpoint & new idempotency key -> 429
        s2 = requests.post(f"{BASE}/api/capture", json={"text": "email prof"},
                           headers={**h, "Idempotency-Key": f"cap-{uuid.uuid4().hex[:6]}"},
                           timeout=30)
        assert s2.status_code == 429, f"expected 429 got {s2.status_code}: {s2.text}"
        detail = s2.json().get("detail", "").lower()
        assert "daily" in detail and "limit" in detail, detail

        # reset
        requests.put(f"{BASE}/api/prefs", json={"daily_ai_limit": 150},
                     headers=h, timeout=30)
        usage = requests.get(f"{BASE}/api/ai-usage", headers=h, timeout=30).json()
        for k in ("used", "limit", "remaining", "unlimited"):
            assert k in usage, usage
        assert usage["limit"] == 150


# --------------------------------------------------------------------------
# 5. Reminders lifecycle
# --------------------------------------------------------------------------
class TestReminders:
    def test_delivered_sets_delivered_at(self, user_a):
        h, _ = user_a
        c = requests.post(f"{BASE}/api/reminders",
                          json={"title": "TEST_deliver",
                                "remind_at": "2027-01-01T10:00:00+00:00"},
                          headers=h, timeout=30)
        assert c.status_code == 200
        rid = c.json()["id"]

        s = requests.post(f"{BASE}/api/reminders/{rid}/status",
                          json={"status": "delivered", "external_id": "n1"},
                          headers=h, timeout=30)
        assert s.status_code == 200
        j = s.json()
        assert j["status"] == "delivered"
        assert j["delivered_at"] is not None
        assert j["external_id"] == "n1"

    def test_failed_retries_then_final_failed(self, user_a):
        h, _ = user_a
        c = requests.post(f"{BASE}/api/reminders",
                          json={"title": "TEST_retry",
                                "remind_at": "2027-01-01T11:00:00+00:00"},
                          headers=h, timeout=30)
        rid = c.json()["id"]

        # 1st fail -> pending, count=1
        j = requests.post(f"{BASE}/api/reminders/{rid}/status",
                          json={"status": "failed"}, headers=h, timeout=30).json()
        assert j["retry_count"] == 1 and j["status"] == "pending", j
        # 2nd fail -> pending, count=2
        j = requests.post(f"{BASE}/api/reminders/{rid}/status",
                          json={"status": "failed"}, headers=h, timeout=30).json()
        assert j["retry_count"] == 2 and j["status"] == "pending", j
        # 3rd fail -> failed
        j = requests.post(f"{BASE}/api/reminders/{rid}/status",
                          json={"status": "failed"}, headers=h, timeout=30).json()
        assert j["retry_count"] == 3 and j["status"] == "failed", j

    def test_snoozed_reschedules(self, user_a):
        h, _ = user_a
        c = requests.post(f"{BASE}/api/reminders",
                          json={"title": "TEST_snooze",
                                "remind_at": "2027-01-01T12:00:00+00:00"},
                          headers=h, timeout=30).json()
        rid = c["id"]
        s = requests.post(f"{BASE}/api/reminders/{rid}/status",
                          json={"status": "snoozed",
                                "snooze_until": "2027-02-01T10:00:00+00:00"},
                          headers=h, timeout=30).json()
        # snooze rewrites status -> scheduled + remind_at updated
        assert s["status"] == "scheduled", s
        assert s["remind_at"] == "2027-02-01T10:00:00+00:00", s

    def test_sync_and_health(self, user_a):
        h, _ = user_a
        s = requests.get(f"{BASE}/api/reminders/sync", headers=h, timeout=30)
        assert s.status_code == 200
        j = s.json()
        assert "reminders" in j and isinstance(j["reminders"], list)
        assert "routines" in j and len(j["routines"]) == 3
        keys = {r["key"] for r in j["routines"]}
        assert keys == {"daily_briefing", "evening_review", "weekly_review"}, keys
        assert "quiet_hours" in j and "server_time" in j

        hh = requests.get(f"{BASE}/api/reminders/health", headers=h, timeout=30)
        assert hh.status_code == 200
        c = hh.json()["counts"]
        for st in ("pending", "scheduled", "delivered", "snoozed", "failed",
                   "cancelled", "done"):
            assert st in c


# --------------------------------------------------------------------------
# 6. Chunked upload
# --------------------------------------------------------------------------
class TestChunkedUpload:
    def test_upload_lifecycle(self, user_a):
        h, _ = user_a
        auth_only = {"Authorization": h["Authorization"]}

        init = requests.post(f"{BASE}/api/uploads/init",
                             json={"filename": "lec.m4a", "title": "Lec",
                                   "total_chunks": 2},
                             headers=h, timeout=30)
        assert init.status_code == 200
        upid = init.json()["upload_id"]

        # upload chunk 0
        f0 = requests.post(f"{BASE}/api/uploads/{upid}/chunk",
                           data={"index": "0"},
                           files={"file": ("a.bin", b"AAAABBBBCCCC", "application/octet-stream")},
                           headers=auth_only, timeout=30)
        assert f0.status_code == 200
        assert f0.json()["received_count"] == 1

        # attempt /complete now -> 409
        c1 = requests.post(f"{BASE}/api/uploads/{upid}/complete",
                           headers=h, timeout=30)
        assert c1.status_code == 409, c1.text

        # re-upload chunk 0 (idempotent -> count stable at 1)
        f0b = requests.post(f"{BASE}/api/uploads/{upid}/chunk",
                            data={"index": "0"},
                            files={"file": ("a.bin", b"AAAABBBBCCCC", "application/octet-stream")},
                            headers=auth_only, timeout=30)
        assert f0b.status_code == 200
        assert f0b.json()["received_count"] == 1, f0b.json()

        # upload chunk 1
        f1 = requests.post(f"{BASE}/api/uploads/{upid}/chunk",
                           data={"index": "1"},
                           files={"file": ("b.bin", b"DDDDEEEEFFFF", "application/octet-stream")},
                           headers=auth_only, timeout=30)
        assert f1.status_code == 200
        assert f1.json()["received_count"] == 2

        # complete succeeds
        done = requests.post(f"{BASE}/api/uploads/{upid}/complete",
                             headers=h, timeout=60)
        assert done.status_code == 200, done.text
        dj = done.json()
        assert "transcript_id" in dj and "text" in dj and "bytes" in dj
        assert dj["bytes"] == 24  # 12 + 12


# --------------------------------------------------------------------------
# 7. Calendar sync mapping
# --------------------------------------------------------------------------
class TestCalendarSync:
    def test_pending_sync_unlink(self, user_a):
        h, _ = user_a
        ev = requests.post(f"{BASE}/api/events",
                           json={"title": "TEST_cal_class",
                                 "start": "2027-03-01T09:00:00+00:00",
                                 "recurring": False},
                           headers=h, timeout=30)
        assert ev.status_code == 200
        eid = ev.json()["id"]

        pend = requests.get(f"{BASE}/api/calendar/pending", headers=h, timeout=30).json()
        assert any(x["id"] == eid for x in pend), pend

        sy = requests.post(f"{BASE}/api/calendar/sync",
                           json={"mappings": {eid: "ext-123"}},
                           headers=h, timeout=30)
        assert sy.status_code == 200
        assert sy.json() == {"ok": True, "synced": 1}, sy.json()

        pend2 = requests.get(f"{BASE}/api/calendar/pending", headers=h, timeout=30).json()
        assert not any(x["id"] == eid for x in pend2)

        un = requests.post(f"{BASE}/api/calendar/unlink/{eid}", headers=h, timeout=30)
        assert un.status_code == 200
        assert un.json().get("ok") is True

        pend3 = requests.get(f"{BASE}/api/calendar/pending", headers=h, timeout=30).json()
        assert any(x["id"] == eid for x in pend3), pend3


# --------------------------------------------------------------------------
# 8. Search grounded in own data
# --------------------------------------------------------------------------
class TestSearch:
    def test_keyword_search(self, user_a):
        h, _ = user_a
        # ensure some chunk with "lab" exists (from TestCommitmentPipeline)
        r = requests.post(f"{BASE}/api/search", json={"query": "lab"},
                          headers=h, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "answer" in j and isinstance(j["answer"], str)
        assert j["mode"] == "keyword", j
        assert isinstance(j["citations"], list)


# --------------------------------------------------------------------------
# 9. Cross-user data isolation
# --------------------------------------------------------------------------
class TestCrossUserIsolation:
    def test_a_data_not_visible_to_b(self, user_a, user_b):
        ha, ua = user_a
        hb, ub = user_b
        assert ua["id"] != ub["id"]

        # A's ids we'll assert absent from B
        a_commits = requests.get(f"{BASE}/api/commitments", headers=ha, timeout=30).json()
        a_led = requests.get(f"{BASE}/api/ledger", headers=ha, timeout=30).json()
        a_rem = requests.get(f"{BASE}/api/reminders", headers=ha, timeout=30).json()
        a_ev = requests.get(f"{BASE}/api/events", headers=ha, timeout=30).json()

        a_commit_ids = {c["id"] for c in a_commits}
        a_led_ids = {e["id"] for e in a_led}
        a_rem_ids = {r["id"] for r in a_rem}
        a_ev_ids = {e["id"] for e in a_ev}

        assert a_commit_ids, "expected user A to have commitments from earlier tests"

        # B fetches — should be empty or fully disjoint
        b_commits = requests.get(f"{BASE}/api/commitments", headers=hb, timeout=30).json()
        b_led = requests.get(f"{BASE}/api/ledger", headers=hb, timeout=30).json()
        b_rem = requests.get(f"{BASE}/api/reminders", headers=hb, timeout=30).json()
        b_ev = requests.get(f"{BASE}/api/events", headers=hb, timeout=30).json()

        assert a_commit_ids.isdisjoint({c["id"] for c in b_commits})
        assert a_led_ids.isdisjoint({e["id"] for e in b_led})
        assert a_rem_ids.isdisjoint({r["id"] for r in b_rem})
        assert a_ev_ids.isdisjoint({e["id"] for e in b_ev})

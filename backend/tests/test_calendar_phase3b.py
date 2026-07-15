"""Phase 3B — provider-neutral calendar integration tests.

Simulates the device (expo-calendar) via the backend /api/calendar/* endpoints.
Real OS-calendar reads/writes are DEVICE-ONLY and out of scope for this suite.
"""
import os
import uuid
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL must be set"


# ---------- helpers ----------
def _new_session(email_prefix: str = "cal") -> requests.Session:
    s = requests.Session()
    s.headers["Content-Type"] = "application/json"
    email = f"TEST_{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/dev-login", json={"email": email}, timeout=15)
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    s.email = email  # type: ignore[attr-defined]
    return s


def _connect(s: requests.Session, access_mode: str = "read_write", cal_id: str = "cal-primary"):
    r = s.put(f"{BASE_URL}/api/calendar/connection", json={
        "calendar_id": cal_id, "calendar_title": "Primary",
        "account_name": "me@example.com", "provider": "google",
        "access_mode": access_mode,
    }, timeout=15)
    r.raise_for_status()
    return r.json()


@pytest.fixture(scope="module")
def user_a() -> requests.Session:
    return _new_session("A")


@pytest.fixture(scope="module")
def user_b() -> requests.Session:
    return _new_session("B")


# ============================================================
# 1) Connection PUT/GET, access_mode -> status
# ============================================================
class TestConnection:
    def test_default_connection_is_disconnected(self):
        s = _new_session("conn0")
        r = s.get(f"{BASE_URL}/api/calendar/connection", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["connected"] is False
        assert d["status"] == "disconnected"

    def test_connect_read_write_status_connected(self):
        s = _new_session("connRW")
        d = _connect(s, "read_write")
        assert d["connected"] is True
        assert d["access_mode"] == "read_write"
        assert d["status"] == "connected"
        # GET reflects it
        d2 = s.get(f"{BASE_URL}/api/calendar/connection").json()
        assert d2["status"] == "connected" and d2["connected"] is True

    def test_connect_read_only_status_read_only(self):
        s = _new_session("connRO")
        d = _connect(s, "read_only")
        assert d["connected"] is True
        assert d["access_mode"] == "read_only"
        assert d["status"] == "read_only"
        d2 = s.get(f"{BASE_URL}/api/calendar/connection").json()
        assert d2["status"] == "read_only"

    def test_invalid_access_mode_rejected(self):
        s = _new_session("connBad")
        r = s.put(f"{BASE_URL}/api/calendar/connection", json={
            "calendar_id": "x", "access_mode": "garbage"}, timeout=10)
        assert r.status_code == 422


# ============================================================
# 2) /calendar/pending — gated on connection & access_mode
# ============================================================
class TestPending:
    def test_pending_empty_when_disconnected(self):
        s = _new_session("pendDis")
        # create an event first
        s.post(f"{BASE_URL}/api/events", json={"title": "T1", "event_type": "study",
            "start": "2026-08-01T10:00:00Z", "end": "2026-08-01T11:00:00Z"}).raise_for_status()
        r = s.get(f"{BASE_URL}/api/calendar/pending")
        assert r.status_code == 200
        assert r.json() == []

    def test_pending_empty_when_read_only(self):
        s = _new_session("pendRO")
        _connect(s, "read_only")
        s.post(f"{BASE_URL}/api/events", json={"title": "T2", "event_type": "study",
            "start": "2026-08-01T10:00:00Z", "end": "2026-08-01T11:00:00Z"}).raise_for_status()
        r = s.get(f"{BASE_URL}/api/calendar/pending")
        assert r.status_code == 200
        assert r.json() == []

    def test_pending_lists_events_when_read_write(self):
        s = _new_session("pendRW")
        _connect(s, "read_write")
        ev = s.post(f"{BASE_URL}/api/events", json={"title": "T3", "event_type": "study",
            "start": "2026-08-01T10:00:00Z", "end": "2026-08-01T11:00:00Z"}).json()
        r = s.get(f"{BASE_URL}/api/calendar/pending")
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()]
        assert ev["id"] in ids


# ============================================================
# 3) /calendar/sync — link + idempotency
# ============================================================
class TestSyncLink:
    def test_sync_links_event_and_removes_from_pending(self):
        s = _new_session("syncA")
        _connect(s, "read_write")
        ev = s.post(f"{BASE_URL}/api/events", json={"title": "Study block",
            "event_type": "study", "start": "2026-08-01T10:00:00Z",
            "end": "2026-08-01T11:00:00Z"}).json()
        ext_id = f"ext-{uuid.uuid4().hex[:8]}"

        r = s.post(f"{BASE_URL}/api/calendar/sync",
                   json={"mappings": {ev["id"]: ext_id}})
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True and body.get("synced") == 1

        # No longer in pending
        pending = s.get(f"{BASE_URL}/api/calendar/pending").json()
        assert ev["id"] not in [p["id"] for p in pending]

        # Idempotent: repeat
        r2 = s.post(f"{BASE_URL}/api/calendar/sync",
                    json={"mappings": {ev["id"]: ext_id}})
        assert r2.status_code == 200
        assert r2.json().get("ok") is True

        # Event still linked, external_id set
        events = s.get(f"{BASE_URL}/api/events").json()
        matched = [e for e in events if e["id"] == ev["id"]][0]
        assert matched.get("external_id") == ext_id


# ============================================================
# 4) External ingest — title-only auto, time change queues review
# ============================================================
class TestExternalIngestLinked:
    def _seed_linked_event(self, s, title="Reading", event_type="study",
                           start="2026-08-05T09:00:00Z", end="2026-08-05T10:00:00Z",
                           recurring=False):
        _connect(s, "read_write")
        ev = s.post(f"{BASE_URL}/api/events", json={
            "title": title, "event_type": event_type,
            "start": start, "end": end, "recurring": recurring}).json()
        ext_id = f"ext-{uuid.uuid4().hex[:8]}"
        s.post(f"{BASE_URL}/api/calendar/sync",
               json={"mappings": {ev["id"]: ext_id}}).raise_for_status()
        return ev, ext_id

    def test_title_only_change_auto_applies_for_non_high_risk(self):
        s = _new_session("ingA")
        ev, ext_id = self._seed_linked_event(s)
        r = s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id, "title": "Reading (renamed)",
                        "start": ev["start"], "end": ev["end"]}]})
        assert r.status_code == 200
        body = r.json()
        assert body.get("updated", 0) >= 1
        # No review queued
        rev = s.get(f"{BASE_URL}/api/calendar/review").json()
        assert not any(x for x in rev if x.get("internal_id") == ev["id"])
        # internal event title changed
        events = s.get(f"{BASE_URL}/api/events").json()
        matched = [e for e in events if e["id"] == ev["id"]][0]
        assert matched["title"] == "Reading (renamed)"

    def test_time_change_creates_review_and_does_not_modify(self):
        s = _new_session("ingB")
        ev, ext_id = self._seed_linked_event(s, title="Reading")
        new_start = "2026-08-05T11:00:00Z"
        r = s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id, "title": "Reading",
                        "start": new_start, "end": ev["end"]}]})
        assert r.status_code == 200
        assert r.json().get("pending_reviews", 0) >= 1
        rev = s.get(f"{BASE_URL}/api/calendar/review").json()
        mine = [x for x in rev if x.get("internal_id") == ev["id"]
                and x.get("kind") == "external_edit"]
        assert mine, "expected external_edit review"
        # Internal event NOT modified
        events = s.get(f"{BASE_URL}/api/events").json()
        matched = [e for e in events if e["id"] == ev["id"]][0]
        assert matched["start"] == ev["start"]

    def test_high_risk_exam_time_change_queues_review(self):
        s = _new_session("ingExam")
        ev, ext_id = self._seed_linked_event(s, title="Exam", event_type="exam")
        r = s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id, "title": "Final Exam",
                        "start": ev["start"], "end": ev["end"]}]})
        assert r.status_code == 200
        # Even title-only change on exam should queue review
        rev = s.get(f"{BASE_URL}/api/calendar/review").json()
        assert any(x for x in rev if x.get("internal_id") == ev["id"]
                   and x.get("kind") == "external_edit")
        # Internal event NOT modified
        events = s.get(f"{BASE_URL}/api/events").json()
        matched = [e for e in events if e["id"] == ev["id"]][0]
        assert matched["title"] == "Exam"

    def test_high_risk_recurring_title_change_queues_review(self):
        s = _new_session("ingRec")
        ev, ext_id = self._seed_linked_event(s, title="Weekly", recurring=True)
        r = s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id, "title": "Weekly (v2)",
                        "start": ev["start"], "end": ev["end"], "recurring": True}]})
        assert r.status_code == 200
        rev = s.get(f"{BASE_URL}/api/calendar/review").json()
        assert any(x for x in rev if x.get("internal_id") == ev["id"]
                   and x.get("kind") == "external_edit")
        events = s.get(f"{BASE_URL}/api/events").json()
        matched = [e for e in events if e["id"] == ev["id"]][0]
        assert matched["title"] == "Weekly"


# ============================================================
# 5) Review approve/dismiss
# ============================================================
class TestReviewActions:
    def test_approve_applies_change(self):
        s = _new_session("revA")
        _connect(s, "read_write")
        ev = s.post(f"{BASE_URL}/api/events", json={"title": "Study", "event_type": "study",
            "start": "2026-08-05T09:00:00Z", "end": "2026-08-05T10:00:00Z"}).json()
        ext_id = f"ext-{uuid.uuid4().hex[:8]}"
        s.post(f"{BASE_URL}/api/calendar/sync", json={"mappings": {ev["id"]: ext_id}})
        new_start = "2026-08-05T14:00:00Z"
        s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id, "title": "Study",
                        "start": new_start, "end": ev["end"]}]}).raise_for_status()
        rev = s.get(f"{BASE_URL}/api/calendar/review").json()
        rid = [x["id"] for x in rev if x.get("internal_id") == ev["id"]][0]

        r = s.post(f"{BASE_URL}/api/calendar/review/{rid}", json={"approve": True})
        assert r.status_code == 200
        events = s.get(f"{BASE_URL}/api/events").json()
        matched = [e for e in events if e["id"] == ev["id"]][0]
        assert matched["start"] == new_start

    def test_dismiss_leaves_change(self):
        s = _new_session("revD")
        _connect(s, "read_write")
        ev = s.post(f"{BASE_URL}/api/events", json={"title": "S2", "event_type": "study",
            "start": "2026-08-05T09:00:00Z", "end": "2026-08-05T10:00:00Z"}).json()
        ext_id = f"ext-{uuid.uuid4().hex[:8]}"
        s.post(f"{BASE_URL}/api/calendar/sync", json={"mappings": {ev["id"]: ext_id}})
        s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id, "title": "S2",
                        "start": "2026-08-05T15:00:00Z", "end": ev["end"]}]}).raise_for_status()
        rev = s.get(f"{BASE_URL}/api/calendar/review").json()
        rid = [x["id"] for x in rev if x.get("internal_id") == ev["id"]][0]
        r = s.post(f"{BASE_URL}/api/calendar/review/{rid}", json={"approve": False})
        assert r.status_code == 200
        events = s.get(f"{BASE_URL}/api/events").json()
        matched = [e for e in events if e["id"] == ev["id"]][0]
        assert matched["start"] == ev["start"]  # unchanged


# ============================================================
# 6) Deletion detection via window + approval
# ============================================================
class TestDeletionDetection:
    def test_missing_from_window_creates_external_delete_review(self):
        s = _new_session("del")
        _connect(s, "read_write")
        ev = s.post(f"{BASE_URL}/api/events", json={"title": "Gone", "event_type": "study",
            "start": "2026-08-10T10:00:00Z", "end": "2026-08-10T11:00:00Z"}).json()
        ext_id = f"ext-{uuid.uuid4().hex[:8]}"
        s.post(f"{BASE_URL}/api/calendar/sync", json={"mappings": {ev["id"]: ext_id}})
        # Seed external mirror with this event
        s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id, "title": "Gone",
                        "start": "2026-08-10T10:00:00Z", "end": "2026-08-10T11:00:00Z"}]})
        # Now report a window containing it but no events → deletion
        r = s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "window_start": "2026-08-10T00:00:00Z",
            "window_end": "2026-08-10T23:59:59Z",
            "events": []})
        assert r.status_code == 200
        rev = s.get(f"{BASE_URL}/api/calendar/review").json()
        mine = [x for x in rev if x.get("internal_id") == ev["id"]
                and x.get("kind") == "external_delete"]
        assert mine, "expected external_delete review"

        # Approve deletion — internal event should be gone
        r2 = s.post(f"{BASE_URL}/api/calendar/review/{mine[0]['id']}", json={"approve": True})
        assert r2.status_code == 200
        events = s.get(f"{BASE_URL}/api/events").json()
        assert not any(e["id"] == ev["id"] for e in events)


# ============================================================
# 7) Non-SA external events -> stored in mirror, is_sa false
# ============================================================
class TestExternalMirror:
    def test_non_sa_stored_and_no_tasks_created(self):
        s = _new_session("mir")
        _connect(s, "read_write")
        ext_id = f"ext-{uuid.uuid4().hex[:8]}"
        s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id, "title": "Dentist",
                        "start": "2026-08-11T09:00:00Z", "end": "2026-08-11T10:00:00Z"}]})
        ext = s.get(f"{BASE_URL}/api/calendar/external").json()
        mine = [x for x in ext if x["external_id"] == ext_id]
        assert mine and mine[0]["is_sa"] is False
        # No new task/event was created from this
        tasks = s.get(f"{BASE_URL}/api/tasks").json()
        assert not any("Dentist" in t.get("title", "") for t in tasks)


# ============================================================
# 8) /calendar/status
# ============================================================
class TestStatus:
    def test_permission_revoked_disconnects(self):
        s = _new_session("stR")
        _connect(s, "read_write")
        r = s.post(f"{BASE_URL}/api/calendar/status", json={"status": "permission_revoked"})
        assert r.status_code == 200
        conn = s.get(f"{BASE_URL}/api/calendar/connection").json()
        assert conn["connected"] is False
        assert conn["status"] == "permission_revoked"

    def test_sync_failed_stores_reason(self):
        s = _new_session("stF")
        _connect(s, "read_write")
        r = s.post(f"{BASE_URL}/api/calendar/status",
                   json={"status": "sync_failed", "failure_reason": "network down"})
        assert r.status_code == 200
        conn = s.get(f"{BASE_URL}/api/calendar/connection").json()
        assert conn["status"] == "sync_failed"
        assert conn["failure_reason"] == "network down"

    def test_invalid_status_422(self):
        s = _new_session("stX")
        r = s.post(f"{BASE_URL}/api/calendar/status", json={"status": "wonky"})
        assert r.status_code == 422


# ============================================================
# 9) Briefing includes external, no dupes, conflict risk
# ============================================================
class TestBriefing:
    def test_briefing_shows_external_and_conflict(self):
        s = _new_session("brf")
        _connect(s, "read_write")
        # Today in UTC (tz_offset_min=0)
        today = datetime.now(timezone.utc).date()
        start_a = f"{today.isoformat()}T10:00:00Z"
        end_a = f"{today.isoformat()}T11:00:00Z"
        start_b = f"{today.isoformat()}T10:30:00Z"  # overlaps a
        end_b = f"{today.isoformat()}T11:30:00Z"

        # SA event
        sa_ev = s.post(f"{BASE_URL}/api/events", json={"title": "SA class",
            "event_type": "class", "start": start_a, "end": end_a}).json()
        # External event overlapping (non-SA)
        ext_id_free = f"ext-{uuid.uuid4().hex[:8]}"
        s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id_free, "title": "Ext meeting",
                        "start": start_b, "end": end_b}]})
        # A linked SA event (should NOT appear duplicated as external)
        sa_linked = s.post(f"{BASE_URL}/api/events", json={"title": "Linked",
            "event_type": "study", "start": f"{today.isoformat()}T14:00:00Z",
            "end": f"{today.isoformat()}T15:00:00Z"}).json()
        ext_id_linked = f"ext-{uuid.uuid4().hex[:8]}"
        s.post(f"{BASE_URL}/api/calendar/sync", json={"mappings": {sa_linked["id"]: ext_id_linked}})
        s.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id_linked, "title": "Linked",
                        "start": f"{today.isoformat()}T14:00:00Z",
                        "end": f"{today.isoformat()}T15:00:00Z"}]})

        r = s.get(f"{BASE_URL}/api/briefing?tz_offset_min=0")
        assert r.status_code == 200
        b = r.json()
        # external present with external=true flag
        externals = [e for e in b["today_classes"] if e.get("external")]
        assert any(e.get("id") == ext_id_free for e in externals)
        # linked external NOT duplicated: only one entry with that title
        titles = [e.get("title") for e in b["today_classes"]]
        assert titles.count("Linked") == 1
        # conflict risk
        assert any("Schedule conflict" in r.get("text", "") for r in b["risks"])
        # stats
        assert "external_today" in b["stats"]
        assert b["stats"]["external_today"] >= 1
        assert "calendar_review" in b["stats"]


# ============================================================
# 10) Two-user isolation
# ============================================================
class TestIsolation:
    def test_user_b_cannot_see_user_a_data(self, user_a, user_b):
        _connect(user_a, "read_write", cal_id="A-cal")
        ev = user_a.post(f"{BASE_URL}/api/events", json={"title": "A-only",
            "event_type": "study", "start": "2026-08-20T10:00:00Z",
            "end": "2026-08-20T11:00:00Z"}).json()
        ext_id = f"ext-{uuid.uuid4().hex[:8]}"
        user_a.post(f"{BASE_URL}/api/calendar/sync",
                    json={"mappings": {ev["id"]: ext_id}}).raise_for_status()
        # Cause a review for A
        user_a.post(f"{BASE_URL}/api/calendar/external/ingest", json={
            "events": [{"external_id": ext_id, "title": "A-only",
                        "start": "2026-08-20T15:00:00Z", "end": "2026-08-20T16:00:00Z"}]})
        # B checks: nothing bleeds through
        b_conn = user_b.get(f"{BASE_URL}/api/calendar/connection").json()
        assert b_conn.get("calendar_id") != "A-cal"
        b_ext = user_b.get(f"{BASE_URL}/api/calendar/external").json()
        assert not any(x.get("external_id") == ext_id for x in b_ext)
        b_rev = user_b.get(f"{BASE_URL}/api/calendar/review").json()
        assert b_rev == [] or all(x.get("internal_id") != ev["id"] for x in b_rev)


# ============================================================
# 11) Regressions (200s)
# ============================================================
class TestRegressions:
    def test_regression_endpoints(self):
        s = _new_session("reg")
        # tasks CRUD
        t = s.post(f"{BASE_URL}/api/tasks", json={"title": "TReg", "due": "2026-08-20"}).json()
        assert s.get(f"{BASE_URL}/api/tasks").status_code == 200
        assert s.patch(f"{BASE_URL}/api/tasks/{t['id']}",
                       json={"status": "done"}).status_code == 200
        assert s.delete(f"{BASE_URL}/api/tasks/{t['id']}").status_code == 200
        # events CRUD
        e = s.post(f"{BASE_URL}/api/events", json={"title": "EReg",
            "event_type": "study", "start": "2026-08-20T10:00:00Z",
            "end": "2026-08-20T11:00:00Z"}).json()
        assert s.get(f"{BASE_URL}/api/events").status_code == 200
        assert s.patch(f"{BASE_URL}/api/events/{e['id']}",
                       json={"title": "EReg2"}).status_code == 200
        assert s.delete(f"{BASE_URL}/api/events/{e['id']}").status_code == 200
        # briefing/timeline/reminders
        assert s.get(f"{BASE_URL}/api/briefing?tz_offset_min=0").status_code == 200
        assert s.get(f"{BASE_URL}/api/timeline").status_code == 200
        assert s.get(f"{BASE_URL}/api/reminders").status_code == 200


# ============================================================
# 12) DELETE /me safeguard
# ============================================================
class TestDeleteAccount:
    def test_dev_login_account_deletes_without_password(self):
        s = _new_session("delDev")
        r = s.delete(f"{BASE_URL}/api/me")
        assert r.status_code == 200
        assert r.json().get("deleted") is True

    def test_password_account_requires_password(self):
        # Register + verify + login a real password account
        email = f"TEST_pw_{uuid.uuid4().hex[:8]}@uni.edu"
        pw = "correct horse battery staple"
        rs = requests.Session()
        rs.headers["Content-Type"] = "application/json"
        rr = rs.post(f"{BASE_URL}/api/auth/register",
                     json={"email": email, "password": pw, "full_name": "Test PW"}, timeout=15)
        if rr.status_code == 429:
            pytest.skip("rate-limited on register")
        assert rr.status_code == 200
        # get verify token from dev-outbox (backend lowercases the email)
        ob = rs.get(f"{BASE_URL}/api/auth/dev-outbox", timeout=10).json()
        token = None
        el = email.lower()
        for msg in reversed(ob.get("messages", [])):
            if msg.get("to", "").lower() == el and "verify-email" in msg.get("text", ""):
                import re
                m = re.search(r"verify-email\?token=([^\s]+)", msg["text"])
                if m:
                    token = m.group(1); break
        assert token, "verification token not captured"
        vr = rs.post(f"{BASE_URL}/api/auth/verify-email", json={"token": token})
        assert vr.status_code == 200
        lr = rs.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
        if lr.status_code == 429:
            pytest.skip("rate-limited on login")
        assert lr.status_code == 200
        rs.headers["Authorization"] = f"Bearer {lr.json()['access_token']}"
        # DELETE without password -> 403
        r1 = rs.delete(f"{BASE_URL}/api/me")
        assert r1.status_code == 403
        # DELETE with wrong password -> 403
        r2 = rs.delete(f"{BASE_URL}/api/me",
                       data='{"password":"wrong-guess-abc"}')
        assert r2.status_code == 403
        # DELETE with correct password -> 200
        import json
        r3 = rs.delete(f"{BASE_URL}/api/me", data=json.dumps({"password": pw}))
        assert r3.status_code == 200
        assert r3.json().get("deleted") is True

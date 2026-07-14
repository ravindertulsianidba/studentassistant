"""Regression suite verifying the server.py -> routers/ refactor introduced NO
behavior change. Runs against the public URL with AI_PROVIDER=openai (LIVE).

Grouped by review_request numbering:
1. Auth (dev-login, /me, refresh rotation, logout)
2. Cross-user isolation (A vs B)
3. Tasks/Events CRUD (+ reminders cancel on task done)
4. LIVE AI (capture, import, notes/generate, search)
5. Briefing (regression: NameError defaultdict) + evening/weekly/timeline/courses/review
6. Reliability (commitments, ledger, reminders full lifecycle, sync, health)
7. Calendar (pending -> sync -> unlink)
8. Chunked upload (init/chunk/complete + 409 partial + idempotent repeat)
9. Idempotency-Key on /capture (same result, no duplicate commitment, ai-usage counted once)
10. Daily AI cap (429)
11. /prefs, /export (commitments/ledger/reminders), DELETE /me revokes sessions
"""
import os, uuid, time, io, pytest, requests

BASE = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL") or "").rstrip("/")
assert BASE, "public backend URL required"

def _mk_user(prefix="reg"):
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:8]}@uni.edu"
    r = requests.post(f"{BASE}/api/auth/dev-login", json={"email": email}, timeout=20)
    r.raise_for_status()
    body = r.json()
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json",
                      "Authorization": f"Bearer {body['access_token']}"})
    return s, body, email

# -------------------- 1. AUTH --------------------
class TestAuth:
    def test_devlogin_me_unauth_refresh_logout(self):
        s, body, email = _mk_user("auth")
        assert body["access_token"] and body["refresh_token"] and body["user"]["email"] == email

        # /me with token
        r = s.get(f"{BASE}/api/me", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["email"] == email

        # unauth /tasks -> 401
        r = requests.get(f"{BASE}/api/tasks", timeout=15)
        assert r.status_code == 401

        # refresh rotates + old refresh revoked
        old_refresh = body["refresh_token"]
        r = requests.post(f"{BASE}/api/auth/refresh", json={"refresh_token": old_refresh}, timeout=15)
        assert r.status_code == 200, r.text
        new = r.json()
        assert new["refresh_token"] and new["refresh_token"] != old_refresh

        # reusing old refresh -> 401
        r = requests.post(f"{BASE}/api/auth/refresh", json={"refresh_token": old_refresh}, timeout=15)
        assert r.status_code == 401

        # logout revokes the new refresh
        r = requests.post(f"{BASE}/api/auth/logout", json={"refresh_token": new["refresh_token"]}, timeout=15)
        assert r.status_code == 200
        r = requests.post(f"{BASE}/api/auth/refresh", json={"refresh_token": new["refresh_token"]}, timeout=15)
        assert r.status_code == 401

# -------------------- 2. USER ISOLATION --------------------
class TestIsolation:
    def test_ab_isolation(self):
        a, _, _ = _mk_user("iso_a")
        b, _, _ = _mk_user("iso_b")

        # A creates a task and event
        rt = a.post(f"{BASE}/api/tasks", json={"title": "A-only task", "course": "COURSE_A"}, timeout=15)
        assert rt.status_code == 200
        a_tid = rt.json()["id"]
        re_ = a.post(f"{BASE}/api/events", json={"title": "A-only event", "event_type": "meeting",
                                                 "course": "COURSE_A", "start": "2030-01-01T10:00:00+00:00"}, timeout=15)
        assert re_.status_code == 200

        # B should not see A's items
        b_tasks = b.get(f"{BASE}/api/tasks", timeout=15).json()
        b_events = b.get(f"{BASE}/api/events", timeout=15).json()
        assert not any(t["id"] == a_tid for t in b_tasks)
        assert not any(e.get("course") == "COURSE_A" for e in b_events)

        # B cannot PATCH A's task -> 404
        r = b.patch(f"{BASE}/api/tasks/{a_tid}", json={"status": "done"}, timeout=15)
        assert r.status_code == 404

        # B DELETE of A's task -> 404 & task must still exist for A
        r = b.delete(f"{BASE}/api/tasks/{a_tid}", timeout=15)
        assert r.status_code == 404
        r = a.get(f"{BASE}/api/tasks", timeout=15).json()
        assert any(t["id"] == a_tid for t in r)

        # courses scoped
        assert "COURSE_A" not in [c["name"] for c in b.get(f"{BASE}/api/courses", timeout=15).json()]

        # export scoped
        exp_a = a.get(f"{BASE}/api/export", timeout=20).json()
        exp_b = b.get(f"{BASE}/api/export", timeout=20).json()
        a_task_ids = {t["id"] for t in exp_a["tasks"]}
        b_task_ids = {t["id"] for t in exp_b["tasks"]}
        assert a_tid in a_task_ids
        assert not (a_task_ids & b_task_ids)

# -------------------- 3. TASKS/EVENTS CRUD --------------------
class TestCRUD:
    def test_task_lifecycle_cancels_reminders(self):
        s, _, _ = _mk_user("crud")
        # create task
        rt = s.post(f"{BASE}/api/tasks", json={"title": "CRUD Task", "due": "2030-05-01T09:00:00+00:00"}, timeout=15)
        assert rt.status_code == 200
        tid = rt.json()["id"]

        # create manual reminder ref'ing task
        rr = s.post(f"{BASE}/api/reminders", json={"title": "ping", "remind_at": "2030-05-01T08:00:00+00:00",
                                                    "ref_type": "task", "ref_id": tid}, timeout=15)
        assert rr.status_code == 200
        rid = rr.json()["id"]

        # list & patch done
        assert any(t["id"] == tid for t in s.get(f"{BASE}/api/tasks", timeout=15).json())
        rp = s.patch(f"{BASE}/api/tasks/{tid}", json={"status": "done"}, timeout=15)
        assert rp.status_code == 200 and rp.json()["status"] == "done"

        # reminder should be cancelled
        rems = s.get(f"{BASE}/api/reminders", timeout=15).json()
        found = [r for r in rems if r["id"] == rid]
        assert found and found[0]["status"] == "cancelled"

        # delete
        rd = s.delete(f"{BASE}/api/tasks/{tid}", timeout=15)
        assert rd.status_code == 200

    def test_event_crud(self):
        s, _, _ = _mk_user("crud_ev")
        r = s.post(f"{BASE}/api/events", json={"title": "Ev1", "event_type": "meeting",
                                               "start": "2030-06-01T10:00:00+00:00"}, timeout=15)
        assert r.status_code == 200
        eid = r.json()["id"]
        assert any(e["id"] == eid for e in s.get(f"{BASE}/api/events", timeout=15).json())
        assert s.delete(f"{BASE}/api/events/{eid}", timeout=15).status_code == 200

# -------------------- 4. LIVE AI --------------------
class TestLiveAI:
    def test_capture(self):
        s, _, _ = _mk_user("ai_cap")
        r = s.post(f"{BASE}/api/capture",
                   json={"text": "sociology midterm Friday 10am room 204; email Professor Lee tomorrow"},
                   timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "committed" in d and "review" in d
        # LIVE AI should produce SOME structured item (either bucket).
        assert (len(d["committed"]) + len(d["review"])) >= 1

    def test_import(self):
        s, _, _ = _mk_user("ai_imp")
        r = s.post(f"{BASE}/api/import",
                   json={"text": "CS101 Syllabus. Assignment 1 due Sept 15. Final exam Dec 12 at 9am."},
                   timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("doc_type") and "review" in d
        assert len(d["review"]) >= 1

    def test_notes_generate(self):
        s, _, _ = _mk_user("ai_notes")
        r = s.post(f"{BASE}/api/notes/generate",
                   json={"title": "Photosynthesis",
                         "transcript": "Photosynthesis converts light energy into chemical energy. "
                                       "Chlorophyll absorbs light. Water is split. Oxygen is released. "
                                       "Glucose is produced. The Calvin cycle fixes CO2. "
                                       "Professor emphasized light-dependent vs light-independent reactions."},
                   timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("study_notes") and isinstance(d["study_notes"], dict)

    def test_search(self):
        s, _, _ = _mk_user("ai_srch")
        # seed material
        r = s.post(f"{BASE}/api/import",
                   json={"text": "CS101. Final exam is on December 12 at 9am in Room 100."},
                   timeout=60)
        assert r.status_code == 200
        r = s.post(f"{BASE}/api/search", json={"query": "final exam"}, timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "answer" in d and "citations" in d and d.get("mode") in ("keyword", "semantic")

# -------------------- 5. PLANNER / BRIEFING (regression) --------------------
class TestPlannerReadOnly:
    def test_briefing_and_reviews(self):
        s, _, _ = _mk_user("planner")
        # seed a task so briefing has content
        s.post(f"{BASE}/api/tasks", json={"title": "Study for midterm", "due": "2030-06-05T09:00:00+00:00", "course": "SOC"}, timeout=15)

        r = s.get(f"{BASE}/api/briefing", timeout=20)
        assert r.status_code == 200, r.text  # was the reported regression
        b = r.json()
        for k in ("stats", "risks", "recommendation"):
            assert k in b, f"missing {k}: {b}"

        assert s.get(f"{BASE}/api/evening-review", timeout=15).status_code == 200
        assert s.get(f"{BASE}/api/weekly-review", timeout=60).status_code == 200
        assert s.get(f"{BASE}/api/timeline", timeout=15).status_code == 200
        assert s.get(f"{BASE}/api/timeline?kind=task", timeout=15).status_code == 200
        assert s.get(f"{BASE}/api/courses", timeout=15).status_code == 200
        assert s.get(f"{BASE}/api/courses/SOC", timeout=15).status_code == 200
        assert s.get(f"{BASE}/api/review", timeout=15).status_code == 200

# -------------------- 6. RELIABILITY --------------------
class TestReliability:
    def test_capture_creates_commitment_ledger_reminder(self):
        s, _, _ = _mk_user("rel_cap")
        r = s.post(f"{BASE}/api/capture",
                   json={"text": "Assignment 3 due tomorrow at 5pm"}, timeout=60)
        assert r.status_code == 200

        commits = s.get(f"{BASE}/api/commitments", timeout=15).json()
        assert len(commits) >= 1
        # some should be scheduled after commit_item ran
        assert any(c.get("state") == "scheduled" for c in commits) or any(c.get("state") == "detected" for c in commits)

        ledger = s.get(f"{BASE}/api/ledger", timeout=15).json()
        assert len(ledger) >= 1  # transition entries present

        rems = s.get(f"{BASE}/api/reminders", timeout=15).json()
        # A reminder may have been created if the item was auto-committed with a datetime
        # (either way endpoint returns 200 and a list)
        assert isinstance(rems, list)

    def test_reminder_lifecycle(self):
        s, _, _ = _mk_user("rel_rem")
        rc = s.post(f"{BASE}/api/reminders",
                    json={"title": "TR", "remind_at": "2030-01-01T10:00:00+00:00"}, timeout=15)
        assert rc.status_code == 200
        rid = rc.json()["id"]

        # delivered
        r = s.post(f"{BASE}/api/reminders/{rid}/status",
                   json={"status": "delivered", "external_id": "ext-1"}, timeout=15)
        assert r.status_code == 200 and r.json()["status"] == "delivered"

        # snoozed: create a fresh reminder for snooze so we don't mix states
        rc2 = s.post(f"{BASE}/api/reminders",
                     json={"title": "TR2", "remind_at": "2030-01-01T10:00:00+00:00"}, timeout=15)
        rid2 = rc2.json()["id"]
        r = s.post(f"{BASE}/api/reminders/{rid2}/status",
                   json={"status": "snoozed", "snooze_until": "2030-01-01T11:00:00+00:00"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] in ("scheduled", "snoozed")
        assert "2030-01-01T11" in r.json().get("remind_at", "")

        # failed retries
        rc3 = s.post(f"{BASE}/api/reminders",
                     json={"title": "TR3", "remind_at": "2030-01-01T10:00:00+00:00"}, timeout=15)
        rid3 = rc3.json()["id"]
        last = None
        for i in range(3):
            r = s.post(f"{BASE}/api/reminders/{rid3}/status", json={"status": "failed"}, timeout=15)
            assert r.status_code == 200
            last = r.json()
        assert last.get("status") == "failed"
        assert (last.get("retry_count") or 0) >= 3

    def test_reminders_sync_and_health(self):
        s, _, _ = _mk_user("rel_sync")
        r = s.get(f"{BASE}/api/reminders/sync", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("reminders", "routines", "quiet_hours", "server_time"):
            assert k in d
        r = s.get(f"{BASE}/api/reminders/health", timeout=15)
        assert r.status_code == 200 and "counts" in r.json()

# -------------------- 7. CALENDAR --------------------
class TestCalendar:
    def test_pending_sync_unlink(self):
        s, _, _ = _mk_user("cal")
        rc = s.post(f"{BASE}/api/events", json={"title": "Sync me", "event_type": "meeting",
                                                "start": "2030-07-01T10:00:00+00:00"}, timeout=15)
        eid = rc.json()["id"]
        pending = s.get(f"{BASE}/api/calendar/pending", timeout=15).json()
        assert any(e["id"] == eid for e in pending)

        r = s.post(f"{BASE}/api/calendar/sync", json={"mappings": {eid: "ext-99"}}, timeout=15)
        assert r.status_code == 200 and r.json()["synced"] == 1

        pending2 = s.get(f"{BASE}/api/calendar/pending", timeout=15).json()
        assert not any(e["id"] == eid for e in pending2)

        r = s.post(f"{BASE}/api/calendar/unlink/{eid}", timeout=15)
        assert r.status_code == 200
        pending3 = s.get(f"{BASE}/api/calendar/pending", timeout=15).json()
        assert any(e["id"] == eid for e in pending3)

# -------------------- 8. CHUNKED UPLOAD --------------------
class TestChunkedUpload:
    def test_init_partial_complete_and_idempotent(self):
        s, _, _ = _mk_user("upl")
        auth_h = {"Authorization": s.headers["Authorization"]}
        r = requests.post(f"{BASE}/api/uploads/init",
                          headers={**auth_h, "Content-Type": "application/json"},
                          json={"filename": "a.m4a", "title": "T", "total_chunks": 2}, timeout=15)
        assert r.status_code == 200
        up_id = r.json()["upload_id"]

        # chunk 0
        r = requests.post(f"{BASE}/api/uploads/{up_id}/chunk",
                          headers=auth_h,
                          data={"index": "0"},
                          files={"file": ("c0.bin", b"AAAAAAAAAAAA", "application/octet-stream")}, timeout=15)
        assert r.status_code == 200

        # complete with only 1/2 -> 409
        r = requests.post(f"{BASE}/api/uploads/{up_id}/complete", headers=auth_h, timeout=15)
        assert r.status_code == 409, r.text

        # chunk 1
        r = requests.post(f"{BASE}/api/uploads/{up_id}/chunk",
                          headers=auth_h,
                          data={"index": "1"},
                          files={"file": ("c1.bin", b"BBBBBBBBBBBB", "application/octet-stream")}, timeout=15)
        assert r.status_code == 200

        # complete -- LIVE Whisper on fake bytes typically returns 503 (per spec: EXPECTED).
        r = requests.post(f"{BASE}/api/uploads/{up_id}/complete", headers=auth_h, timeout=90)
        if r.status_code == 200:
            d1 = r.json()
            assert d1.get("transcript_id") and "bytes" in d1
            # idempotent: repeat call returns same transcript_id
            r2 = requests.post(f"{BASE}/api/uploads/{up_id}/complete", headers=auth_h, timeout=30)
            assert r2.status_code == 200
            assert r2.json().get("transcript_id") == d1["transcript_id"]
        else:
            # per review_request: LIVE Whisper with fake audio bytes -> 503 EXPECTED, not a bug
            assert r.status_code == 503, f"expected 200 or 503, got {r.status_code}: {r.text}"

# -------------------- 9. IDEMPOTENCY --------------------
class TestIdempotency:
    def test_capture_idempotency(self):
        s, _, _ = _mk_user("idem")
        key = f"idem-{uuid.uuid4().hex[:10]}"
        body = {"text": "quiz next Tuesday at 3pm"}
        r1 = s.post(f"{BASE}/api/capture", json=body,
                    headers={"Idempotency-Key": key}, timeout=60)
        assert r1.status_code == 200, r1.text
        usage1 = s.get(f"{BASE}/api/ai-usage", timeout=15).json()["used"]

        r2 = s.post(f"{BASE}/api/capture", json=body,
                    headers={"Idempotency-Key": key}, timeout=60)
        assert r2.status_code == 200
        assert r2.json() == r1.json(), "idempotent replay must return identical body"

        usage2 = s.get(f"{BASE}/api/ai-usage", timeout=15).json()["used"]
        assert usage2 == usage1, f"replay should NOT increment ai-usage (was {usage1}, now {usage2})"

# -------------------- 10. DAILY AI CAP --------------------
class TestAICap:
    def test_daily_cap_429(self):
        s, _, _ = _mk_user("cap")
        # set daily limit to 1
        r = s.put(f"{BASE}/api/prefs", json={"daily_ai_limit": 1}, timeout=15)
        assert r.status_code == 200

        r1 = s.post(f"{BASE}/api/capture", json={"text": "meeting Monday 9am"},
                    headers={"Idempotency-Key": f"cap-1-{uuid.uuid4().hex[:6]}"}, timeout=60)
        assert r1.status_code == 200, r1.text

        r2 = s.post(f"{BASE}/api/capture", json={"text": "another meeting"},
                    headers={"Idempotency-Key": f"cap-2-{uuid.uuid4().hex[:6]}"}, timeout=60)
        assert r2.status_code == 429, r2.text
        assert "limit" in r2.text.lower()

        # restore
        s.put(f"{BASE}/api/prefs", json={"daily_ai_limit": 150}, timeout=15)
        r = s.get(f"{BASE}/api/ai-usage", timeout=15).json()
        for k in ("used", "limit", "remaining"):
            assert k in r, f"missing {k} in {r}"

# -------------------- 11. PREFS / EXPORT / DELETE --------------------
class TestPrefsExportDelete:
    def test_prefs_export_delete(self):
        s, body, _ = _mk_user("acc")
        # put prefs
        r = s.put(f"{BASE}/api/prefs", json={"morning_time": "08:15"}, timeout=15)
        assert r.status_code == 200 and r.json().get("morning_time") == "08:15"
        r = s.get(f"{BASE}/api/prefs", timeout=15)
        assert r.status_code == 200 and r.json().get("morning_time") == "08:15"

        # export must include commitments/ledger/reminders keys
        r = s.get(f"{BASE}/api/export", timeout=20)
        assert r.status_code == 200
        exp = r.json()
        for k in ("commitments", "ledger", "reminders", "tasks", "events"):
            assert k in exp, f"export missing {k}"

        # delete /me -> 200 and refresh becomes 401
        r = s.delete(f"{BASE}/api/me", timeout=15)
        assert r.status_code == 200
        r = requests.post(f"{BASE}/api/auth/refresh",
                          json={"refresh_token": body["refresh_token"]}, timeout=15)
        assert r.status_code == 401

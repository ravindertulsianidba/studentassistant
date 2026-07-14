"""V3 production hardening tests: auth, isolation, security, AI 503 degradation, CRUD."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://semester-sync-7.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def user_a(s):
    email = f"TEST_user_a_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/dev-login", json={"email": email}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, **data}


@pytest.fixture(scope="module")
def user_b(s):
    email = f"TEST_user_b_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/dev-login", json={"email": email}, timeout=15)
    assert r.status_code == 200, r.text
    return {"email": email, **r.json()}


def h(u):
    return {"Authorization": f"Bearer {u['access_token']}"}


# ---------- Health ----------
class TestHealth:
    def test_health(self, s):
        r = s.get(f"{API}/health", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        # config-dependent flags: just assert they are present booleans + provider set
        assert isinstance(d["ai_configured"], bool)
        assert isinstance(d["google_configured"], bool)
        assert d["ai_provider"] in ("openai", "fixture")


# ---------- Auth ----------
class TestAuth:
    def test_unauth_tasks(self, s):
        assert s.get(f"{API}/tasks", timeout=10).status_code == 401

    def test_unauth_events(self, s):
        assert s.get(f"{API}/events", timeout=10).status_code == 401

    def test_unauth_briefing(self, s):
        assert s.get(f"{API}/briefing", timeout=10).status_code == 401

    def test_unauth_timeline(self, s):
        assert s.get(f"{API}/timeline", timeout=10).status_code == 401

    def test_unauth_me(self, s):
        assert s.get(f"{API}/me", timeout=10).status_code == 401

    def test_dev_login_returns_tokens(self, user_a):
        assert "access_token" in user_a
        assert "refresh_token" in user_a
        assert user_a["user"]["email"] == user_a["email"]

    def test_me_with_bearer(self, s, user_a):
        r = s.get(f"{API}/me", headers=h(user_a), timeout=10)
        assert r.status_code == 200
        assert r.json()["email"] == user_a["email"]

    def test_refresh_rotates(self, s, user_a):
        # do a dedicated refresh flow using a fresh login so we don't invalidate user_a
        email = f"TEST_refresh_{uuid.uuid4().hex[:8]}@example.com"
        u = s.post(f"{API}/auth/dev-login", json={"email": email}, timeout=10).json()
        r = s.post(f"{API}/auth/refresh", json={"refresh_token": u["refresh_token"]}, timeout=10)
        assert r.status_code == 200
        new = r.json()
        assert new["access_token"] != u["access_token"]
        # old refresh should now be revoked
        r2 = s.post(f"{API}/auth/refresh", json={"refresh_token": u["refresh_token"]}, timeout=10)
        assert r2.status_code == 401

    def test_logout_revokes(self, s):
        email = f"TEST_logout_{uuid.uuid4().hex[:8]}@example.com"
        u = s.post(f"{API}/auth/dev-login", json={"email": email}, timeout=10).json()
        r = s.post(f"{API}/auth/logout", json={"refresh_token": u["refresh_token"]}, timeout=10)
        assert r.status_code == 200
        # subsequent refresh with same token fails
        r2 = s.post(f"{API}/auth/refresh", json={"refresh_token": u["refresh_token"]}, timeout=10)
        assert r2.status_code == 401


# ---------- Data Isolation ----------
class TestIsolation:
    def test_task_isolation(self, s, user_a, user_b):
        # A creates a task
        r = s.post(f"{API}/tasks", headers=h(user_a),
                   json={"title": "TEST_A_only_task", "course": "CS101"}, timeout=10)
        assert r.status_code == 200
        tid = r.json()["id"]

        # A sees it
        la = s.get(f"{API}/tasks", headers=h(user_a), timeout=10).json()
        assert any(t["id"] == tid for t in la)

        # B does NOT see it
        lb = s.get(f"{API}/tasks", headers=h(user_b), timeout=10).json()
        assert all(t["id"] != tid for t in lb)

        # B cannot patch A's task
        rp = s.patch(f"{API}/tasks/{tid}", headers=h(user_b),
                     json={"title": "hacked"}, timeout=10)
        assert rp.status_code == 404

        # B delete → returns ok but must NOT actually delete
        s.delete(f"{API}/tasks/{tid}", headers=h(user_b), timeout=10)
        la2 = s.get(f"{API}/tasks", headers=h(user_a), timeout=10).json()
        assert any(t["id"] == tid for t in la2), "Task must survive B's delete"

    def test_event_isolation(self, s, user_a, user_b):
        r = s.post(f"{API}/events", headers=h(user_a),
                   json={"title": "TEST_A_only_event", "event_type": "personal"}, timeout=10)
        assert r.status_code == 200
        eid = r.json()["id"]
        la = s.get(f"{API}/events", headers=h(user_a), timeout=10).json()
        lb = s.get(f"{API}/events", headers=h(user_b), timeout=10).json()
        assert any(e["id"] == eid for e in la)
        assert all(e["id"] != eid for e in lb)

    def test_source_isolation(self, s, user_a, user_b):
        # A cannot query a random source, and B cannot query A's (we simulate with a random id)
        random_id = str(uuid.uuid4())
        assert s.get(f"{API}/source/{random_id}", headers=h(user_a), timeout=10).status_code == 404
        assert s.get(f"{API}/source/{random_id}", headers=h(user_b), timeout=10).status_code == 404

    def test_export_scoped(self, s, user_a, user_b):
        # A creates a marker task
        marker = f"TEST_export_marker_{uuid.uuid4().hex[:6]}"
        s.post(f"{API}/tasks", headers=h(user_a), json={"title": marker}, timeout=10)
        ea = s.get(f"{API}/export", headers=h(user_a), timeout=10).json()
        eb = s.get(f"{API}/export", headers=h(user_b), timeout=10).json()
        assert any(t.get("title") == marker for t in ea.get("tasks", []))
        assert not any(t.get("title") == marker for t in eb.get("tasks", []))

    def test_courses_scoped(self, s, user_a, user_b):
        s.post(f"{API}/tasks", headers=h(user_a), json={"title": "TEST_c", "course": "COURSE_A_ONLY"}, timeout=10)
        ca = s.get(f"{API}/courses", headers=h(user_a), timeout=10).json()
        cb = s.get(f"{API}/courses", headers=h(user_b), timeout=10).json()
        assert any(c["name"] == "COURSE_A_ONLY" for c in ca)
        assert not any(c["name"] == "COURSE_A_ONLY" for c in cb)


# ---------- Security ----------
class TestSecurity:
    def test_wipe_removed(self, s):
        r = s.delete(f"{API}/wipe", timeout=10)
        assert r.status_code in (404, 405)

    def test_delete_me(self, s):
        email = f"TEST_delete_{uuid.uuid4().hex[:8]}@example.com"
        u = s.post(f"{API}/auth/dev-login", json={"email": email}, timeout=10).json()
        # create data
        s.post(f"{API}/tasks", headers=h(u), json={"title": "TEST_will_be_deleted"}, timeout=10)
        r = s.delete(f"{API}/me", headers=h(u), timeout=10)
        assert r.status_code == 200
        # refresh must now fail (sessions revoked)
        # NOTE: refresh_tokens are deleted, so this refresh should fail
        rr = s.post(f"{API}/auth/refresh", json={"refresh_token": u["refresh_token"]}, timeout=10)
        assert rr.status_code == 401

    def test_import_oversized(self, s, user_a):
        # Bigger than 25MB threshold * 1.4 factor. Send ~40MB base64 to exceed comfortably.
        big = "A" * (40 * 1024 * 1024)
        r = s.post(f"{API}/import", headers=h(user_a),
                   json={"image_base64": big}, timeout=60)
        assert r.status_code == 413

    def test_rate_limit_dev_login(self):
        # limit is 40/min for auth bucket per pod. Behind ingress there may be
        # multiple pods, so we fire a large burst without keep-alive so at least
        # one pod trips the limit.
        codes = []
        for i in range(120):
            r = requests.post(f"{API}/auth/dev-login",
                              json={"email": f"TEST_rl_{i}_{uuid.uuid4().hex[:4]}@example.com"},
                              timeout=10, headers={"Connection": "close"})
            codes.append(r.status_code)
        assert 429 in codes, f"Expected a 429, got codes: {set(codes)}"


# ---------- AI endpoints degrade gracefully (never 500) ----------
# Historically these asserted 503 (dead key). AI is now a working dependency
# with a deterministic fixture fallback, so we assert graceful handling: a
# success or a clean 503 — never a 500/uncaught error.
class TestAI503:
    def test_capture_ok_or_503(self, s, user_a):
        r = s.post(f"{API}/capture", headers=h(user_a), json={"text": "read chapter 3 by Friday"}, timeout=30)
        assert r.status_code in (200, 503), r.text

    def test_import_text_ok_or_503(self, s, user_a):
        r = s.post(f"{API}/import", headers=h(user_a),
                   json={"text": "syllabus content, assignment due Sept 15"}, timeout=30)
        assert r.status_code in (200, 503), r.text

    def test_notes_generate_ok_or_503(self, s, user_a):
        r = s.post(f"{API}/notes/generate", headers=h(user_a),
                   json={"title": "L1", "transcript": "hello world lecture content"}, timeout=30)
        assert r.status_code in (200, 503), r.text

    def test_search_503(self, s, user_a):
        # Need to first ensure there are chunks with the term, otherwise search short-circuits
        # to a non-AI answer. Create a note isn't possible without AI, so we insert via /capture...
        # Simpler: hit search with a common term after creating a task (add_chunks needs source_doc).
        # Use a query that likely finds nothing so returns the graceful message, then verify AI is not required.
        # Instead: Provide a query with a term that DOES exist by creating a task via /tasks
        # But /tasks doesn't call add_chunks. So the chunks collection will be empty for this user
        # and the endpoint returns 200 with the "couldn't find" message (no AI call).
        # To test the AI 503 path, we need chunks. Easiest is skip if no chunks yield hits.
        r = s.post(f"{API}/search", headers=h(user_a), json={"query": "quantum"}, timeout=15)
        # Either 200 with fallback message (if no chunks) OR 503 (if chunks exist and AI called)
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            assert "couldn't find" in r.json().get("answer", "").lower()

    def test_transcribe_ok_or_503(self, s, user_a):
        files = {"file": ("audio.m4a", b"fake-audio-bytes", "audio/mp4")}
        r = s.post(f"{API}/transcribe", headers=h(user_a), files=files, timeout=30)
        assert r.status_code in (200, 503), r.text


# ---------- Non-AI CRUD ----------
class TestCRUD:
    def test_task_crud_flow(self, s, user_a):
        r = s.post(f"{API}/tasks", headers=h(user_a),
                   json={"title": "TEST_crud_task", "course": "CS201"}, timeout=10)
        assert r.status_code == 200
        tid = r.json()["id"]

        # list status=open
        lst = s.get(f"{API}/tasks?status=open", headers=h(user_a), timeout=10).json()
        assert any(t["id"] == tid and t["status"] == "open" for t in lst)

        # patch status=done
        rp = s.patch(f"{API}/tasks/{tid}", headers=h(user_a),
                     json={"status": "done"}, timeout=10)
        assert rp.status_code == 200
        assert rp.json()["status"] == "done"

        # delete
        rd = s.delete(f"{API}/tasks/{tid}", headers=h(user_a), timeout=10)
        assert rd.status_code == 200

    def test_event_crud_flow(self, s, user_a):
        r = s.post(f"{API}/events", headers=h(user_a),
                   json={"title": "TEST_crud_event", "event_type": "class"}, timeout=10)
        assert r.status_code == 200
        eid = r.json()["id"]
        lst = s.get(f"{API}/events", headers=h(user_a), timeout=10).json()
        assert any(e["id"] == eid for e in lst)
        rd = s.delete(f"{API}/events/{eid}", headers=h(user_a), timeout=10)
        assert rd.status_code == 200

    def test_briefing(self, s, user_a):
        r = s.get(f"{API}/briefing", headers=h(user_a), timeout=10)
        assert r.status_code == 200
        d = r.json()
        for k in ("stats", "risks", "recommendation"):
            assert k in d
        assert set(["classes", "deadlines", "open_tasks", "review"]).issubset(d["stats"].keys())

    def test_courses_and_detail(self, s, user_a):
        s.post(f"{API}/tasks", headers=h(user_a), json={"title": "TEST_c2", "course": "CS_DETAIL"}, timeout=10)
        cs = s.get(f"{API}/courses", headers=h(user_a), timeout=10)
        assert cs.status_code == 200
        d = s.get(f"{API}/courses/CS_DETAIL", headers=h(user_a), timeout=10)
        assert d.status_code == 200
        body = d.json()
        assert body["name"] == "CS_DETAIL"
        for k in ("tasks", "events", "notes", "memory"):
            assert k in body

    def test_timeline_filters(self, s, user_a):
        r = s.get(f"{API}/timeline", headers=h(user_a), timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        r2 = s.get(f"{API}/timeline?kind=task", headers=h(user_a), timeout=10)
        assert r2.status_code == 200

    def test_evening_review(self, s, user_a):
        r = s.get(f"{API}/evening-review", headers=h(user_a), timeout=10)
        assert r.status_code == 200
        assert "unfinished" in r.json()

    def test_weekly_review(self, s, user_a):
        # May be 200 (fallback) since exception handler catches AI errors, or 503
        r = s.get(f"{API}/weekly-review", headers=h(user_a), timeout=15)
        assert r.status_code in (200, 503)

    def test_prefs_get_put(self, s, user_a):
        r = s.get(f"{API}/prefs", headers=h(user_a), timeout=10)
        assert r.status_code == 200
        r2 = s.put(f"{API}/prefs", headers=h(user_a),
                   json={"morning_time": "08:00", "auto_create_tasks": False}, timeout=10)
        assert r2.status_code == 200
        assert r2.json()["morning_time"] == "08:00"

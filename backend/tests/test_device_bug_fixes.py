"""
Tests for device-reported bug fixes (iteration 6):
1. Completed tasks can be reopened via PATCH status open<->done
2. Task edits (title/due/priority/category) via PATCH /api/tasks/{id}
3. Event edit (title/start) via NEW PATCH /api/events/{id}
4. Event delete via DELETE /api/events/{id}
5. Regressions: capture / import / briefing / reminders still return 200
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://semester-sync-7.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def auth_headers():
    email = f"TEST_{uuid.uuid4().hex[:8]}@uni.edu"
    r = requests.post(f"{API}/auth/dev-login", json={"email": email}, timeout=30)
    assert r.status_code == 200, f"dev-login failed: {r.status_code} {r.text}"
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- Bug #1: reopen completed task ----------------
class TestReopenTask:
    def test_reopen_flow(self, auth_headers):
        # Create
        r = requests.post(f"{API}/tasks", headers=auth_headers,
                          json={"title": "TEST_reopen", "due": "2027-05-01T09:00:00+00:00",
                                "priority": "normal", "category": "task"}, timeout=30)
        assert r.status_code == 200, r.text
        tid = r.json()["id"]

        # Mark done
        r = requests.patch(f"{API}/tasks/{tid}", headers=auth_headers,
                           json={"status": "done"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "done"

        # GET status=done → includes
        r = requests.get(f"{API}/tasks?status=done", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert any(t["id"] == tid for t in r.json()), "Completed task missing from status=done list"

        # Reopen
        r = requests.patch(f"{API}/tasks/{tid}", headers=auth_headers,
                           json={"status": "open"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("status") == "open"

        # GET status=open → includes
        r = requests.get(f"{API}/tasks?status=open", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert any(t["id"] == tid for t in r.json()), "Reopened task missing from status=open list"


# ---------------- Bug #2: edit task fields ----------------
class TestEditTaskFields:
    def test_update_all_fields(self, auth_headers):
        r = requests.post(f"{API}/tasks", headers=auth_headers,
                          json={"title": "TEST_orig", "priority": "normal", "category": "task"}, timeout=30)
        assert r.status_code == 200
        tid = r.json()["id"]

        payload = {"title": "TEST_edited", "due": "2027-04-01T09:00:00+00:00",
                   "priority": "high", "category": "exam"}
        r = requests.patch(f"{API}/tasks/{tid}", headers=auth_headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["title"] == "TEST_edited"
        assert body["priority"] == "high"
        assert body["category"] == "exam"
        assert body["due"].startswith("2027-04-01")


# ---------------- Bug #3: edit / delete event (NEW endpoint) ----------------
class TestEventPatchDelete:
    def test_patch_event(self, auth_headers):
        r = requests.post(f"{API}/events", headers=auth_headers,
                          json={"title": "TEST_ev", "event_type": "class",
                                "start": "2027-04-02T09:00:00+00:00",
                                "end": "2027-04-02T10:00:00+00:00"}, timeout=30)
        assert r.status_code == 200, r.text
        eid = r.json()["id"]

        r = requests.patch(f"{API}/events/{eid}", headers=auth_headers,
                           json={"title": "Moved", "start": "2027-04-02T11:00:00+00:00"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["title"] == "Moved"
        assert body["start"].startswith("2027-04-02T11")

    def test_delete_event(self, auth_headers):
        r = requests.post(f"{API}/events", headers=auth_headers,
                          json={"title": "TEST_del", "event_type": "meeting",
                                "start": "2027-04-05T09:00:00+00:00"}, timeout=30)
        eid = r.json()["id"]

        r = requests.delete(f"{API}/events/{eid}", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        r = requests.get(f"{API}/events", headers=auth_headers, timeout=30)
        assert not any(e["id"] == eid for e in r.json()), "Deleted event still returned"

    def test_patch_missing_event_returns_404(self, auth_headers):
        r = requests.patch(f"{API}/events/nonexistent-id", headers=auth_headers,
                           json={"title": "x"}, timeout=30)
        assert r.status_code == 404


# ---------------- Regression: capture / briefing / reminders ----------------
class TestOtherEndpointsRegression:
    def test_briefing_200(self, auth_headers):
        r = requests.get(f"{API}/briefing", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        assert "stats" in r.json()

    def test_reminders_list_200(self, auth_headers):
        r = requests.get(f"{API}/reminders", headers=auth_headers, timeout=30)
        assert r.status_code == 200

    def test_reminders_sync_200(self, auth_headers):
        r = requests.get(f"{API}/reminders/sync", headers=auth_headers, timeout=30)
        assert r.status_code == 200

    def test_capture_200(self, auth_headers):
        r = requests.post(f"{API}/capture", headers=auth_headers,
                          json={"text": "TEST_capture finish lab report Friday"}, timeout=90)
        assert r.status_code == 200, r.text

    def test_courses_200(self, auth_headers):
        r = requests.get(f"{API}/courses", headers=auth_headers, timeout=30)
        assert r.status_code == 200

    def test_timeline_200(self, auth_headers):
        r = requests.get(f"{API}/timeline?kind=all", headers=auth_headers, timeout=30)
        assert r.status_code == 200

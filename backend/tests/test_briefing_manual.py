"""Manual verification for review request items 2-6 (Phase 3 iteration-1)."""
import uuid
import datetime as dt
import requests
import os

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://semester-sync-7.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _tok():
    r = requests.post(f"{API}/auth/dev-login", json={"email": f"rr_{uuid.uuid4().hex[:8]}@uni.edu"}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}


def test_2_briefing_keys():
    """Item 2: GET /api/briefing?tz_offset_min=0 returns required keys."""
    h = _tok()
    r = requests.get(f"{API}/briefing?tz_offset_min=0", headers=h, timeout=20)
    assert r.status_code == 200, r.text
    b = r.json()
    for k in ["due_today", "overdue", "deadlines", "today_classes", "has_timed_events", "stats"]:
        assert k in b, f"missing key: {k}"
    for k in ["due_today", "overdue"]:
        assert k in b["stats"], f"missing stats.{k}"


def test_3_due_today_task():
    """Item 3: task due local-today -> due_today, NOT deadlines."""
    h = _tok()
    today = dt.datetime.now(dt.timezone.utc).date()
    due = f"{today.isoformat()}T00:00:00+00:00"
    r = requests.post(f"{API}/tasks", headers=h, json={"title": "GrassX", "due": due, "category": "task"}, timeout=15)
    assert r.status_code == 200, r.text
    b = requests.get(f"{API}/briefing?tz_offset_min=0", headers=h, timeout=15).json()
    assert "GrassX" in [t["title"] for t in b["due_today"]]
    assert "GrassX" not in [t["title"] for t in b["deadlines"]]


def test_4_overdue_and_tomorrow():
    """Item 4: 3-days-ago task overdue; tomorrow task in deadlines."""
    h = _tok()
    today = dt.datetime.now(dt.timezone.utc).date()
    past = today - dt.timedelta(days=3)
    tom = today + dt.timedelta(days=1)
    requests.post(f"{API}/tasks", headers=h, json={"title": "PastX", "due": f"{past.isoformat()}T00:00:00+00:00"}, timeout=15)
    requests.post(f"{API}/tasks", headers=h, json={"title": "TomX", "due": f"{tom.isoformat()}T00:00:00+00:00"}, timeout=15)
    b = requests.get(f"{API}/briefing?tz_offset_min=0", headers=h, timeout=15).json()
    assert "PastX" in [t["title"] for t in b["overdue"]]
    assert "PastX" not in [t["title"] for t in b["due_today"]]
    assert "TomX" in [t["title"] for t in b["deadlines"]]
    assert "TomX" not in [t["title"] for t in b["due_today"]]


def test_5_mark_done_disappears():
    """Item 5: PATCH task status=done -> disappears from due_today."""
    h = _tok()
    today = dt.datetime.now(dt.timezone.utc).date()
    due = f"{today.isoformat()}T00:00:00+00:00"
    r = requests.post(f"{API}/tasks", headers=h, json={"title": "DoneX", "due": due}, timeout=15)
    tid = r.json()["id"]
    b = requests.get(f"{API}/briefing?tz_offset_min=0", headers=h, timeout=15).json()
    assert "DoneX" in [t["title"] for t in b["due_today"]]
    pr = requests.patch(f"{API}/tasks/{tid}", headers=h, json={"status": "done"}, timeout=15)
    assert pr.status_code == 200, pr.text
    b2 = requests.get(f"{API}/briefing?tz_offset_min=0", headers=h, timeout=15).json()
    assert "DoneX" not in [t["title"] for t in b2["due_today"]]


def test_6_other_endpoints_no_500():
    """Item 6: capture / tasks / events / reminders still work (no 500s)."""
    h = _tok()
    # tasks
    r = requests.get(f"{API}/tasks", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    # events GET + POST
    r = requests.get(f"{API}/events", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    ev = requests.post(f"{API}/events", headers=h, json={"title": "EvX", "start": dt.datetime.now(dt.timezone.utc).isoformat(), "event_type": "personal"}, timeout=15)
    assert ev.status_code == 200, ev.text
    # capture
    cap = requests.post(f"{API}/capture", headers=h, json={"text": "remind me to buy milk tomorrow"}, timeout=30)
    assert cap.status_code in (200, 429), cap.text  # 429 if AI cap hit, but no 500
    # reminders
    r = requests.get(f"{API}/reminders", headers=h, timeout=15)
    assert r.status_code == 200, r.text

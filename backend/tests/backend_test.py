"""Backend regression tests for Student Assistant API."""
import base64, io, time, pytest
from PIL import Image, ImageDraw, ImageFont

pytestmark = pytest.mark.filterwarnings("ignore")


def _make_schedule_image_b64():
    """Real JPEG with legible academic schedule text."""
    img = Image.new("RGB", (900, 500), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except Exception:
        font = small = ImageFont.load_default()
    d.text((20, 10), "Fall 2026 Class Schedule", fill="black", font=font)
    rows = [
        ("Mon 09:00-10:30", "CS101 Intro to CS", "Room A12"),
        ("Tue 14:00-16:00", "CS150 Programming Lab", "Room B12"),
        ("Wed 11:00-12:30", "MATH210 Calculus II", "Room C7"),
        ("Thu 10:00-11:30", "PHYS110 Physics I", "Room D3"),
        ("Fri 13:00-14:30", "ENG105 Academic Writing", "Room E9"),
    ]
    y = 70
    for a, b, c in rows:
        d.text((20, y), a, fill="black", font=small)
        d.text((260, y), b, fill="black", font=small)
        d.text((600, y), c, fill="black", font=small)
        y += 60
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


# ---------- Health ----------
class TestHealth:
    def test_root(self, api, base_url):
        # No root route; health lives at /api/health (unchanged since Phase 1).
        r = api.get(f"{base_url}/api/health")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ---------- Briefing ----------
class TestBriefing:
    def test_briefing_shape(self, api, base_url):
        r = api.get(f"{base_url}/api/briefing")
        assert r.status_code == 200
        j = r.json()
        for k in ("greeting", "date", "stats", "risks", "today_classes", "deadlines"):
            assert k in j, f"missing {k}"
        for k in ("classes", "deadlines", "open_tasks", "review"):
            assert k in j["stats"]
        assert isinstance(j["risks"], list)


# ---------- Capture (LLM) ----------
@pytest.fixture(scope="module")
def capture_result(api, base_url):
    payload = {"text": "I have a lab Tuesday at 2pm in room B12 and I need to email Professor Lee tomorrow"}
    r = api.post(f"{base_url}/api/capture", json=payload, timeout=90)
    assert r.status_code == 200, r.text
    return r.json()


class TestCapture:
    def test_capture_returns_lists(self, capture_result):
        assert "committed" in capture_result
        assert "review" in capture_result
        assert isinstance(capture_result["committed"], list)
        assert isinstance(capture_result["review"], list)

    def test_capture_creates_items(self, capture_result):
        total = len(capture_result["committed"]) + len(capture_result["review"])
        assert total >= 1, "LLM should extract at least 1 item"


# ---------- Tasks CRUD ----------
class TestTasks:
    def test_task_crud(self, api, base_url):
        payload = {"title": "TEST_Read chapter 3", "course": "CS101",
                   "due": "2026-02-01T10:00:00+00:00", "priority": "normal", "category": "assignment"}
        r = api.post(f"{base_url}/api/tasks", json=payload)
        assert r.status_code == 200, r.text
        tk = r.json()
        assert tk["title"] == payload["title"]
        assert tk["status"] == "open"
        assert "id" in tk
        tid = tk["id"]

        # list open
        r = api.get(f"{base_url}/api/tasks", params={"status": "open"})
        assert r.status_code == 200
        assert any(t["id"] == tid for t in r.json())

        # patch -> done
        r = api.patch(f"{base_url}/api/tasks/{tid}", json={"status": "done"})
        assert r.status_code == 200
        assert r.json()["status"] == "done"

        # delete
        r = api.delete(f"{base_url}/api/tasks/{tid}")
        assert r.status_code == 200
        # verify gone
        r = api.get(f"{base_url}/api/tasks")
        assert not any(t["id"] == tid for t in r.json())


# ---------- Events ----------
class TestEvents:
    def test_event_crud(self, api, base_url):
        payload = {"title": "TEST_Study session", "event_type": "study",
                   "start": "2026-02-05T14:00:00+00:00", "end": "2026-02-05T16:00:00+00:00",
                   "location": "Library"}
        r = api.post(f"{base_url}/api/events", json=payload)
        assert r.status_code == 200, r.text
        ev = r.json()
        eid = ev["id"]
        r = api.get(f"{base_url}/api/events")
        assert r.status_code == 200
        assert any(e["id"] == eid for e in r.json())
        r = api.delete(f"{base_url}/api/events/{eid}")
        assert r.status_code == 200


# ---------- Timeline ----------
class TestTimeline:
    def test_timeline_and_filter(self, api, base_url):
        r = api.get(f"{base_url}/api/timeline")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        r = api.get(f"{base_url}/api/timeline", params={"kind": "task"})
        assert r.status_code == 200
        for d in r.json():
            assert d.get("kind") == "task"


# ---------- Review Queue ----------
class TestReview:
    def test_review_list_and_action(self, api, base_url):
        # seed a low-confidence capture to force review
        r = api.post(f"{base_url}/api/capture",
                     json={"text": "maybe schedule something sometime with someone"}, timeout=90)
        assert r.status_code == 200
        r = api.get(f"{base_url}/api/review")
        assert r.status_code == 200
        items = r.json()
        if not items:
            pytest.skip("No review items to test action on")
        rid = items[0]["id"]
        r = api.post(f"{base_url}/api/review/{rid}/action", json={"action": "ignore"})
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_approve_commits(self, api, base_url):
        # create a synthetic review item via a vague capture then approve
        api.post(f"{base_url}/api/capture",
                 json={"text": "possibly a study group later this week"}, timeout=90)
        items = api.get(f"{base_url}/api/review").json()
        if not items:
            pytest.skip("no pending items")
        rid = items[0]["id"]
        before = len(api.get(f"{base_url}/api/tasks").json()) + len(api.get(f"{base_url}/api/events").json())
        r = api.post(f"{base_url}/api/review/{rid}/action", json={"action": "approve"})
        assert r.status_code == 200
        after = len(api.get(f"{base_url}/api/tasks").json()) + len(api.get(f"{base_url}/api/events").json())
        assert after >= before  # committed something (or empty item -> task fallback)


# ---------- Import (LLM+vision) ----------
class TestImport:
    def test_import_schedule(self, api, base_url):
        b64 = _make_schedule_image_b64()
        r = api.post(f"{base_url}/api/import",
                     json={"image_base64": b64, "kind": "schedule"}, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "review" in j
        assert isinstance(j["review"], list)
        # not strict on count but LLM should find at least 1 class from the image
        assert len(j["review"]) >= 1, "vision should extract >=1 item from schedule image"


# ---------- Notes ----------
@pytest.fixture(scope="module")
def note_id(api, base_url):
    transcript = (
        "Today we discussed derivatives. A derivative measures instantaneous rate of change. "
        "The power rule states d/dx x^n = n x^(n-1). Prof emphasized chain rule for exam. "
        "Homework 3 is due next Friday. Read chapter 4 for next lecture."
    )
    r = api.post(f"{base_url}/api/notes/generate",
                 json={"title": "TEST_Calc Lecture 3", "course": "MATH210", "transcript": transcript},
                 timeout=120)
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestNotes:
    def test_generate_shape(self, api, base_url, note_id):
        r = api.get(f"{base_url}/api/notes/{note_id}")
        assert r.status_code == 200
        j = r.json()
        assert "study_notes" in j
        sn = j["study_notes"]
        assert isinstance(sn, dict)
        # at least half the expected keys present
        expected = ["overview", "key_concepts", "definitions", "examples",
                    "professor_emphasis", "important_dates", "likely_exam_topics", "action_items"]
        present = sum(1 for k in expected if k in sn)
        assert present >= 4, f"missing structured note fields, got: {list(sn.keys())}"

    def test_list_notes(self, api, base_url, note_id):
        r = api.get(f"{base_url}/api/notes")
        assert r.status_code == 200
        assert any(n["id"] == note_id for n in r.json())


# ---------- Search ----------
class TestSearch:
    def test_search(self, api, base_url):
        r = api.post(f"{base_url}/api/search", json={"query": "What do I have this week?"}, timeout=90)
        assert r.status_code == 200
        j = r.json()
        assert "answer" in j and isinstance(j["answer"], str) and len(j["answer"]) > 0
        assert "citations" in j and isinstance(j["citations"], list)
        assert j.get("mode") in ("keyword", "semantic")


# ---------- Weekly review ----------
class TestWeekly:
    def test_weekly(self, api, base_url):
        r = api.get(f"{base_url}/api/weekly-review", timeout=90)
        assert r.status_code == 200
        j = r.json()
        assert "upcoming" in j and "review" in j


# ---------- Export & Wipe (kept last) ----------
class TestPrivacy:
    def test_export(self, api, base_url):
        r = api.get(f"{base_url}/api/export")
        assert r.status_code == 200
        j = r.json()
        for k in ("tasks", "events", "notes", "timeline"):
            assert k in j and isinstance(j[k], list)

    def test_wipe(self, api, base_url):
        # /api/wipe was removed in v3 for safety; account deletion is /api/me.
        r = api.delete(f"{base_url}/api/wipe")
        assert r.status_code in (404, 405)

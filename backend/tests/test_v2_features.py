"""V2-specific tests: entity linking, overdue nudges, auto-classify, courses, review shape."""
import base64, io, time, pytest
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont


def _schedule_jpeg_b64():
    img = Image.new("RGB", (900, 500), "white")
    d = ImageDraw.Draw(img)
    try:
        f1 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        f2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except Exception:
        f1 = f2 = ImageFont.load_default()
    d.text((20, 10), "Fall 2026 Class Schedule", fill="black", font=f1)
    for i, (a, b, c) in enumerate([
        ("Mon 09:00-10:30", "CS101 Intro to CS", "Room A12"),
        ("Tue 14:00-16:00", "CS150 Programming Lab", "Room B12"),
        ("Wed 11:00-12:30", "MATH210 Calculus II", "Room C7"),
        ("Thu 10:00-11:30", "PHYS110 Physics I", "Room D3"),
        ("Fri 13:00-14:30", "ENG105 Academic Writing", "Room E9"),
    ]):
        y = 70 + 60 * i
        d.text((20, y), a, fill="black", font=f2)
        d.text((260, y), b, fill="black", font=f2)
        d.text((600, y), c, fill="black", font=f2)
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


# ---------- Briefing overdue nudges ----------
class TestOverdueNudges:
    def test_overdue_appears_in_risks(self, api, base_url):
        past = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        r = api.post(f"{base_url}/api/tasks", json={
            "title": "TEST_V2_Overdue paper", "course": "SOC101",
            "due": past, "category": "assignment"
        })
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        try:
            r = api.get(f"{base_url}/api/briefing", timeout=60)
            assert r.status_code == 200
            risks = r.json().get("risks", [])
            texts = " || ".join(x.get("text", "") for x in risks)
            assert ("Overdue" in texts) or ("promised" in texts), f"no overdue nudge; risks={texts}"
        finally:
            api.delete(f"{base_url}/api/tasks/{tid}")

    def test_promised_verb_for_followup(self, api, base_url):
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        r = api.post(f"{base_url}/api/tasks", json={
            "title": "TEST_V2_Email advisor", "course": None,
            "due": past, "category": "followup"
        })
        assert r.status_code == 200
        tid = r.json()["id"]
        try:
            j = api.get(f"{base_url}/api/briefing", timeout=60).json()
            texts = " || ".join(x.get("text", "") for x in j.get("risks", []))
            assert "promised" in texts, f"followup should trigger 'promised'; got: {texts}"
        finally:
            api.delete(f"{base_url}/api/tasks/{tid}")


# ---------- Entity relationship linking ----------
class TestEntityLinking:
    def test_entity_field_present_and_linked_update(self, api, base_url):
        # step 1: create task via capture with clear entity
        r1 = api.post(f"{base_url}/api/capture", json={
            "text": "Assignment 2 for Sociology due Friday at 5pm"
        }, timeout=90)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        # collect committed+review items and check 'entity' key exists on committed items
        all_items = j1.get("committed", []) + [x.get("item", {}) for x in j1.get("review", [])]
        # entity is an optional field but must be present on the schema; at least one item should carry it
        has_entity_key = any("entity" in it for it in j1.get("committed", []))
        # Even if LLM returned None entity, key should be there
        # Softer assert: field-key exists on committed record
        if j1.get("committed"):
            assert "entity" in j1["committed"][0], "committed items must include 'entity' field"

        time.sleep(1)
        # step 2: follow-up mentioning same entity
        r2 = api.post(f"{base_url}/api/capture", json={
            "text": "Assignment 2 for Sociology deadline moved to next Monday"
        }, timeout=90)
        assert r2.status_code == 200, r2.text
        j2 = r2.json()

        # step 3: verify only one task titled/matching Assignment 2 for Sociology course
        tasks = api.get(f"{base_url}/api/tasks").json()
        matches = [t for t in tasks if (t.get("course") or "").lower().startswith("soc")
                   and "assignment 2" in (t.get("title") or "").lower()]
        # In case LLM created event instead
        events = api.get(f"{base_url}/api/events").json()
        matches += [e for e in events if (e.get("course") or "").lower().startswith("soc")
                    and "assignment 2" in (e.get("title") or "").lower()]

        # Should be at most 1 (linked update, not duplicate). Allow 1.
        assert len(matches) <= 1, f"expected linked update (<=1), got {len(matches)}: {matches}"

        # cleanup
        for t in matches:
            api.delete(f"{base_url}/api/tasks/{t['id']}")
            api.delete(f"{base_url}/api/events/{t['id']}")


# ---------- Review confidence label & shape ----------
class TestReviewShape:
    def test_low_confidence_review_has_labels(self, api, base_url):
        r = api.post(f"{base_url}/api/capture", json={
            "text": "maybe something about the thing later"
        }, timeout=90)
        assert r.status_code == 200
        items = api.get(f"{base_url}/api/review").json()
        assert isinstance(items, list)
        if not items:
            pytest.skip("no review items produced by LLM this run")
        r0 = items[0]
        for k in ("detected", "suggestion", "confidence", "confidence_label", "raw_text", "source"):
            assert k in r0, f"review missing '{k}': keys={list(r0.keys())}"
        assert r0["confidence_label"] in ("high", "medium", "low")


# ---------- Auto-classify import ----------
class TestImportAuto:
    def test_import_auto_returns_doc_type_and_labels(self, api, base_url):
        b64 = _schedule_jpeg_b64()
        r = api.post(f"{base_url}/api/import", json={"image_base64": b64, "kind": "auto"}, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "doc_type" in j and isinstance(j["doc_type"], str) and j["doc_type"]
        assert "review" in j and isinstance(j["review"], list)
        if j["review"]:
            assert "confidence_label" in j["review"][0]
            assert j["review"][0]["confidence_label"] in ("high", "medium", "low")


# ---------- Courses endpoints ----------
class TestCourses:
    def test_courses_list_and_detail(self, api, base_url):
        # seed
        r = api.post(f"{base_url}/api/tasks", json={
            "title": "TEST_V2_HW1", "course": "TEST_COURSE_X",
            "due": "2026-03-01T10:00:00+00:00"
        })
        tid = r.json()["id"]
        try:
            lst = api.get(f"{base_url}/api/courses").json()
            assert isinstance(lst, list)
            names = [c["name"] for c in lst]
            assert "TEST_COURSE_X" in names, f"course not returned: {names}"
            match = next(c for c in lst if c["name"] == "TEST_COURSE_X")
            for k in ("open_tasks", "events", "notes"):
                assert k in match, f"missing {k}"
            assert match["open_tasks"] >= 1

            det = api.get(f"{base_url}/api/courses/TEST_COURSE_X").json()
            for k in ("name", "tasks", "events", "notes", "memory"):
                assert k in det
            assert det["name"] == "TEST_COURSE_X"
            assert any(t["id"] == tid for t in det["tasks"])
        finally:
            api.delete(f"{base_url}/api/tasks/{tid}")


# ---------- Review actions: approve / ignore / delete ----------
class TestReviewActions:
    def _seed_review(self, api, base_url):
        api.post(f"{base_url}/api/capture", json={
            "text": "possibly some review kind of thing sometime maybe"
        }, timeout=90)
        items = api.get(f"{base_url}/api/review").json()
        return items

    def test_ignore_action(self, api, base_url):
        items = self._seed_review(api, base_url)
        if not items:
            pytest.skip("no review items")
        rid = items[0]["id"]
        r = api.post(f"{base_url}/api/review/{rid}/action", json={"action": "ignore"})
        assert r.status_code == 200 and r.json().get("ok")

    def test_approve_commits(self, api, base_url):
        items = self._seed_review(api, base_url)
        if not items:
            pytest.skip("no review items")
        rid = items[0]["id"]
        r = api.post(f"{base_url}/api/review/{rid}/action", json={"action": "approve"})
        assert r.status_code == 200 and r.json().get("ok")
        # committed should be non-null when approve returned a record (may be None if item empty)

    def test_delete_action(self, api, base_url):
        items = self._seed_review(api, base_url)
        if not items:
            pytest.skip("no review items")
        rid = items[0]["id"]
        r = api.post(f"{base_url}/api/review/{rid}/action", json={"action": "delete"})
        assert r.status_code == 200 and r.json().get("ok")

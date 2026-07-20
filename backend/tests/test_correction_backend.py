"""Backend regression tests for the coordinated correction set.

Covers: manual entry (no AI, no quota), AI error sanitization, cached health
probe, Evening Review eligibility, email delivery observability (sanitized) and
secret redaction. Runs offline against the local Mongo (no live provider calls).
"""
import asyncio
import uuid
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

import server
import auth
import config
import ai_service
import mailer
import security_redaction
import reliability as rel
from db import db

TEST_UID = f"testcorr_{uuid.uuid4().hex[:10]}"

# Synchronous client for test assertions/cleanup — avoids motor event-loop
# conflicts with the TestClient's own loop.
_sync = MongoClient(config.MONGO_URL)
_sdb = _sync[config.DB_NAME]


def _ai_count_sync():
    from datetime import datetime, timezone
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = _sdb.ai_usage.find_one({"user_id": TEST_UID, "date": day})
    return (doc or {}).get("count", 0)


@pytest.fixture(scope="module")
def client():
    server.app.dependency_overrides[auth.get_current_user] = lambda: TEST_UID
    with TestClient(server.app) as c:
        yield c
    server.app.dependency_overrides.clear()
    for coll in ("tasks", "events", "notes", "reminders", "ai_usage", "timeline", "chunks", "review"):
        _sdb[coll].delete_many({"user_id": TEST_UID})


# ---------------- 1. Manual entry: works, never consumes AI quota ----------------
def test_manual_entry_no_ai_quota(client):
    before = _ai_count_sync()
    t = client.post("/api/tasks", json={"title": "Read chapter 4", "priority": "high"})
    assert t.status_code == 200, t.text
    e = client.post("/api/events", json={"title": "Study group", "start": "2026-08-01T15:00:00"})
    assert e.status_code == 200, e.text
    n = client.post("/api/notes", json={"title": "Lecture idea", "body": "outline"})
    assert n.status_code == 200 and n.json().get("manual") is True, n.text
    r = client.post("/api/reminders", json={"title": "Email prof", "remind_at": "2026-08-01T09:00:00"})
    assert r.status_code == 200, r.text
    after = _ai_count_sync()
    assert after == before, "manual creation must NOT consume AI quota"


# ---------------- 2. AI error sanitization ----------------
def test_ai_error_is_sanitized():
    for raw, expected in [
        (Exception("invalid_api_key: sk-abc"), "authentication_failure"),
        (Exception("You exceeded your insufficient_quota"), "quota_exceeded"),
        (Exception("Rate limit reached"), "rate_limited"),
        (Exception("connection error"), "network_failure"),
    ]:
        err = ai_service._ai_error(raw, "unit")
        assert isinstance(err, ai_service.AIError)
        assert err.category == expected
        msg = str(err).lower()
        for banned in ("openai", "api key", "invalid_api_key", "sk-", "quota exceeded — add"):
            assert banned not in msg
        assert str(err) == ai_service.USER_MESSAGE


def test_capture_ai_failure_refunds_quota(client, monkeypatch):
    async def boom(*a, **k):
        raise ai_service.AIError("processing_failure")
    monkeypatch.setattr(ai_service, "extract_json", boom)
    before = _ai_count_sync()
    res = client.post("/api/capture", json={"text": "I have an exam Friday"})
    assert res.status_code == 503
    body = res.json()
    assert body.get("ai_error") is True and body.get("error_category")
    txt = str(body).lower()
    for banned in ("openai", "api key", "invalid_api_key", "sk-"):
        assert banned not in txt
    after = _ai_count_sync()
    assert after == before, "technical AI failure must not permanently consume quota"


# ---------------- 3. Cached health probe ----------------
def test_health_probe_states():
    async def scenario():
        # configured + live (controlled)
        ai_service.set_live_status(True)
        s = await ai_service.get_live_status(ttl=999)
        assert s["ok"] is True and s["last_checked"]
        # configured but rejected
        ai_service.set_live_status(False, "authentication_failure")
        s = await ai_service.get_live_status(ttl=999)
        assert s["ok"] is False
        # cached: probe override should NOT be called again within ttl
        calls = {"n": 0}
        async def probe():
            calls["n"] += 1
            return True
        ai_service._probe_override = probe
        try:
            await ai_service.get_live_status(ttl=999, force=True)  # 1 call
            await ai_service.get_live_status(ttl=999)              # cached, no call
            assert calls["n"] == 1
            # timeout → not live
            async def timeout_probe():
                raise asyncio.TimeoutError()
            ai_service._probe_override = timeout_probe
            s = await ai_service.get_live_status(ttl=0, force=True)
            assert s["ok"] is False
        finally:
            ai_service._probe_override = None
    asyncio.run(scenario())


def test_health_endpoint_shape(client):
    ai_service.set_live_status(True)
    h = client.get("/api/health").json()
    assert "ai_configured" in h and "ai_live" in h and "ai_last_checked" in h


# ---------------- 4. Evening Review eligibility ----------------
def test_evening_review_eligibility(client):
    for coll in ("tasks", "events", "review"):
        _sdb[coll].delete_many({"user_id": TEST_UID})
    # empty account → not eligible → routines omit evening_review
    sync = client.get("/api/reminders/sync").json()
    assert sync["evening_review_eligible"] is False
    assert not any(r["key"] == "evening_review" for r in sync["routines"])
    # add a task due today → eligible
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    client.post("/api/tasks", json={"title": "Due now", "due": f"{today}T10:00:00"})
    sync2 = client.get("/api/reminders/sync").json()
    assert sync2["evening_review_eligible"] is True
    assert any(r["key"] == "evening_review" for r in sync2["routines"])


# ---------------- 5. Email delivery observability (sanitized) ----------------
def test_email_delivery_log_is_sanitized():
    _sdb.email_delivery_log.delete_many({"message_type": "unittest"})
    asyncio.run(mailer._record_delivery("unittest", "someone@Example.COM", "accepted", 1, 0, 0))
    doc = _sdb.email_delivery_log.find_one({"message_type": "unittest"})
    assert doc is not None
    assert doc["recipient_domain"] == "example.com"
    assert doc["accepted_count"] == 1 and doc["rejected_count"] == 0
    blob = str(doc).lower()
    assert "someone@" not in blob
    _sdb.email_delivery_log.delete_many({"message_type": "unittest"})
    assert mailer._classify_smtp_exc(TimeoutError("timed out")) == "timeout"


# ---------------- 6. Secret redaction ----------------
def test_secret_redaction():
    r = security_redaction.redact
    assert "sk-" in r("key sk-ABC123456789") and "ABC123456789" not in r("key sk-ABC123456789")
    assert "[REDACTED]" in r("Authorization: Bearer abc.def.ghi")
    assert "[REDACTED]" in r("password=SuperSecret1")
    link = "https://app.example.com/reset-password?token=abcdef1234567890"
    out = r(link)
    assert "abcdef1234567890" not in out and "reset-password" in out

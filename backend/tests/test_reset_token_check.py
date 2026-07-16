"""Automated test: a reused reset token reports the invalid-link state via the
non-consuming /auth/check-reset-token endpoint that the reset screen calls on load.
This is the API contract the frontend relies on to hide the form before submission.
"""
import os
import sys
import asyncio
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.environ.get("TEST_BASE_URL", "http://localhost:8001")
API = BASE + "/api"
EMAIL = "reset-check-test@decisivlabs.invalid"


async def _mint_token():
    from routers.auth import _make_email_token
    from db import db
    await db.auth_tokens.delete_many({"email": EMAIL})
    return await _make_email_token(EMAIL, "reset_password", 1)


async def _consume(raw):
    from routers.auth import _consume_token
    return await _consume_token(raw, "reset_password")


async def _cleanup():
    from db import db
    await db.auth_tokens.delete_many({"email": EMAIL})


def _check(token):
    r = requests.post(f"{API}/auth/check-reset-token", json={"token": token}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def test_reused_reset_token_reports_invalid_before_submission():
    loop = asyncio.new_event_loop()
    try:
        raw = loop.run_until_complete(_mint_token())

        # Fresh token -> valid (form should render).
        fresh = _check(raw)
        assert fresh["valid"] is True and fresh["reason"] is None, fresh

        # Consume it once (simulates a completed reset).
        email, err = loop.run_until_complete(_consume(raw))
        assert email == EMAIL and err is None, (email, err)

        # Reused token -> invalid with reason 'used' (form must be hidden).
        reused = _check(raw)
        assert reused["valid"] is False and reused["reason"] == "used", reused

        # Garbage token -> invalid.
        junk = _check("not-a-real-token")
        assert junk["valid"] is False and junk["reason"] == "invalid", junk
    finally:
        loop.run_until_complete(_cleanup())
        loop.close()


if __name__ == "__main__":
    test_reused_reset_token_reports_invalid_before_submission()
    print("PASS — reused reset token reports invalid-link state before submission")

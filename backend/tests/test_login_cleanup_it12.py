"""
Iteration 12 — Auth-screen cleanup regression.
Verifies backend email/password flow (register -> dev-outbox -> verify -> login)
plus /auth/forgot-password and /auth/dev-login still function against the public preview URL.
"""
import os
import re
import time
import uuid
import pytest
import requests

BASE = os.environ["EXPO_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_BACKEND_URL") else "https://semester-sync-7.preview.emergentagent.com"
API = f"{BASE}/api"
PW = "correct horse battery staple"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture(scope="module")
def fresh_email():
    return f"tester+{int(time.time())}_{uuid.uuid4().hex[:6]}@uni.edu"


# ---- register / verify / login ----
class TestEmailPasswordFlow:
    def test_register(self, s, fresh_email):
        r = s.post(f"{API}/auth/register", json={"email": fresh_email, "password": PW, "full_name": "IT12 Tester"})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body.get("ok") is True or body.get("status") in ("pending", "sent") or "message" in body, body

    def test_verify_from_dev_outbox(self, s, fresh_email):
        r = s.get(f"{API}/auth/dev-outbox", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("live_smtp") is False
        msgs = data.get("messages", [])
        assert msgs, "dev-outbox has no messages"
        # find message addressed to our fresh email (last match)
        mine = [m for m in msgs if m.get("to", "").lower() == fresh_email.lower()]
        assert mine, f"no message for {fresh_email}"
        text = mine[-1].get("text") or mine[-1].get("html") or ""
        m = re.search(r"verify-email\?token=([A-Za-z0-9\-_\.]+)", text)
        assert m, f"no token in mail body: {text[:400]}"
        token = m.group(1)
        v = s.post(f"{API}/auth/verify-email", json={"token": token})
        assert v.status_code == 200, v.text

    def test_login_after_verify(self, s, fresh_email):
        r = s.post(f"{API}/auth/login", json={"email": fresh_email, "password": PW})
        assert r.status_code == 200, r.text
        body = r.json()
        # accept either session token or user object
        assert "user" in body or "token" in body or "session" in body, body

    def test_login_bad_password_is_401(self, s, fresh_email):
        r = s.post(f"{API}/auth/login", json={"email": fresh_email, "password": "wrong wrong wrong wrong"})
        assert r.status_code in (400, 401), r.status_code


# ---- forgot password ----
class TestForgotPassword:
    def test_forgot_generic_200(self, s, fresh_email):
        r = s.post(f"{API}/auth/forgot-password", json={"email": fresh_email})
        assert r.status_code == 200, r.text

    def test_forgot_unknown_email_generic_200(self, s):
        r = s.post(f"{API}/auth/forgot-password", json={"email": f"nobody+{uuid.uuid4().hex[:6]}@uni.edu"})
        assert r.status_code == 200, r.text


# ---- dev-login expected present in this preview (ALLOW_INSECURE_DEV=true) ----
class TestDevLoginPreview:
    def test_dev_login_still_available_in_preview(self, s):
        # Expected behavior per review context: ALLOW_INSECURE_DEV=true here, dev-login returns 200.
        r = s.post(f"{API}/auth/dev-login", json={"email": f"tester+devcheck_{uuid.uuid4().hex[:6]}@uni.edu"})
        # 200 expected; 429 acceptable (rate limiter) and treated as skip
        if r.status_code == 429:
            pytest.skip("rate-limited dev-login in preview")
        assert r.status_code == 200, r.text

"""Phase 3A email/password auth end-to-end tests.

Tests verify:
- Register + email verification flow via MockMailer/dev-outbox
- Login before/after verification, generic error messages
- Brute force lockout (5 wrong attempts -> 429)
- Forgot -> reset password revokes sessions (token_version bump)
- Password policy validation
- Email normalization, duplicate registration
- Two-user data isolation on /api/tasks and /api/timeline
- Google endpoint still present, dev-login available
"""
import os
import re
import time
import pytest
import requests

BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_PUBLIC_BACKEND_URL") else os.environ["EXPO_BACKEND_URL"].rstrip("/")
PASS = "correct horse battery staple"


def _uniq(prefix="tester"):
    return f"{prefix}+{int(time.time()*1000)}_{os.getpid()}@uni.edu"


@pytest.fixture
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _outbox(api):
    r = api.get(f"{BASE}/api/auth/dev-outbox")
    assert r.status_code == 200, r.text
    return r.json()


def _token_for(email, purpose, api, subject_pattern):
    email_l = (email or "").strip().lower()
    data = _outbox(api)
    for m in reversed(data.get("messages", [])):
        if m.get("to") == email_l and subject_pattern in m.get("subject", ""):
            match = re.search(r"token=([A-Za-z0-9_\-]+)", m.get("text", ""))
            if match:
                return match.group(1)
    return None


# -------------------- Registration + Verification --------------------

def test_register_sends_exactly_one_verification_email(api):
    email = _uniq()
    before = len([m for m in _outbox(api)["messages"] if m["to"] == email])
    r = api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS, "full_name": "Test User"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("verification_required") is True
    after = [m for m in _outbox(api)["messages"] if m["to"] == email and "Verify" in m["subject"]]
    assert len(after) - before == 1, f"Expected 1 new email, got {len(after)-before}"


def test_login_before_verification_returns_403(api):
    email = _uniq()
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    r = api.post(f"{BASE}/api/auth/login", json={"email": email, "password": PASS})
    assert r.status_code == 403, r.text


def test_verify_email_and_reuse_token_fails(api):
    email = _uniq()
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    tok = _token_for(email, "verify_email", api, "Verify")
    assert tok, "Verification token not found in mock outbox"
    r1 = api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    assert r1.status_code == 200, r1.text
    assert r1.json().get("verified") is True
    r2 = api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    assert r2.status_code == 400, r2.text


def test_verify_invalid_token_returns_400(api):
    r = api.post(f"{BASE}/api/auth/verify-email", json={"token": "not-a-real-token-xyz"})
    assert r.status_code == 400


def test_login_after_verification_returns_tokens(api):
    email = _uniq()
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    tok = _token_for(email, "verify_email", api, "Verify")
    api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    r = api.post(f"{BASE}/api/auth/login", json={"email": email, "password": PASS})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body and "refresh_token" in body and "user" in body
    assert body["user"]["email"] == email


def test_wrong_password_generic_401(api):
    email = _uniq()
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    tok = _token_for(email, "verify_email", api, "Verify")
    api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    r = api.post(f"{BASE}/api/auth/login", json={"email": email, "password": "wrongpass99"})
    assert r.status_code == 401
    assert r.json().get("detail") == "Invalid email or password."


def test_brute_force_lockout_returns_429(api):
    email = _uniq()
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    tok = _token_for(email, "verify_email", api, "Verify")
    api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    codes = []
    for _ in range(5):
        r = api.post(f"{BASE}/api/auth/login", json={"email": email, "password": "wrongpass99"})
        codes.append(r.status_code)
    # After 5 failures, next attempt should be locked
    r6 = api.post(f"{BASE}/api/auth/login", json={"email": email, "password": PASS})
    assert r6.status_code == 429, f"Expected 429 lockout, got {r6.status_code}. Prior codes={codes}"


# -------------------- Forgot/Reset password --------------------

def test_forgot_password_generic_ok(api):
    email = _uniq()
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    tok = _token_for(email, "verify_email", api, "Verify")
    api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    r = api.post(f"{BASE}/api/auth/forgot-password", json={"email": email})
    assert r.status_code == 200
    r2 = api.post(f"{BASE}/api/auth/forgot-password", json={"email": "nonexistent+xyz@uni.edu"})
    assert r2.status_code == 200


def test_reset_password_revokes_sessions_and_token_reuse_fails(api):
    email = _uniq()
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    tok_v = _token_for(email, "verify_email", api, "Verify")
    api.post(f"{BASE}/api/auth/verify-email", json={"token": tok_v})
    login = api.post(f"{BASE}/api/auth/login", json={"email": email, "password": PASS}).json()
    old_access = login["access_token"]
    old_refresh = login["refresh_token"]

    # Verify old access works
    me = api.get(f"{BASE}/api/me", headers={"Authorization": f"Bearer {old_access}"})
    assert me.status_code == 200

    api.post(f"{BASE}/api/auth/forgot-password", json={"email": email})
    reset_tok = _token_for(email, "reset_password", api, "Reset")
    assert reset_tok, "Reset token not captured"
    new_pass = PASS + "-v2"
    r = api.post(f"{BASE}/api/auth/reset-password", json={"token": reset_tok, "password": new_pass})
    assert r.status_code == 200

    # Old access token must be revoked (token_version bumped)
    me2 = api.get(f"{BASE}/api/me", headers={"Authorization": f"Bearer {old_access}"})
    assert me2.status_code == 401, f"Old access token still works after reset: {me2.status_code}"

    # Old refresh token must fail
    rref = api.post(f"{BASE}/api/auth/refresh", json={"refresh_token": old_refresh})
    assert rref.status_code == 401

    # Reusing reset token must fail
    rreuse = api.post(f"{BASE}/api/auth/reset-password", json={"token": reset_tok, "password": new_pass})
    assert rreuse.status_code == 400


# -------------------- Password policy --------------------

def test_weak_password_on_register_returns_422(api):
    r = api.post(f"{BASE}/api/auth/register", json={"email": _uniq(), "password": "short"})
    assert r.status_code == 422


def test_weak_password_on_reset_returns_422(api):
    email = _uniq()
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    tok = _token_for(email, "verify_email", api, "Verify")
    api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    api.post(f"{BASE}/api/auth/forgot-password", json={"email": email})
    reset_tok = _token_for(email, "reset_password", api, "Reset")
    r = api.post(f"{BASE}/api/auth/reset-password", json={"token": reset_tok, "password": "short"})
    assert r.status_code == 422


# -------------------- No enumeration / normalization --------------------

def test_duplicate_registration_of_verified_returns_generic_200(api):
    email = _uniq()
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    tok = _token_for(email, "verify_email", api, "Verify")
    api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    r = api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS + "-2"})
    assert r.status_code == 200
    body = r.json()
    # Generic action ok message - no account-existence leak
    assert "verification_required" in body or "message" in body


def test_email_normalization_mixed_case(api):
    email_lower = _uniq("normcase").lower()
    email_mixed = email_lower.replace("uni.edu", "Uni.EDU")
    email_mixed = email_mixed[:1].upper() + email_mixed[1:]
    api.post(f"{BASE}/api/auth/register", json={"email": email_mixed, "password": PASS})
    tok = _token_for(email_lower, "verify_email", api, "Verify")
    assert tok, f"Should capture email under normalized lowercase form {email_lower}"
    api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    r = api.post(f"{BASE}/api/auth/login", json={"email": email_mixed, "password": PASS})
    assert r.status_code == 200


# -------------------- Two-user data isolation --------------------

def _register_verify_login(api, email):
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    tok = _token_for(email, "verify_email", api, "Verify")
    api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    r = api.post(f"{BASE}/api/auth/login", json={"email": email, "password": PASS})
    return r.json()


def test_two_user_data_isolation(api):
    e1 = _uniq("userA")
    time.sleep(0.01)
    e2 = _uniq("userB")
    a = _register_verify_login(api, e1)
    time.sleep(0.05)
    b = _register_verify_login(api, e2)
    assert "access_token" in a, f"A login failed: {a}"
    assert "access_token" in b, f"B login failed: {b}"
    h1 = {"Authorization": f"Bearer {a['access_token']}"}
    h2 = {"Authorization": f"Bearer {b['access_token']}"}

    task_a = api.post(f"{BASE}/api/tasks", headers=h1,
                     json={"title": "TEST_taskA", "course": None}).json()
    task_b = api.post(f"{BASE}/api/tasks", headers=h2,
                     json={"title": "TEST_taskB", "course": None}).json()

    la = api.get(f"{BASE}/api/tasks", headers=h1).json()
    lb = api.get(f"{BASE}/api/tasks", headers=h2).json()
    la_ids = {t["id"] for t in (la if isinstance(la, list) else la.get("items", []))}
    lb_ids = {t["id"] for t in (lb if isinstance(lb, list) else lb.get("items", []))}
    assert task_a.get("id") in la_ids
    assert task_a.get("id") not in lb_ids
    assert task_b.get("id") in lb_ids
    assert task_b.get("id") not in la_ids

    ta = api.get(f"{BASE}/api/timeline", headers=h1).json()
    tb = api.get(f"{BASE}/api/timeline", headers=h2).json()
    ta_items = ta if isinstance(ta, list) else ta.get("items", [])
    tb_items = tb if isinstance(tb, list) else tb.get("items", [])
    # No cross-user timeline leakage
    for it in ta_items:
        assert "TEST_taskB" not in (it.get("title") or "")
    for it in tb_items:
        assert "TEST_taskA" not in (it.get("title") or "")


# -------------------- logout-all bumps token_version --------------------

def test_logout_all_revokes_old_access(api):
    email = _uniq()
    api.post(f"{BASE}/api/auth/register", json={"email": email, "password": PASS})
    tok = _token_for(email, "verify_email", api, "Verify")
    api.post(f"{BASE}/api/auth/verify-email", json={"token": tok})
    j = api.post(f"{BASE}/api/auth/login", json={"email": email, "password": PASS}).json()
    old_access = j["access_token"]
    r = api.post(f"{BASE}/api/auth/logout-all", headers={"Authorization": f"Bearer {old_access}"})
    assert r.status_code == 200
    me = api.get(f"{BASE}/api/me", headers={"Authorization": f"Bearer {old_access}"})
    assert me.status_code == 401


# -------------------- Google endpoint / dev-login --------------------

def test_google_endpoint_returns_401_on_invalid_token(api):
    r = api.post(f"{BASE}/api/auth/google", json={"id_token": "not-a-real-google-token"})
    assert r.status_code == 401, f"Expected 401, got {r.status_code} ({r.text})"


def test_dev_login_ok(api):
    r = api.post(f"{BASE}/api/auth/dev-login", json={"email": _uniq("dev")})
    assert r.status_code == 200
    assert "access_token" in r.json()

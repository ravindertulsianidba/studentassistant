import asyncio
from unittest.mock import patch

import config
from routers import billing


def run(coroutine):
    return asyncio.run(coroutine)


def test_oidc_fails_closed_without_audience(monkeypatch):
    monkeypatch.setattr(
        config,
        "PUBSUB_SERVICE_ACCOUNT_EMAIL",
        "student-assistant-pubsub-push@example.iam.gserviceaccount.com",
    )
    monkeypatch.setattr(config, "PUBSUB_AUDIENCE", "")

    with patch("google.oauth2.id_token.verify_oauth2_token") as verify:
        result = run(billing._verify_pubsub_oidc("test-token"))

    assert result is False
    verify.assert_not_called()


def test_oidc_validates_audience_and_email(monkeypatch):
    email = (
        "student-assistant-pubsub-push@"
        "studentassisstant-502413.iam.gserviceaccount.com"
    )
    audience = (
        "https://studentassistant-api.decisivlabs.com/"
        "api/billing/google/rtdn"
    )

    monkeypatch.setattr(config, "PUBSUB_SERVICE_ACCOUNT_EMAIL", email)
    monkeypatch.setattr(config, "PUBSUB_AUDIENCE", audience)

    claims = {
        "email": email,
        "email_verified": True,
        "aud": audience,
    }

    with patch(
        "google.oauth2.id_token.verify_oauth2_token",
        return_value=claims,
    ) as verify:
        result = run(billing._verify_pubsub_oidc("test-token"))

    assert result is True
    assert verify.call_args.kwargs["audience"] == audience


def test_oidc_rejects_wrong_email(monkeypatch):
    expected_email = (
        "student-assistant-pubsub-push@"
        "studentassisstant-502413.iam.gserviceaccount.com"
    )
    audience = (
        "https://studentassistant-api.decisivlabs.com/"
        "api/billing/google/rtdn"
    )

    monkeypatch.setattr(
        config,
        "PUBSUB_SERVICE_ACCOUNT_EMAIL",
        expected_email,
    )
    monkeypatch.setattr(config, "PUBSUB_AUDIENCE", audience)

    claims = {
        "email": "wrong-account@example.iam.gserviceaccount.com",
        "email_verified": True,
        "aud": audience,
    }

    with patch(
        "google.oauth2.id_token.verify_oauth2_token",
        return_value=claims,
    ):
        result = run(billing._verify_pubsub_oidc("test-token"))

    assert result is False

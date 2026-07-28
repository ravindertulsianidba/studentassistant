"""VPS-only email delivery diagnostic.

Sends ONE harmless test email to a specified address and prints sanitized SMTP
acceptance/rejection information. Never prints secrets, bodies, tokens or links.

    python -m admin_email_test --to someone@example.com

This does NOT read or print backend/.env values.
"""
import os
import sys
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mailer  # noqa: E402


async def _run(to: str):
    domain = to.rsplit("@", 1)[-1].lower() if "@" in to else "unknown"
    configured = mailer.smtp_configured()
    print(f"smtp_configured={configured} recipient_domain={domain} is_mock={getattr(mailer.mailer,'is_mock',False)}")
    if not configured and not getattr(mailer.mailer, "is_mock", False):
        print("result=unconfigured  detail=SMTP is not configured on this server.")
        return
    try:
        await mailer.send_tracked(
            "diagnostic", to,
            "GotU — delivery test",
            "This is a harmless delivery test from GotU. No action needed.",
            "<p>This is a harmless delivery test from GotU. No action needed.</p>",
        )
        print("result=accepted  detail=SMTP accepted the message for the recipient.")
    except Exception as e:
        # send_tracked already logged a sanitized category; surface only the type.
        print(f"result=failed  detail=delivery failed ({type(e).__name__}); check SMTP configuration and recipient domain.")


def main():
    p = argparse.ArgumentParser(prog="admin_email_test")
    p.add_argument("--to", required=True, help="recipient email address")
    a = p.parse_args()
    asyncio.run(_run(a.to))


if __name__ == "__main__":
    main()

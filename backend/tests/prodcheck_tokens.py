"""Deterministic single-use / reuse proof for email tokens (sanitized output only).
Exercises the SAME _make_email_token / _consume_token code path the live emails use,
without exposing any token value. Uses a throwaway email and cleans up after itself.
"""
import asyncio
from routers.auth import _make_email_token, _consume_token
from db import db

EMAIL = "logic-proof@decisivlabs.invalid"

async def prove(purpose: str, hours: int):
    raw = await _make_email_token(EMAIL, purpose, hours)
    email1, err1 = await _consume_token(raw, purpose)   # first use
    email2, err2 = await _consume_token(raw, purpose)   # reuse attempt
    first_ok = (email1 == EMAIL and err1 is None)
    reuse_blocked = (email2 is None and err2 == "used")
    print(f"[{purpose}] first-use={'PASS' if first_ok else 'FAIL'} "
          f"reuse-blocked={'PASS' if reuse_blocked else 'FAIL'} (reuse_reason={err2})")

async def main():
    await prove("verify_email", 24)
    await prove("reset_password", 1)
    await db.auth_tokens.delete_many({"email": EMAIL})
    print("cleanup done")

if __name__ == "__main__":
    asyncio.run(main())

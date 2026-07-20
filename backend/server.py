"""Student Assistant API — app assembly.

Business logic lives in `core.py`; request/response models in `models.py`;
endpoints are grouped under `routers/` (auth, content, planner, reliability).
This module only wires the app, middleware, exception handlers, health,
startup indexes and shutdown.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

import config
import ai_service
import vectorstore as vs
import security_redaction
from db import db, client
from core import now_iso, logger
from routers import auth, content, planner, reliability, calendar, listen, diagnostics, billing, monetization
import monetization as mon_svc
import retention

logging.getLogger("student-assistant")
security_redaction.install()

app = FastAPI(title="Student Assistant API")


@app.get("/api/health")
async def health():
    ok = True
    try:
        await db.command("ping")
    except Exception:
        ok = False
    # ai_configured = required config present. ai_live = a recent probe succeeded.
    # The probe result is CACHED (ttl) so we never call the provider on every request.
    ai_configured = (config.AI_PROVIDER == "fixture") or bool(config.OPENAI_API_KEY)
    live = {"ok": False, "last_checked": None}
    if ai_configured:
        try:
            live = await ai_service.get_live_status()
        except Exception:
            live = {"ok": False, "last_checked": None}
    return {"status": "ok" if ok else "degraded", "db": ok,
            "ai_provider": config.AI_PROVIDER,
            "ai_configured": ai_configured,
            "ai_live": bool(live.get("ok")),
            "ai_last_checked": live.get("last_checked"),
            "vector_search": vs.enabled(),
            "google_configured": bool(config.GOOGLE_CLIENT_ID),
            "time": now_iso()}


@app.exception_handler(ai_service.AIError)
async def ai_error(request: Request, exc: ai_service.AIError):
    # Sanitized: generic message + opaque category. No provider name/credential/model.
    return JSONResponse(status_code=503, content={
        "detail": ai_service.USER_MESSAGE, "error_category": exc.category, "ai_error": True})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


for r in (auth.router, content.router, planner.router, reliability.router, calendar.router,
          listen.router, diagnostics.router, billing.router, monetization.router):
    app.include_router(r)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS or ["http://localhost"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.on_event("startup")
async def startup():
    try:
        await db.users.create_index("google_sub", unique=True,
            partialFilterExpression={"google_sub": {"$exists": True, "$type": "string"}})
        await db.users.create_index("email", unique=True, sparse=True)
        await db.refresh_tokens.create_index("jti_hash", unique=True)
        await db.auth_tokens.create_index("token_hash", unique=True)
        await db.auth_tokens.create_index([("email", 1), ("purpose", 1), ("created_at", -1)])
        for coll in ["tasks", "events", "timeline", "review", "notes", "chunks",
                     "imports", "source_docs", "transcripts", "audit",
                     "commitments", "ledger", "reminders", "uploads"]:
            await db[coll].create_index("user_id")
        await db.chunks.create_index([("user_id", 1), ("source_type", 1)])
        await db.commitments.create_index([("user_id", 1), ("ref_id", 1)])
        await db.commitments.create_index([("user_id", 1), ("state", 1)])
        await db.reminders.create_index([("user_id", 1), ("status", 1)])
        await db.ledger.create_index([("user_id", 1), ("ts", -1)])
        await db.idempotency.create_index([("user_id", 1), ("key", 1)], unique=True)
        await db.ai_usage.create_index([("user_id", 1), ("date", 1)], unique=True)
        await db.upload_chunks.create_index([("upload_id", 1), ("index", 1)], unique=True)
        await db.calendar_connection.create_index("user_id", unique=True)
        await db.calendar_links.create_index([("user_id", 1), ("internal_id", 1)], unique=True)
        await db.calendar_links.create_index([("user_id", 1), ("external_id", 1)])
        await db.external_events.create_index([("user_id", 1), ("external_id", 1)], unique=True)
        await db.calendar_review.create_index([("user_id", 1), ("status", 1)])
        await db.listen_sessions.create_index([("user_id", 1), ("status", 1)])
        await db.listen_sessions.create_index([("user_id", 1), ("started_at", -1)])
        await db.device_state.create_index("user_id", unique=True)
        # Monetization / entitlement / cost indexes.
        await db.entitlements.create_index("user_id", unique=True)
        await db.usage_cycles.create_index([("user_id", 1), ("cycle_type", 1), ("cycle_start", 1)])
        # Migrate off the legacy plaintext-token index (tokens are now stored encrypted + hashed).
        try:
            await db.purchase_tokens.drop_index("purchase_token_1")
        except Exception:
            pass
        await db.purchase_tokens.create_index("purchase_token_hash", unique=True)
        await db.rtdn_events.create_index("message_id", unique=True)
        await db.cost_ledger.create_index([("user_id", 1), ("ts", -1)])
        await db.cost_ledger.create_index("ts")
        await db.usage_ledger.create_index([("user_id", 1), ("ts", -1)])
        await db.monetization_events.create_index([("kind", 1), ("ts", -1)])
        await db.subscription_audit.create_index([("user_id", 1), ("ts", -1)])
        await mon_svc.refresh_pricing()
        retention.start(app)
        billing.start_reconciliation(app)
        logger.info("Indexes ready. AI_PROVIDER=%s Vector=%s Google=%s Billing=%s",
                    config.AI_PROVIDER, vs.enabled(), bool(config.GOOGLE_CLIENT_ID), config.BILLING_ENABLED)
    except Exception as e:
        logger.warning("Index setup issue: %s", e)


@app.on_event("shutdown")
async def shutdown():
    client.close()

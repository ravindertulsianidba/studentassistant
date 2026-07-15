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
from db import db, client
from core import now_iso, logger
from routers import auth, content, planner, reliability

logging.getLogger("student-assistant")

app = FastAPI(title="Student Assistant API")


@app.get("/api/health")
async def health():
    ok = True
    try:
        await db.command("ping")
    except Exception:
        ok = False
    return {"status": "ok" if ok else "degraded", "db": ok,
            "ai_provider": config.AI_PROVIDER,
            "ai_configured": (config.AI_PROVIDER == "fixture") or bool(config.OPENAI_API_KEY),
            "ai_live": config.AI_PROVIDER == "openai" and bool(config.OPENAI_API_KEY),
            "vector_search": vs.enabled(),
            "google_configured": bool(config.GOOGLE_CLIENT_ID),
            "time": now_iso()}


@app.exception_handler(ai_service.AIError)
async def ai_error(request: Request, exc: ai_service.AIError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


for r in (auth.router, content.router, planner.router, reliability.router):
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
        await db.users.create_index("google_sub", unique=True, sparse=True)
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
        logger.info("Indexes ready. AI_PROVIDER=%s Vector=%s Google=%s",
                    config.AI_PROVIDER, vs.enabled(), bool(config.GOOGLE_CLIENT_ID))
    except Exception as e:
        logger.warning("Index setup issue: %s", e)


@app.on_event("shutdown")
async def shutdown():
    client.close()

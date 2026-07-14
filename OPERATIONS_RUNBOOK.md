# Operations Runbook — Student Assistant

## Services
`docker-compose.production.yml`: `mongo`, `backend` (FastAPI/uvicorn), `nginx` (TLS). Health: `GET /api/health` → `{status:"ok", db, ai_configured, google_configured}`.

## Common commands
```bash
docker compose -f docker-compose.production.yml ps
docker compose -f docker-compose.production.yml logs -f backend
docker compose -f docker-compose.production.yml restart backend
```

## Deploy / update / rollback
- Deploy: `bash deploy/deploy.sh`
- Update: `bash deploy/update.sh` (auto-backs up, rebuilds backend, health-checks)
- Rollback:
  ```bash
  git checkout <previous-tag>
  docker compose -f docker-compose.production.yml up -d --build backend
  # if data migration needed: bash deploy/restore.sh backups/<pre-update>.archive.gz
  ```

## Backups
- Nightly cron: `0 3 * * * cd /opt/student-assistant && bash deploy/backup.sh`
- Verify monthly by restoring into a scratch DB name.

## Incident playbook
| Symptom | Check | Fix |
|---|---|---|
| 503 on AI endpoints | `/api/health` `ai_configured:false` | set `OPENAI_API_KEY`, restart backend |
| 401 everywhere | JWT_SECRET changed | old sessions invalid; users re-login |
| Google login 503 | `google_configured:false` | set `GOOGLE_CLIENT_ID` |
| 429 responses | rate limiter | expected under abuse; tune limits in `server.py` |
| Mongo down | `docker compose ps` | `restart mongo`; restore from backup if corrupt |
| High memory | `docker stats` | lower uvicorn workers / Mongo cache |

## Rotating secrets
Update `backend/.env`, `restart backend`. Rotating `JWT_SECRET` signs users out (expected).

## Monitoring (recommended)
Add uptime check on `/api/health`; alert if `status!=ok` for >2 min. Ship Nginx logs to your log store; ensure no PII in app logs (errors are sanitized to generic messages).

#!/usr/bin/env bash
# First-time deploy on a clean Hostinger VPS. Run from repo root.
set -euo pipefail

echo "==> Student Assistant :: production deploy"

if [ ! -f backend/.env ]; then
  echo "!! backend/.env missing. Copy .env.example -> backend/.env and fill values."; exit 1
fi

# Basic secret sanity check
grep -q "CHANGE_ME" backend/.env && { echo "!! JWT_SECRET still placeholder"; exit 1; } || true
grep -q "^ALLOW_INSECURE_DEV=true" backend/.env && echo "WARNING: ALLOW_INSECURE_DEV=true (dev login enabled)."

docker compose -f docker-compose.production.yml pull || true
docker compose -f docker-compose.production.yml up -d --build

echo "==> Waiting for health..."
sleep 8
curl -fsS http://localhost:8001/api/health || (docker compose -f docker-compose.production.yml logs --tail=50 backend; exit 1)
echo "==> Deploy OK. Point Nginx/DNS to this host and run certbot (see HOSTINGER_DEPLOYMENT_GUIDE.md)."

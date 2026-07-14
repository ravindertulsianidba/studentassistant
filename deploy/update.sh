#!/usr/bin/env bash
# Zero-downtime-ish update: pull code, rebuild backend, keep DB volume.
set -euo pipefail
echo "==> Backing up before update"
bash deploy/backup.sh
echo "==> Pulling latest & rebuilding backend"
git pull --ff-only || echo "(skip git pull)"
docker compose -f docker-compose.production.yml up -d --build backend
sleep 6
curl -fsS http://localhost:8001/api/health && echo "==> Update OK" || {
  echo "!! Health failed — see rollback in OPERATIONS_RUNBOOK.md"; exit 1; }

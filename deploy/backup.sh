#!/usr/bin/env bash
# Mongo backup -> ./backups/backup-YYYYmmdd-HHMMSS.archive.gz
set -euo pipefail
DB=${DB_NAME:-student_assistant}
TS=$(date +%Y%m%d-%H%M%S)
mkdir -p backups
docker compose -f docker-compose.production.yml exec -T mongo \
  mongodump --db "$DB" --archive --gzip > "backups/backup-$TS.archive.gz"
echo "Backup written: backups/backup-$TS.archive.gz"
# Retain last 14
ls -1t backups/backup-*.archive.gz | tail -n +15 | xargs -r rm --

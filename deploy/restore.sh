#!/usr/bin/env bash
# Restore Mongo from an archive: ./deploy/restore.sh backups/backup-XX.archive.gz
set -euo pipefail
FILE=${1:?"usage: restore.sh <backup.archive.gz>"}
DB=${DB_NAME:-student_assistant}
echo "!! This will drop and restore DB '$DB' from $FILE"
read -p "Type 'yes' to continue: " ok; [ "$ok" = "yes" ] || exit 1
cat "$FILE" | docker compose -f docker-compose.production.yml exec -T mongo \
  mongorestore --db "$DB" --archive --gzip --drop
echo "Restore complete."

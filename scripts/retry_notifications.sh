#!/usr/bin/env bash
set -euo pipefail

# Добивка очереди Telegram-уведомлений задачника (повтор до успеха, в пределах часа).
# Cron: */3 * * * * /opt/automarks/automarks/scripts/retry_notifications.sh >> /var/log/notify_retry.log 2>&1

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "Neither 'docker compose' nor 'docker-compose' is available" >&2
  exit 1
fi

"${COMPOSE_CMD[@]}" exec -T web python manage.py retry_notifications

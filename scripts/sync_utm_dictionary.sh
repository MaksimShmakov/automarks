#!/usr/bin/env bash
set -euo pipefail

# Авто-sync справочника UTM (medium/source/campaign) из Google Sheet (CSV) в БД приложения.
# URL-адреса вкладок читаются из .env и передаются в контейнер флагами -e (без правки compose).
# Ставится в cron, напр.: 0 * * * * /opt/automarks/automarks/scripts/sync_utm_dictionary.sh >> /var/log/utm_sync.log 2>&1

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

set -a
# shellcheck disable=SC1091
source ./.env
set +a

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "Neither 'docker compose' nor 'docker-compose' is available" >&2
  exit 1
fi

"${COMPOSE_CMD[@]}" exec -T \
  -e UTM_DICTIONARY_MEDIUM_CSV_URL \
  -e UTM_DICTIONARY_SOURCE_CSV_URL \
  -e UTM_DICTIONARY_CAMPAIGN_CSV_URL \
  web python manage.py sync_utm_dictionary

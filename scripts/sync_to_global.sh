#!/usr/bin/env bash
set -euo pipefail

# Sync local Postgres (docker) -> global Postgres (remote)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

set -a
# shellcheck disable=SC1091
source ./.env
set +a

: "${GLOBAL_PGHOST:?}"
: "${GLOBAL_PGPORT:?}"
: "${GLOBAL_PGDB:?}"
: "${GLOBAL_PGUSER:?}"
: "${GLOBAL_PGPASSWORD:?}"

DUMP_FILE="/tmp/automarks_$(date +%F_%H%M).dump"

# Dump local DB from docker container
if ! docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges > "$DUMP_FILE"; then
  echo "pg_dump failed" >&2
  rm -f "$DUMP_FILE"
  exit 1
fi

# Restore into global DB (drops/recreates objects from the dump only)
docker run --rm   -e PGPASSWORD="$GLOBAL_PGPASSWORD"   -v /tmp:/tmp   postgres:16-alpine   pg_restore --clean --if-exists --no-owner --no-privileges   -h "$GLOBAL_PGHOST" -p "$GLOBAL_PGPORT" -U "$GLOBAL_PGUSER" -d "$GLOBAL_PGDB"   "$DUMP_FILE"

rm -f "$DUMP_FILE"

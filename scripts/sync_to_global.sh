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
: "${GLOBAL_PGSCHEMA:=activation_data}"

RAW_SQL="$(mktemp /tmp/automarks_raw_XXXX.sql)"
PATCHED_SQL="$(mktemp /tmp/automarks_patched_XXXX.sql)"
# TEMP: keep tmp files for debugging; remove after identifying failing statement

# Dump local DB from docker container (public schema only)
if ! docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"   -Fp --schema=public --no-owner --no-privileges --clean --if-exists > "$RAW_SQL"; then
  echo "pg_dump failed" >&2
  rm -f "$RAW_SQL"
  exit 1
fi

# Rewrite schema from public -> GLOBAL_PGSCHEMA
{
  cat <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '$GLOBAL_PGSCHEMA') THEN
    EXECUTE format('CREATE SCHEMA %I', '$GLOBAL_PGSCHEMA');
  END IF;
END
\$\$;
SET search_path = "$GLOBAL_PGSCHEMA";
SQL
  sed \
    -e "/^CREATE SCHEMA public;$/d" \
    -e "/^DROP SCHEMA public;$/d" \
    -e "/^DROP SCHEMA IF EXISTS public;$/d" \
    -e "/^ALTER SCHEMA public /d" \
    -e "/^COMMENT ON SCHEMA public /d" \
    -e "/^REVOKE .* ON SCHEMA public /d" \
    -e "/^GRANT .* ON SCHEMA public /d" \
    -e "s/\\<public\\./${GLOBAL_PGSCHEMA}./g" \
    -e "s/^SET search_path = public, pg_catalog;/SET search_path = \"${GLOBAL_PGSCHEMA}\", pg_catalog;/" \
    -e "s/^SET search_path = public;/SET search_path = \"${GLOBAL_PGSCHEMA}\";/" \
    "$RAW_SQL"
} > "$PATCHED_SQL"

# Restore into global DB
# Drops/recreates objects from the dump only, in GLOBAL_PGSCHEMA

docker run --rm \
  -e PGPASSWORD="$GLOBAL_PGPASSWORD" \
  -e PGSSLMODE="${GLOBAL_PGSSLMODE:-require}" \
  -v /tmp:/tmp \
  postgres:16-alpine \
  psql -h "$GLOBAL_PGHOST" -p "$GLOBAL_PGPORT" -U "$GLOBAL_PGUSER" -d "$GLOBAL_PGDB" \
  -v ON_ERROR_STOP=1 -f "$PATCHED_SQL"

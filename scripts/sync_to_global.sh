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
SOURCE_TABLES="$(mktemp /tmp/automarks_source_tables_XXXX.txt)"
SOURCE_COLUMNS_RAW="$(mktemp /tmp/automarks_source_columns_raw_XXXX.txt)"
SOURCE_COLUMN_KEYS="$(mktemp /tmp/automarks_source_column_keys_XXXX.txt)"
REMOTE_TABLES="$(mktemp /tmp/automarks_remote_tables_XXXX.txt)"
REMOTE_COLUMNS="$(mktemp /tmp/automarks_remote_columns_XXXX.txt)"
MISSING_TABLES="$(mktemp /tmp/automarks_missing_tables_XXXX.txt)"
MISSING_COLUMNS="$(mktemp /tmp/automarks_missing_columns_XXXX.txt)"
MISSING_SCHEMA_RAW="$(mktemp /tmp/automarks_missing_schema_raw_XXXX.sql)"
MISSING_SCHEMA_PATCHED="$(mktemp /tmp/automarks_missing_schema_patched_XXXX.sql)"
MISSING_COLUMNS_SQL="$(mktemp /tmp/automarks_missing_columns_XXXX.sql)"
cleanup() {
  rm -f \
    "$RAW_SQL" \
    "$PATCHED_SQL" \
    "$SOURCE_TABLES" \
    "$SOURCE_COLUMNS_RAW" \
    "$SOURCE_COLUMN_KEYS" \
    "$REMOTE_TABLES" \
    "$REMOTE_COLUMNS" \
    "$MISSING_TABLES" \
    "$MISSING_COLUMNS" \
    "$MISSING_SCHEMA_RAW" \
    "$MISSING_SCHEMA_PATCHED" \
    "$MISSING_COLUMNS_SQL"
}
trap cleanup EXIT

# Dump local DB data only from docker container (public schema only).
# We intentionally avoid --clean to keep dependent views in the global DB intact.
if ! docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -Fp --schema=public --data-only --no-owner --no-privileges > "$RAW_SQL"; then
  echo "pg_dump failed" >&2
  rm -f "$RAW_SQL"
  exit 1
fi

# Extract source table list from COPY commands.
awk '/^COPY public\./ {tbl=$2; sub(/^public\./, "", tbl); print tbl}' "$RAW_SQL" | sort -u > "$SOURCE_TABLES"

if [ ! -s "$SOURCE_TABLES" ]; then
  echo "No source tables found in dump; aborting" >&2
  exit 1
fi

# Fetch table list from remote schema.
docker run --rm \
  -e PGPASSWORD="$GLOBAL_PGPASSWORD" \
  -e PGSSLMODE="${GLOBAL_PGSSLMODE:-require}" \
  postgres:16-alpine \
  psql -h "$GLOBAL_PGHOST" -p "$GLOBAL_PGPORT" -U "$GLOBAL_PGUSER" -d "$GLOBAL_PGDB" \
  -At -c "SELECT tablename FROM pg_tables WHERE schemaname = '$GLOBAL_PGSCHEMA' ORDER BY 1;" > "$REMOTE_TABLES"

# Determine missing tables in remote schema.
comm -23 "$SOURCE_TABLES" "$REMOTE_TABLES" > "$MISSING_TABLES"

# Create only missing table structures (if any), preserving existing objects and views.
if [ -s "$MISSING_TABLES" ]; then
  mapfile -t missing_tables < "$MISSING_TABLES"
  TABLE_ARGS=()
  for table_name in "${missing_tables[@]}"; do
    TABLE_ARGS+=(--table="public.${table_name}")
  done

  if ! docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -Fp --schema-only --no-owner --no-privileges "${TABLE_ARGS[@]}" > "$MISSING_SCHEMA_RAW"; then
    echo "pg_dump (schema-only for missing tables) failed" >&2
    exit 1
  fi

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
      "$MISSING_SCHEMA_RAW"
  } > "$MISSING_SCHEMA_PATCHED"

  docker run --rm \
    -e PGPASSWORD="$GLOBAL_PGPASSWORD" \
    -e PGSSLMODE="${GLOBAL_PGSSLMODE:-require}" \
    -v /tmp:/tmp \
    postgres:16-alpine \
    psql -h "$GLOBAL_PGHOST" -p "$GLOBAL_PGPORT" -U "$GLOBAL_PGUSER" -d "$GLOBAL_PGDB" \
    -v ON_ERROR_STOP=1 -f "$MISSING_SCHEMA_PATCHED"
fi

# Build source column definitions from the local DB so remote tables can be extended
# when new Django migrations only add columns to already-synced tables.
if ! docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -AtF $'\t' -c "
SELECT
  cols.table_name,
  cols.column_name,
  format_type(attr.atttypid, attr.atttypmod) AS column_type
FROM information_schema.columns AS cols
JOIN pg_class AS cls
  ON cls.relname = cols.table_name
JOIN pg_namespace AS ns
  ON ns.oid = cls.relnamespace
 AND ns.nspname = cols.table_schema
JOIN pg_attribute AS attr
  ON attr.attrelid = cls.oid
 AND attr.attname = cols.column_name
 AND attr.attnum > 0
 AND NOT attr.attisdropped
WHERE cols.table_schema = 'public'
  AND cls.relkind IN ('r', 'p')
ORDER BY 1, 2;
" > "$SOURCE_COLUMNS_RAW"; then
  echo "psql failed while collecting local column metadata" >&2
  exit 1
fi

awk -F $'\t' '{print $1 "|" $2}' "$SOURCE_COLUMNS_RAW" | sort -u > "$SOURCE_COLUMN_KEYS"

docker run --rm \
  -e PGPASSWORD="$GLOBAL_PGPASSWORD" \
  -e PGSSLMODE="${GLOBAL_PGSSLMODE:-require}" \
  postgres:16-alpine \
  psql -h "$GLOBAL_PGHOST" -p "$GLOBAL_PGPORT" -U "$GLOBAL_PGUSER" -d "$GLOBAL_PGDB" \
  -At -c "SELECT cols.table_name || '|' || cols.column_name
FROM information_schema.columns AS cols
JOIN information_schema.tables AS tbls
  ON tbls.table_schema = cols.table_schema
 AND tbls.table_name = cols.table_name
WHERE cols.table_schema = '$GLOBAL_PGSCHEMA'
  AND tbls.table_type = 'BASE TABLE'
ORDER BY 1;" > "$REMOTE_COLUMNS"

comm -23 "$SOURCE_COLUMN_KEYS" "$REMOTE_COLUMNS" > "$MISSING_COLUMNS"

if [ -s "$MISSING_COLUMNS" ]; then
  {
    cat <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = '$GLOBAL_PGSCHEMA') THEN
    EXECUTE format('CREATE SCHEMA %I', '$GLOBAL_PGSCHEMA');
  END IF;
END
\$\$;
SQL
    awk -F $'\t' '
      NR == FNR {
        missing[$1] = 1
        next
      }
      {
        key = $1 "|" $2
        if (!(key in missing)) {
          next
        }

        table_name = $1
        column_name = $2
        column_type = $3

        gsub(/"/, "\"\"", table_name)
        gsub(/"/, "\"\"", column_name)

        printf "ALTER TABLE \"%s\".\"%s\" ADD COLUMN IF NOT EXISTS \"%s\" %s;\n", schema, table_name, column_name, column_type
      }
    ' schema="$GLOBAL_PGSCHEMA" "$MISSING_COLUMNS" "$SOURCE_COLUMNS_RAW"
  } > "$MISSING_COLUMNS_SQL"

  docker run --rm \
    -e PGPASSWORD="$GLOBAL_PGPASSWORD" \
    -e PGSSLMODE="${GLOBAL_PGSSLMODE:-require}" \
    -v /tmp:/tmp \
    postgres:16-alpine \
    psql -h "$GLOBAL_PGHOST" -p "$GLOBAL_PGPORT" -U "$GLOBAL_PGUSER" -d "$GLOBAL_PGDB" \
    -v ON_ERROR_STOP=1 -f "$MISSING_COLUMNS_SQL"
fi

# Build truncate list from source tables.
TRUNCATE_LIST="$(
  awk -v schema="$GLOBAL_PGSCHEMA" '{printf "%s\"%s\".\"%s\"", NR==1?"":", ", schema, $1}' "$SOURCE_TABLES"
)"

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
TRUNCATE TABLE ${TRUNCATE_LIST} RESTART IDENTITY CASCADE;
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
# Refreshes data in GLOBAL_PGSCHEMA without dropping table structure/views.

docker run --rm \
  -e PGPASSWORD="$GLOBAL_PGPASSWORD" \
  -e PGSSLMODE="${GLOBAL_PGSSLMODE:-require}" \
  -v /tmp:/tmp \
  postgres:16-alpine \
  psql -h "$GLOBAL_PGHOST" -p "$GLOBAL_PGPORT" -U "$GLOBAL_PGUSER" -d "$GLOBAL_PGDB" \
  -v ON_ERROR_STOP=1 -f "$PATCHED_SQL"

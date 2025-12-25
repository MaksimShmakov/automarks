#!/usr/bin/env bash
set -e

if [ -n "$POSTGRES_HOST" ]; then
  echo "Waiting for Postgres at $POSTGRES_HOST:$POSTGRES_PORT..."
  until python - <<'PYCODE'
import os, psycopg2, time
from psycopg2 import OperationalError
host=os.environ.get("POSTGRES_HOST")
port=int(os.environ.get("POSTGRES_PORT", "5432"))
db=os.environ.get("POSTGRES_DB")
user=os.environ.get("POSTGRES_USER")
pwd=os.environ.get("POSTGRES_PASSWORD")
for i in range(60):
    try:
        psycopg2.connect(host=host, port=port, dbname=db, user=user, password=pwd).close()
        print("Postgres is up!")
        break
    except OperationalError:
        time.sleep(1)
else:
    raise SystemExit("Postgres timeout")
PYCODE
  do
    sleep 1
  done
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 60

#!/usr/bin/env sh
set -e

if [ -z "$DOMAIN" ]; then
  echo "DOMAIN is not set. Exiting." >&2
  exit 1
fi

envsubst '${DOMAIN}' < /etc/nginx/templates/nginx.conf.template > /etc/nginx/nginx.conf
nginx -g 'daemon off;'


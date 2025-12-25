#!/bin/sh
set -e

while :; do
  certbot renew --webroot -w /var/www/certbot --quiet
  sleep 12h
done

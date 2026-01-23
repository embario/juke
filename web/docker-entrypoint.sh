#!/bin/sh

RUNTIME_ENV=${JUKE_RUNTIME_ENV:-development}
WEB_PORT=${WEB_PORT:?Set WEB_PORT}
BACKEND_PORT=${BACKEND_PORT:?Set BACKEND_PORT}

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

if [ "$RUNTIME_ENV" = "development" ]; then
  exec npm run dev -- --host 0.0.0.0 --port "$WEB_PORT"
fi

BUILD_SCRIPT="build:prod"
if [ "$RUNTIME_ENV" = "staging" ]; then
  BUILD_SCRIPT="build:staging"
fi

npm run "$BUILD_SCRIPT"

rm -rf /usr/share/nginx/html/*
cp -r dist/. /usr/share/nginx/html/

envsubst '$WEB_PORT $BACKEND_PORT' \
  < /etc/nginx/http.d/default.conf.template \
  > /etc/nginx/http.d/default.conf

exec nginx -g 'daemon off;'

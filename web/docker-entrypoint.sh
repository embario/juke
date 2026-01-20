#!/bin/sh

RUNTIME_ENV=${JUKE_RUNTIME_ENV:-development}
FRONTEND_PORT=${FRONTEND_PORT:-5173}

if [ "$#" -gt 0 ]; then
  exec "$@"
fi

if [ "$RUNTIME_ENV" = "development" ]; then
  exec npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
fi

BUILD_SCRIPT="build:prod"
if [ "$RUNTIME_ENV" = "staging" ]; then
  BUILD_SCRIPT="build:staging"
fi

npm run "$BUILD_SCRIPT"

rm -rf /usr/share/nginx/html/*
cp -r dist/. /usr/share/nginx/html/

exec nginx -g 'daemon off;'

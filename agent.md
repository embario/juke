# Juke Platform • Agent Handbook

This document orients AI agents to the entire repository. Each major subproject also carries its own `agent.md` for deep dives:

- [backend/agent.md](backend/agent.md)
- [mobile/android/agent.md](mobile/android/agent.md)
- [mobile/ios/agent.md](mobile/ios/agent.md)
- [mobile/ios/shotclock/ARCHITECTURE.md](mobile/ios/shotclock/ARCHITECTURE.md) — ShotClock (Power Hour) iOS app
- [web/agent.md](web/agent.md)

## High-Level Architecture

| Layer | Tech | Purpose |
| --- | --- | --- |
| Backend API | Django 4 + DRF, Celery, Redis, Postgres | User auth, catalog ingestion, playback control, recommendation orchestration. |
| Recommender Engine | FastAPI + Psycopg + NumPy | Embedding lookup + cosine similarity ranking, exposed at `/embed` and `/recommend`. |
| Web Console | React 18 + Vite + TypeScript | Analyst/operator UI, storybook-driven UI kit. |
| Mobile Apps | Native SwiftUI and Kotlin projects | End-user clients that hit the same API. |

The default `docker-compose.yml` wires Django (`backend`), Celery workers/beat, Redis, Postgres, the recommender-engine container, and the Vite-built frontend. `template.env` lists every shared env var (copy to `.env`).

## Key Paths

- Django apps: `catalog/`, `juke_auth/`, `recommender/` plus `settings/` for configuration and `tests/` for API/unit suites.
- ML service: `recommender_engine/app/main.py` describes FastAPI endpoints backed by Postgres embeddings.
- Frontend: `web/` (Vite project) with `web/src/features`, `shared`, `uikit`, etc.
- Mobile: `mobile/android/juke` (Gradle multi-module project) and `mobile/ios/juke` (Xcode workspace).
- Utility scripts: `scripts/` includes build helpers for both mobile platforms and log tailers.

## Common Workflows

1. **Bring up the stack**
   ```bash
   cp template.env .env  # fill secrets
   docker compose up --build
   ```
   - API → BACKEND_URL from `.env`
   - Web console → FRONTEND_URL from `.env`
   - Recommender engine → RECOMMENDER_ENGINE_BASE_URL from `.env`
2. **Celery tasks**
   - Workers + beat already run under compose. For a one-off worker: `docker compose run --rm worker celery -A settings.celery worker -l info`.
   - Genre sync task lives at `catalog/tasks.py` and is scheduled daily.
3. **Testing**
   - Backend: `docker compose exec backend python manage.py test`
   - Frontend: `cd web && npm test`
   - Mobile: `scripts/test_mobile.sh` (runs both iOS and Android test suites; see `scripts/test_mobile.sh --help` for options)
4. **Mobile config (.env)**
   - Mobile build/test scripts load `.env` via `scripts/load_env.sh`; set `BACKEND_URL` and `DISABLE_REGISTRATION` there to configure iOS + Android builds consistently.
5. **iOS workflow**
   - When editing iOS app code, run `scripts/build_and_run_ios.sh -p <project>` after each change to verify the update in the simulator.
4. **Environment switches**
   - `JUKE_RUNTIME_ENV` (development/staging/production) drives both Django settings (DEBUG, security toggles) and the web container entrypoint.
   - In Docker: `development` keeps the live Vite dev server, while `staging`/`production` invoke `npm run build:*`, copy the compressed assets, and hand them to NGINX (see `web/docker-entrypoint.sh`).
   - `SPOTIFY_USE_STUB_DATA=1` forces stubbed catalog data; defaults to `True` when running tests.

## Deployment Notes (Compose + Caddy)

- Production stack uses `docker-compose.prod.yml` with Caddy for TLS, Gunicorn for Django, and Nginx for the web app.
- Caddy terminates HTTPS and reverse-proxies to the `web` container; once DNS points at the VM, certs are auto-issued.
- `backend/run_prod.sh` runs migrations, `collectstatic`, then Gunicorn.
- Web build requires `BACKEND_URL` at build time; `docker-compose.prod.yml` passes it into the web image.
- Nginx inside the web container needs Docker DNS: `resolver 127.0.0.11` in `web/nginx.conf`.
- Proxy `/static/`, `/media/`, and `/admin/` in `web/nginx.conf` to the backend to avoid Django static assets returning HTML.
- Registration email flow can be disabled via `DISABLE_REGISTRATION=1` (blocks `/api/v1/auth/accounts/register/` with a 403 and replaces the register form with a warning banner).

## Data & Service Flow

1. Clients authenticate via OAuth (Spotify through `juke_auth`) or email-based flows (DRF + rest_registration).
2. Catalog endpoints (`catalog/views.py`) ingest/search artists, albums, and tracks, optionally calling the `recommender_engine` for embeddings.
3. Celery tasks populate embeddings (see `recommender/services`) and store them under `recommender_*` models.
4. Mobile/web clients call playlist/recommendation endpoints; Django forwards taste vectors to the FastAPI engine, then formats responses.

## Operational Notes

- Default Postgres hostnames (`db` inside Docker) and Redis (`redis://redis:$REDIS_PORT/0`) are set via env vars; override via `.env` for cloud deployments.
- Static media under `backend/static/media` stores cover art; in production serve via CDN and point `STATIC_URL` accordingly.
- GitHub Actions runs lint + tests on push to `main` (see `.github/workflows/ci.yml`).

Consult the per-subproject guides above for build and code-structure specifics.

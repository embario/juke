# Backend Agent Guide

## Scope
The Django backend lives at the repo root (files such as `manage.py`, `settings/`, `catalog/`, `juke_auth/`, `recommender/`, and `tests/`). This document tracks how the API, workers, and recommender integration fit together so you can reason about new behavior without walking the tree manually.

## Key Components

- **Settings**: `settings/base.py` defines env-aware config (see `JUKE_RUNTIME_ENV`, Celery knobs, CORS/CSRF, Spotify OAuth, custom `AUTH_USER_MODEL`). `settings/celery.py` exposes the Celery app used by workers/beat.
- **Apps**
  - `juke_auth`: custom user model (`JukeUser`), registration + OAuth pipeline, strategy overrides, email templates.
  - `catalog`: Spotify ingest, playback endpoints, serializers, Celery tasks (`catalog/tasks.py`) for syncing genres and catalog metadata.
  - `recommender`: Models referencing embeddings, API views that proxy/compose with the FastAPI service under `recommender_engine/`.
- **Services**: `catalog/services/`, `recommender/services/`, and `catalog/api_clients.py` wrap external APIs (Spotify) and the internal recommender engine.
- **Management commands**: `catalog/management/commands` for ingestion/sync jobs invoked via `python manage.py <command>`.
- **Tests**: Django/DRF tests under `tests/api/` and `tests/unit/` cover auth, catalog, playback, recommendations, and Spotify integrations.

## Environment & Secrets

- Copy `template.env` → `.env`. Core variables: `DJANGO_SECRET_KEY`, Postgres creds (`POSTGRES_*`), `SOCIAL_AUTH_SPOTIFY_*`, `EMAIL_HOST_*`, `RECOMMENDER_ENGINE_BASE_URL`, and `JUKE_RUNTIME_ENV`.
- `SPOTIFY_USE_STUB_DATA` defaults to `True` for `manage.py test`; flip via env when needing live Spotify calls.
- Allowed hosts and CORS/CSRF lists derive from `DJANGO_ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`. Defaults include localhost, Docker service names, and Android emulator loopback.
- `CELERY_VISIBILITY_TIMEOUT` (seconds) controls how long Redis keeps leased Celery tasks hidden before redelivery; keep this aligned with the Celery transport options set in `settings/base.py`.

## Running Locally

```bash
# API + workers + recommender + Postgres + Redis
cp template.env .env
docker compose up --build
```

- Django: `docker compose exec backend python manage.py migrate` & `python manage.py createsuperuser` when needed.
- Celery worker: part of compose (`worker` service). Manual run: `docker compose run --rm worker celery -A settings.celery worker -l info`.
- Celery beat: `docker compose up beat`.
- Recommender FastAPI container: `recommender-engine` service exposes `/embed` and `/recommend` (see `recommender_engine/app/main.py`).

## Troubleshooting Permissions (MANDATORY)

- When problems occur during testing or development, agents are authorized to inspect backend, web, and iOS/Android logs in their respective locations and Docker containers.
- No explicit virtualenv is required; agents must use Docker containers for troubleshooting and log inspection.

## Iterative Mobile Development Loop (MANDATORY)

- For each change, rebuild and rerun using the platform build script (`scripts/build_and_run_ios.sh -p <project>` or `scripts/build_and_run_android.sh -p <project>`).
- Capture the PIDs printed by the script (Android emulator PID + app PID; iOS app PID) and use them to scope log inspection.
- Review the per-run logs saved by the scripts before checking backend/web logs in Docker containers.

## HTTP Surfaces

- API URLs grouped under `settings/urls.py`:
  - `/api/v1/auth/...` (registration, login, Spotify OAuth redirect `SPOTIFY_REDIRECT_PATH`).
  - `/api/v1/catalog/...` (artists, albums, playback control using `catalog/services/playback.py`).
  - `/api/v1/recommendations/...` (calls `recommender/services/taste.py` then the FastAPI engine).
- Serializers live in each app’s `serializers.py`. Views generally subclass DRF `APIView`/`ViewSet`.

## Workers & Tasks

- `catalog.tasks.sync_spotify_genres` enqueued on `catalog` queue; scheduled daily via `CELERY_BEAT_SCHEDULE`.
- `CELERY_TASK_ALWAYS_EAGER` flips on when running tests (or when env var truthy) which keeps unit tests deterministic.
- Worker queue selection lives in `CELERY_TASK_ROUTES`; add new routes as needed.

## Data & Models

- `catalog/models.py`: Spotify entities (Artist, Album, Track, Genre, Playback state).
- `recommender/models.py`: Embedding tables storing vectors/metadata produced by ingestion tasks.
- `juke_auth/models.py`: `JukeUser` plus profile tables.
- Migrations reside under each app’s `migrations/` directory; use `python manage.py makemigrations <app>`.

## Testing & Tooling

 - Run backend tests either via Docker (`docker compose exec backend python manage.py test`). Tests can take longer than 10s; use a higher timeout when invoking from tooling.
- Linting: `ruff check .` (config in `backend/pyproject.toml`); legacy `flake8` uses `backend/setup.cfg` if needed.
- Coverage-critical suites under `tests/api/` assume stubbed Spotify responses; keep fixtures in `tests/fixtures/` in sync.
- Management command smoke tests live under `tests/unit/`.

## Extension Points

- Add new async jobs via `catalog/tasks.py` or `recommender/tasks.py`; remember to register queue routes.
- To call third-party APIs, add adapters in `catalog/api_clients.py` and keep pure-Python logic inside `catalog/services/*.py` for easier testing.
- Expose new endpoints by extending `settings/urls.py` and wiring DRF views/serializers within the relevant app.

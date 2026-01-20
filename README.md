# Juke Platform

Backend services for the Juke Music Service now live under `backend/`, the React-based analyst console sits in `web/`, and the platform-specific mobile clients live under `mobile/`.

## Repository layout

- `backend/`: Django API, Celery workers/beat, recommender engine, infrastructure Dockerfiles, and backend-specific configuration such as `setup.cfg` and `genres.txt`.
- `web/`: Vite + React frontend for analysts.
- `mobile/`: Native clients (`mobile/android/juke`, `mobile/ios/juke`).
- `template.env`, `.env`, and `test.env`: stay at the repository root so both Docker Compose files can source them regardless of where services run.
- `backend/static/` (cover art + other media) and `scripts/`: shared assets that remain addressable from the repository root.

## Running the stack

1. Duplicate `template.env` into `.env` (both stay in the repo root) and populate the secrets as needed, including `BACKEND_URL` (defaults to `http://127.0.0.1:8000` for the API) and `FRONTEND_URL` (`http://127.0.0.1:5173`).
2. Start the local services, including the asynchronous workers and web container:

	 ```bash
	 docker-compose up --build
	 ```

	 The Django API stays on `http://127.0.0.1:8000`, Celery workers connect to the bundled Redis broker, the recommender ML engine listens on `http://localhost:9000`, and the web console lives on `http://localhost:5173`.

### Background tasks

- Celery powers asynchronous workloads (Redis is provisioned automatically in `docker-compose.yml`).
- The default worker plus a beat scheduler are part of the compose stack; for ad-hoc runs use:

	```bash
	docker-compose run --rm worker celery -A settings.celery worker -l info
	```

- Tasks may be triggered via the API (see the genre sync endpoint) or scheduled via Celery Beat.
- The FastAPI-based `recommender-engine` container exposes `/embed` and `/recommend` for computing taste embeddings and likeness scores; Django calls it via the internal Docker network.

## Frontend development

- The React application resides in `web/` with Vite + TypeScript.
- To run the app outside of Docker:

	```bash
	cd web
	npm install
	npm run dev
	```

	You can override the backend target via `VITE_API_BASE_URL`.

- Asset builds honor `JUKE_RUNTIME_ENV` (`development`, `staging`, `production`). Use `npm run build:dev`, `npm run build:staging`, or `npm run build:prod` to emit the correct bundle; the default `npm run build` targets production and now outputs pre-compressed Brotli/Gzip assets ready for staging or production servers.
- The Dockerized frontend follows the same flag: `development` keeps the Vite dev server live (no bundling), while `staging`/`production` trigger the optimized build and serve the static assets through NGINX (including gzip precompression and `/api` + `/auth` proxying).

- Storybook documents the UI kit living under `web/src/uikit`. Launch it with:

	```bash
	cd web
	npm run storybook
	```

	The builder runs on `http://localhost:6006` by default.

## Mobile app

- Platform projects now live in `mobile/<platform>/<project>` to make room for future apps (for example, `mobile/android/juke` and `mobile/ios/juke`).
- Open the iOS app with Xcode via `xed mobile/ios/juke/juke-iOS.xcodeproj`.
- Use the existing `juke-iOS` scheme for running on simulators or devices; it continues to build against the same bundle identifiers.

## Tests

- Backend: `docker-compose exec backend python manage.py test` (run `cd backend` first if you prefer executing management commands on the host machine instead of Docker).
- Frontend: `cd web && npm test`

GitHub Actions (see `.github/workflows/ci.yml`) runs linting plus both suites on every push and pull request targeting `main`.

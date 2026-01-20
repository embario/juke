# Juke Platform

Backend services for the Juke Music Service now ship with a React-based analyst console located at `web/` and the SwiftUI mobile client now lives alongside it under `mobile/`.

## Running the stack

1. Duplicate `template.env` into `.env` and populate the secrets as needed, including `BACKEND_URL` (defaults to `http://127.0.0.1:8000` for the API) and `FRONTEND_URL` (`http://127.0.0.1:5173`).
2. Start the local services, including the asynchronous workers and frontend container:

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

- Storybook documents the UI kit living under `web/src/uikit`. Launch it with:

	```bash
	cd web
	npm run storybook
	```

	The builder runs on `http://localhost:6006` by default.

## Mobile app

- The native SwiftUI client from the former iOS repository has been moved into `mobile/`.
- Open the project with Xcode via `xed mobile/ios/juke-iOS.xcodeproj`.
- Use the existing `juke-iOS` scheme for running on simulators or devices; it continues to build against the same bundle identifiers.

## Tests

- Backend: `docker-compose exec web python manage.py test`
- Frontend: `cd web && npm test`

GitHub Actions (see `.github/workflows/ci.yml`) runs linting plus both suites on every push and pull request targeting `main`.

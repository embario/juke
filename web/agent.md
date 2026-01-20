# Web Agent Guide

## Stack Overview

- Framework: React 18 + React Router 6
- Build tool: Vite 7 + TypeScript 5
- Testing: Vitest (`web/src/setupTests.ts` + Testing Library) and Storybook 8 for UI kit documentation.
- Entry points: `src/main.tsx` bootstraps the app, `src/router.tsx` centralizes route definitions, and `src/App.tsx` composes top-level providers/layout.

## Directory Layout (`web/src`)

- `features/`: Page-level bundles (dashboards, catalog views, etc.).
- `shared/`: Cross-cutting utilities (hooks, constants, context providers).
- `uikit/`: Design system components mirrored in Storybook (`npm run storybook`).
- `types/`: Reusable TypeScript type definitions for DTOs and response models.
- `utils/`: Pure helpers (formatting, network glue).
- `index.css`: Tailwind/utility imports or base styles.

## Scripts & Environments

```bash
cd web
npm install                # once per environment
npm run dev                # Vite dev server @ http://127.0.0.1:5173
npm run build:dev          # development bundle (sets JUKE_RUNTIME_ENV=development)
npm run build:staging      # staging optimizations
npm run build:prod         # production bundle (default `npm run build`)
npm run preview            # serve a built bundle locally
npm test                   # Vitest suite
npm run storybook          # Storybook dev mode (port 6006)
npm run build-storybook    # Static Storybook export
```

- `VITE_API_BASE_URL` controls the API root; defaults to `http://127.0.0.1:8000` via `.env` or runtime injection from Docker.
- `JUKE_RUNTIME_ENV` aligns with backend settings and toggles analytics/logging gates.

## Networking & Data Flow

- REST calls should funnel through typed wrappers inside `shared` or `utils` (e.g., `shared/apiClient.ts`) so headers/auth tokens remain centralized.
- Authentication tokens originate from the Django backend (Session or DRF token). Mirror storage strategies with mobile clients for parity.
- Realtime/worker-driven updates (genre sync, playback state) poll backend endpoints; consider using React Query/SWR-style hooks inside `shared` if reliability becomes critical.

## Testing Guidance

- Component/unit tests: colocate `*.test.tsx` under the relevant folders; use Testing Library queries that reference semantic roles to stay resilient.
- E2E testing currently runs outside this repo (handled by QA). Keep contracts stable by exporting mock data from `tests/fixtures` when possible.
- Storybook stories live next to components (e.g., `Component.stories.tsx`) to ensure design parity across teams.

## Build & Delivery Notes

- Production builds generate Brotli + gzip assets (via `vite-plugin-compression`). Host them behind a CDN or the `web` service inside Docker.
- When running under Docker Compose, the container entrypoint (`web/docker-entrypoint.sh`) checks `JUKE_RUNTIME_ENV`:
	- `development` → skips bundling and launches `npm run dev` bound to `0.0.0.0:5173` so HMR works.
	- `staging`/`production` → runs the matching `npm run build:*`, copies `dist/` into `/usr/share/nginx/html`, and starts NGINX using `web/nginx.conf` (gz precompressed assets + `/api`/`/auth` proxy to the backend service).
- After changing frontend dependencies or environment wiring, restart with `docker compose restart web` (or rebuild with `docker compose build web`) to regenerate bundles.
- Keep dependency versions in `package.json` aligned with Node >=18 as enforced by the `engines` block.

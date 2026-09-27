# Music memories API

All endpoints require a Juke `Authorization: Bearer <token>` or `Token <token>`
header (authenticated web sessions also work with CSRF). Records and media are
private to the authenticated user's music profile.

- `GET /api/v1/vibe/memories/?limit=50&offset=0` returns
  `{memories: [...], count, nextOffset}` in descending memory date order.
- `POST /api/v1/vibe/memories/` creates a memory.
- `GET`, `PATCH`, `DELETE /api/v1/vibe/memories/<uuid>/` operate on one memory.
- `POST /api/v1/vibe/memories/classify/` previews Jev tags without persistence.
- `GET /api/v1/vibe/memory-tags/` returns `{tags: [string]}`, the user's reusable
  vocabulary. Explicitly submitted tags are retained for future memories.
- `GET /api/v1/vibe/memory-insights/` returns `{prompt, memoryCount, connections}`.
  Connections have `{kind, label, count, memoryIDs}` and are observations over
  submitted metadata, not inferred facial identities or image descriptions.
- `POST /api/v1/vibe/memory-media/` accepts a multipart `file` up to 50 MiB.
  Upload first, then submit returned IDs in the memory's `mediaIDs` array.
- `GET /api/v1/vibe/memory-media/<uuid>/content/` returns authenticated private
  bytes; `DELETE` removes an unattached upload. Deleting a memory removes all its
  attachments. Replacing a memory's attachment list deletes removed attachments.

A create request uses:

```json
{
  "title": "The ride home",
  "body": "Windows down after the show.",
  "occurredAt": "2026-09-15T21:00:00Z",
  "place": "Brooklyn",
  "people": ["Sam"],
  "songs": [{
    "id": "48c6d79e-f6ec-4f70-ae11-135ccfc66dc7",
    "provider": "spotify",
    "providerTrackID": "provider-id",
    "title": "A song",
    "artist": "An artist",
    "album": "An album",
    "artworkURL": "",
    "deepLink": "spotify:track:provider-id",
    "segmentStartSeconds": 12,
    "segmentEndSeconds": 30
  }],
  "mediaIDs": [],
  "tags": ["summer"],
  "excludedTags": []
}
```

Only `occurredAt` is required; at least one of body, songs, or attachments
must contain something. Apple Music uses provider `appleMusic`. Responses add
`id`, string `profileID`, `createdAt`, `updatedAt`, `generatedTags`, `classification`,
and `media` objects (`id`, `kind`, `filename`, `contentType`, `size`, relative `url`).
PATCH accepts any subset. A tag-only PATCH applies the supplied selection to the
previous classifier output and never reclassifies or restores removed tags.
An edited entry is reclassified before persistence, retaining explicit exclusions.

## Jev boundary

Set `JEV_CLASSIFICATION_URL`, optional `JEV_API_KEY`, and optionally
`JEV_TIMEOUT_SECONDS` (default 8). The endpoint receives
`{"memory": {title, body, place, people, songs}}` and must return
`{"tags": [string]}` (at most 50 tags, 60 characters each). HTTPS is recommended
for any endpoint outside the private deployment network. No model has been
configured by this implementation. Missing configuration, timeouts, service
errors, or malformed results return `classification: {status: "unavailable",
provider: "jev"}` and no generated tags. Successful validation returns status
`complete`. Never send chat history, attached media bytes, or account credentials.

The backend invokes classification before creating the profile/memory/tag records.
Clients can preview first to review suggestions. Creation classifies the final
submitted content again; use `excludedTags` to preserve rejected suggestions.

## Recommendation input

Each save atomically updates `MusicMemory.recommendation_signals` with a version,
source memory ID, profile ID, occurrence date, selected tags and provider song
identities. `vibe.memory_services.memory_recommendation_context(user)` supplies
the most recent 200 signals to discovery/ranking consumers. The authenticated
`GET /api/v1/vibe/memory-recommendation-context/` endpoint aggregates these into
`{version: 1, source: "musicMemories", memoryCount, songSeeds, tagSignals}`.
Song seeds include provider identity, weight (memory count), and source memory IDs;
tag signals include selected tag, weight, and source memory IDs. No personal prose,
people, place names, or media bytes are exposed to recommendation consumers. No new model
training or recommendation ranking is enabled here, and deletion removes signals.

## Verification

```sh
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations --check --dry-run vibe
docker compose exec backend python manage.py test tests.api.test_vibe_memories
```

Media currently uses private database byte storage for a self-contained first
slice. Large production libraries should move the same authenticated boundary to
private object storage; clients do not need to change URLs. Native clients should
download authenticated videos before handing a local file URL to the media player.

## Isolated Docker test setup (no workers or ingestion services)

The September 2026 verification used Python 3.14, PostgreSQL 18, and the project
requirements, replacing source-built `psycopg2` with `psycopg2-binary` only inside
the disposable test container. The running container names are
`juke-vibe-test-backend` and `juke-vibe-test-db`. This command reruns the checked
suites against that isolated stack:

```sh
docker exec \
  -e MLCORE_PG_HOT_TABLESPACE_HOST_PATH=/tmp/juke-vibe-hot \
  -e MLCORE_PG_COLD_TABLESPACE_HOST_PATH=/tmp/juke-vibe-cold \
  juke-vibe-test-backend python manage.py test \
  tests.api.test_vibe_memories tests.api.test_vibe_api --noinput
```

From a fresh Docker environment, run the following in the repository root. These
are disposable test credentials, and PostgreSQL is not exposed on a host port.
The tablespaces only satisfy existing schema migrations; this runs no ML jobs.

```sh
docker network create juke-vibe-test-net
docker run -d --name juke-vibe-test-db \
  --network juke-vibe-test-net --network-alias db \
  -e POSTGRES_DB=juke_vibe_test -e POSTGRES_USER=juke_vibe_test \
  -e POSTGRES_PASSWORD=vibe-isolated-test postgres:18-alpine
until docker exec juke-vibe-test-db pg_isready -U juke_vibe_test; do sleep 1; done
docker exec -u postgres juke-vibe-test-db mkdir -p \
  /var/lib/postgresql/tablespaces/juke_mlcore_hot \
  /var/lib/postgresql/tablespaces/juke_mlcore_cold
docker exec juke-vibe-test-db psql -U juke_vibe_test -d juke_vibe_test \
  -c "CREATE TABLESPACE juke_mlcore_hot LOCATION '/var/lib/postgresql/tablespaces/juke_mlcore_hot';"
docker exec juke-vibe-test-db psql -U juke_vibe_test -d juke_vibe_test \
  -c "CREATE TABLESPACE juke_mlcore_cold LOCATION '/var/lib/postgresql/tablespaces/juke_mlcore_cold';"
docker run -d --name juke-vibe-test-backend \
  --network juke-vibe-test-net -p 127.0.0.1:8765:8765 \
  -v "$PWD/backend:/app" -w /app \
  -e DJANGO_SECRET_KEY=disposable-vibe-test-only \
  -e BACKEND_URL=http://127.0.0.1:8765 -e FRONTEND_URL=http://127.0.0.1:5173 \
  -e EMAIL_PORT=587 -e POSTGRES_PORT=5432 -e POSTGRES_NAME=juke_vibe_test \
  -e POSTGRES_USER=juke_vibe_test -e POSTGRES_PASSWORD=vibe-isolated-test \
  -e CELERY_BROKER_URL=memory:// -e RECOMMENDER_ENGINE_BASE_URL=http://unused:8001 \
  -e BACKEND_ALLOWED_HOSTS=localhost,127.0.0.1,testserver \
  -e DISABLE_REGISTRATION=1 -e SPOTIFY_USE_STUB_DATA=1 \
  -e MLCORE_PG_HOT_TABLESPACE_HOST_PATH=/tmp/juke-vibe-hot \
  -e MLCORE_PG_COLD_TABLESPACE_HOST_PATH=/tmp/juke-vibe-cold \
  python:3.14-slim sleep infinity
docker exec juke-vibe-test-backend sh -c \
  "sed 's/^psycopg2$/psycopg2-binary/' requirements.txt > /tmp/test-requirements.txt && pip install -q -r /tmp/test-requirements.txt"
docker exec juke-vibe-test-backend python manage.py migrate --noinput
docker exec juke-vibe-test-backend python manage.py makemigrations --check --dry-run vibe
docker exec juke-vibe-test-backend python manage.py test \
  tests.api.test_vibe_memories tests.api.test_vibe_api --noinput
# Optional local HTTP endpoint for the native client integration suite:
docker exec -d juke-vibe-test-backend sh -c \
  'python manage.py runserver 0.0.0.0:8765 --noreload > /tmp/vibe-server.log 2>&1'
```

The first run encountered Docker daemon registry timeouts despite working host
HTTPS. Official ARM64 image manifests/layers were downloaded over host HTTPS and
loaded using `docker load`; the Python image was locally tagged
`juke-vibe-python:3.14-slim`. Container PyPI access worked normally. This is only
an environment workaround and does not change application dependencies or source.
Use the official image tags in the fresh setup above when registry pulls work.

After native integration checks finish, remove only these disposable containers:

```sh
docker rm -f -v juke-vibe-test-backend juke-vibe-test-db
docker network rm juke-vibe-test-net
```

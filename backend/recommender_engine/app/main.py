from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Sequence
from uuid import UUID

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

try:
    from app.scorers import extract_seed_feature_ids, score_cooccurrence, score_metadata
except ModuleNotFoundError:  # pragma: no cover - supports Django test imports
    from recommender_engine.app.scorers import extract_seed_feature_ids, score_cooccurrence, score_metadata

MODEL_VERSION = os.environ.get('RECOMMENDER_MODEL_VERSION', 'v1.0.0')
VECTOR_DIM = int(os.environ.get('RECOMMENDER_VECTOR_DIM', '32'))
DB_POOL_MIN = int(os.environ.get('RECOMMENDER_DB_POOL_MIN', '1'))
DB_POOL_MAX = int(os.environ.get('RECOMMENDER_DB_POOL_MAX', '10'))
DEFAULT_LIMIT = int(os.environ.get('JUKE_RECOMMENDER_DEFAULT_LIMIT', '10'))

logger = logging.getLogger(__name__)


def _database_conninfo() -> str:
    url = os.environ.get('DATABASE_URL')
    if url:
        return url
    name = os.environ.get('POSTGRES_NAME', 'postgres')
    user = os.environ.get('POSTGRES_USER', 'postgres')
    password = os.environ.get('POSTGRES_PASSWORD', 'postgres')
    host = os.environ.get('POSTGRES_HOST') or os.environ.get('POSTGRES_HOSTNAME') or 'db'
    port = os.environ.get('POSTGRES_PORT')
    if not port:
        raise ValueError("POSTGRES_PORT must be set")
    return f"dbname={name} user={user} password={password} host={host} port={port}"


DB_POOL = ConnectionPool(
    conninfo=_database_conninfo(),
    min_size=DB_POOL_MIN,
    max_size=DB_POOL_MAX,
    open=False,
)

app = FastAPI(title='Juke Recommender Engine')


class EmbedRequest(BaseModel):
    resource_type: str = Field(..., description='artist|album|track|text')
    attributes: Dict[str, List[str] | str]


class EmbedResponse(BaseModel):
    vector: List[float]
    model_version: str = MODEL_VERSION
    quality: float = 0.9
    metadata: Dict[str, str] = Field(default_factory=dict)


class RecommendationRequest(BaseModel):
    artists: List[str] = Field(default_factory=list)
    albums: List[str] = Field(default_factory=list)
    tracks: List[str] = Field(default_factory=list)
    genres: List[str] = Field(default_factory=list)
    limit: int = 10
    resource_types: List[str] = Field(default_factory=lambda: ['artists', 'albums', 'tracks'])


class RecommendationItem(BaseModel):
    name: str
    likeness: float
    extra: Dict[str, Any] = Field(default_factory=dict)


class RecommendationResponse(BaseModel):
    artists: List[RecommendationItem] = Field(default_factory=list)
    albums: List[RecommendationItem] = Field(default_factory=list)
    tracks: List[RecommendationItem] = Field(default_factory=list)
    model_version: str = MODEL_VERSION
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class ResolveRequestItem(BaseModel):
    source: str
    resource_type: str
    source_id: str


class ResolveRequest(BaseModel):
    items: List[ResolveRequestItem] = Field(..., min_length=1)


class ResolveResponseItem(BaseModel):
    source: str
    resource_type: str
    source_id: str
    canonical_item_id: UUID | None = None
    status: str
    canonical_key: str = ''
    item_type: str = ''


class ResolveResponse(BaseModel):
    items: List[ResolveResponseItem]
    model_version: str = MODEL_VERSION
    generated_at: datetime = Field(default_factory=datetime.utcnow)


_EMBEDDING_QUERIES = {
    'artists': """
        SELECT a.name, a.spotify_id, e.vector, e.model_version, e.quality_score, e.metadata
        FROM recommender_artistembedding e
        JOIN catalog_artist a ON a.id = e.artist_id
        WHERE e.vector IS NOT NULL
          AND jsonb_typeof(e.vector) = 'array'
          AND jsonb_array_length(e.vector) > 0
    """,
    'albums': """
        SELECT al.name, al.spotify_id, e.vector, e.model_version, e.quality_score, e.metadata
        FROM recommender_albumembedding e
        JOIN catalog_album al ON al.id = e.album_id
        WHERE e.vector IS NOT NULL
          AND jsonb_typeof(e.vector) = 'array'
          AND jsonb_array_length(e.vector) > 0
    """,
    'tracks': """
        SELECT t.name, t.spotify_id, e.vector, e.model_version, e.quality_score, e.metadata
        FROM recommender_trackembedding e
        JOIN catalog_track t ON t.id = e.track_id
        WHERE e.vector IS NOT NULL
          AND jsonb_typeof(e.vector) = 'array'
          AND jsonb_array_length(e.vector) > 0
    """,
}


def _ensure_pool_connection() -> ConnectionPool:
    try:
        if DB_POOL.closed:
            DB_POOL.open()
        return DB_POOL
    except Exception as exc:  # pragma: no cover - startup issues should bubble up
        logger.exception('Unable to open database pool')
        raise HTTPException(status_code=503, detail='Recommender data unavailable') from exc


def _run_query(sql: str, params: Sequence[Any] | None = None) -> List[Dict[str, Any]]:
    pool = _ensure_pool_connection()
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('Database query failed')
        raise HTTPException(status_code=503, detail='Recommender data unavailable') from exc


def _fetch_embeddings(resource_type: str) -> List[Dict[str, Any]]:
    sql = _EMBEDDING_QUERIES.get(resource_type)
    if not sql:
        raise HTTPException(status_code=400, detail=f'Unsupported resource type: {resource_type}')
    return _run_query(sql)


def _vector_from_tokens(tokens: Sequence[str]) -> np.ndarray:
    return _hash_tokens(list(tokens))


def _prepare_candidate_vector(raw_vector: Sequence[float] | None) -> np.ndarray:
    values = np.array(raw_vector or [], dtype=np.float32)
    if values.size < VECTOR_DIM:
        values = np.pad(values, (0, VECTOR_DIM - values.size))
    elif values.size > VECTOR_DIM:
        values = values[:VECTOR_DIM]
    return values


def _build_seed_set(payload: RecommendationRequest) -> set[str]:
    seeds: List[str] = []
    seeds.extend(payload.artists)
    seeds.extend(payload.albums)
    seeds.extend(payload.tracks)
    seeds.extend(payload.genres)
    return {seed.lower() for seed in seeds}


def _rank_candidates(
    user_vector: np.ndarray,
    candidates: List[Dict[str, Any]],
    *,
    limit: int,
    exclude: set[str],
) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    user = np.array(user_vector, dtype=np.float32)
    user_norm = np.linalg.norm(user)
    if not user_norm:
        return []

    ranked: List[Dict[str, Any]] = []
    for row in candidates:
        name = row.get('name')
        if not isinstance(name, str):
            continue
        if name.lower() in exclude:
            continue

        candidate_vector = _prepare_candidate_vector(row.get('vector'))
        cand_norm = np.linalg.norm(candidate_vector)
        if not cand_norm:
            continue
        score = float(np.dot(user, candidate_vector) / (user_norm * cand_norm))
        if np.isnan(score):
            continue
        score = max(0.0, min(score, 1.0))
        ranked.append({
            'name': name,
            'likeness': round(score, 2),
            'extra': _build_extra_payload(row),
        })

    ranked.sort(key=lambda item: item['likeness'], reverse=True)
    return ranked[:limit]


def _build_extra_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    extra: Dict[str, Any] = {
        'spotify_id': row.get('spotify_id'),
        'model_version': row.get('model_version') or MODEL_VERSION,
    }
    quality = row.get('quality_score')
    if quality is not None:
        extra['quality_score'] = quality
    metadata = row.get('metadata') or {}
    if metadata:
        extra['metadata'] = metadata
    return extra


def _hash_tokens(tokens: List[str]) -> np.ndarray:
    """
    Hash a list of tokens into a fixed-size vector.

    :param tokens: List of string tokens to hash
    :type tokens: List[str]
    :return: Normalized vector representation of the tokens
    :rtype: np.ndarray
    """
    if not tokens:
        tokens = ['unknown']
    vector = np.zeros(VECTOR_DIM)
    for token in tokens:
        digest = hashlib.sha1(token.encode('utf-8')).digest()
        sample = np.frombuffer(digest[:VECTOR_DIM], dtype=np.uint8)
        vector[: len(sample)] += sample
    norm = np.linalg.norm(vector)
    if norm:
        vector = vector / norm
    return vector


@app.post('/embed', response_model=EmbedResponse)
def embed(request: EmbedRequest):
    tokens: List[str]
    if isinstance(request.attributes, dict):
        tokens = []
        for value in request.attributes.values():
            if isinstance(value, list):
                tokens.extend(value)
            elif isinstance(value, str):
                tokens.append(value)
    else:
        tokens = [str(request.attributes)]
    vector = _hash_tokens(tokens).tolist()
    return EmbedResponse(vector=vector, metadata={'resource_type': request.resource_type})


@app.post('/recommend', response_model=RecommendationResponse)
def recommend(request: RecommendationRequest):
    resource_types = request.resource_types or ['artists', 'albums', 'tracks']
    seeds = request.artists + request.albums + request.tracks + request.genres
    if not seeds:
        raise HTTPException(status_code=400, detail='At least one seed is required.')

    user_vector = _vector_from_tokens(seeds)
    exclude = _build_seed_set(request)
    response = RecommendationResponse()

    for resource_type in resource_types:
        embeddings = _fetch_embeddings(resource_type)
        ranked = _rank_candidates(user_vector, embeddings, limit=request.limit, exclude=exclude)
        setattr(response, resource_type, ranked)

    response.generated_at = datetime.utcnow()
    return response


# ---------------------------------------------------------------------------
# ML Core Phase 1 — baseline rankers (arch §7.1, §7.2)
#
# These endpoints operate on canonical juke_id UUIDs (arch §5.1). They are
# independent of the legacy hash-token path above; legacy removal is Phase 4.
# ---------------------------------------------------------------------------

class BaselineRequest(BaseModel):
    seed_item_ids: List[UUID] = Field(..., min_length=1)
    exclude_ids: List[UUID] = Field(default_factory=list)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=100)


class BaselineItem(BaseModel):
    juke_id: UUID
    score: float
    components: Dict[str, float] = Field(default_factory=dict)


class BaselineResponse(BaseModel):
    items: List[BaselineItem]
    ranker: str
    seed_count: int
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# Resolve canonical item ids → local track metadata when a bridge exists.
# This keeps the serving item space aligned with MLCore canonical items while
# still allowing metadata ranking over the thin local catalog.
_SEED_FEATURES_SQL = """
    SELECT
        ci.id AS juke_id,
        t.album_id,
        aa.artist_id,
        ag.genre_id
    FROM mlcore_canonical_item ci
    JOIN catalog_track t ON t.juke_id = ci.track_id
    LEFT JOIN catalog_album_artists aa ON aa.album_id = t.album_id
    LEFT JOIN catalog_artist_genres ag ON ag.artist_id = aa.artist_id
    WHERE ci.id = ANY(%s)
"""

# Candidates that match ANY seed feature.
_METADATA_CANDIDATES_SQL = """
    SELECT DISTINCT
        ci.id AS juke_id,
        t.album_id,
        aa.artist_id,
        ag.genre_id
    FROM mlcore_canonical_item ci
    JOIN catalog_track t ON t.juke_id = ci.track_id
    LEFT JOIN catalog_album_artists aa ON aa.album_id = t.album_id
    LEFT JOIN catalog_artist_genres ag ON ag.artist_id = aa.artist_id
    WHERE t.album_id = ANY(%s)
       OR aa.artist_id = ANY(%s)
       OR ag.genre_id = ANY(%s)
"""

# Pairs are stored canonically (a < b); query both orientations.
_COOCCURRENCE_SQL = """
    SELECT item_b_juke_id AS neighbour, pmi_score, co_count
    FROM mlcore_item_cooccurrence
    WHERE item_a_juke_id = ANY(%s)
    UNION ALL
    SELECT item_a_juke_id AS neighbour, pmi_score, co_count
    FROM mlcore_item_cooccurrence
    WHERE item_b_juke_id = ANY(%s)
"""

_RESOLVE_ALIASES_SQL = """
    WITH requested(source, resource_type, source_id) AS (
        SELECT *
        FROM unnest(%s::text[], %s::text[], %s::text[])
    )
    SELECT
        alias.source,
        alias.resource_type,
        alias.source_id,
        alias.status,
        alias.canonical_item_id,
        canonical.canonical_key,
        canonical.item_type
    FROM mlcore_canonical_item_alias alias
    JOIN mlcore_canonical_item canonical ON canonical.id = alias.canonical_item_id
    JOIN requested
      ON requested.source = alias.source
     AND requested.resource_type = alias.resource_type
     AND requested.source_id = alias.source_id
"""


def _as_item(s) -> BaselineItem:
    return BaselineItem(juke_id=s.juke_id, score=s.score, components=s.components)


def _normalize_resolve_item(item: ResolveRequestItem) -> tuple[str, str, str] | None:
    source = str(item.source or '').strip().lower()
    resource_type = str(item.resource_type or '').strip().lower()
    source_id = str(item.source_id or '').strip()
    if not source or not resource_type or not source_id:
        return None
    return source, resource_type, source_id


def _resolve_status(row: Dict[str, Any] | None) -> str:
    if row is None:
        return 'unresolved'
    status = row.get('status')
    if status == 'active':
        return 'resolved'
    if status == 'conflict':
        return 'conflict'
    return 'unresolved'


@app.post('/resolve', response_model=ResolveResponse)
def resolve(request: ResolveRequest):
    normalized_items: list[tuple[int, tuple[str, str, str] | None]] = [
        (index, _normalize_resolve_item(item))
        for index, item in enumerate(request.items)
    ]
    valid_keys = sorted({key for _, key in normalized_items if key is not None})
    rows_by_key: dict[tuple[str, str, str], Dict[str, Any]] = {}

    if valid_keys:
        rows = _run_query(
            _RESOLVE_ALIASES_SQL,
            [
                [key[0] for key in valid_keys],
                [key[1] for key in valid_keys],
                [key[2] for key in valid_keys],
            ],
        )
        requested = set(valid_keys)
        for row in rows:
            key = (row['source'], row['resource_type'], row['source_id'])
            if key in requested:
                rows_by_key[key] = row

    response_items: list[ResolveResponseItem] = []
    for index, key in normalized_items:
        original = request.items[index]
        if key is None:
            response_items.append(
                ResolveResponseItem(
                    source=str(original.source or '').strip().lower(),
                    resource_type=str(original.resource_type or '').strip().lower(),
                    source_id=str(original.source_id or '').strip(),
                    status='invalid',
                )
            )
            continue

        row = rows_by_key.get(key)
        response_items.append(
            ResolveResponseItem(
                source=key[0],
                resource_type=key[1],
                source_id=key[2],
                canonical_item_id=row.get('canonical_item_id') if row else None,
                status=_resolve_status(row),
                canonical_key=row.get('canonical_key') if row else '',
                item_type=row.get('item_type') if row else '',
            )
        )

    return ResolveResponse(items=response_items, generated_at=datetime.utcnow())


@app.post('/engine/recommend/metadata', response_model=BaselineResponse)
def recommend_metadata(request: BaselineRequest):
    exclude = set(request.seed_item_ids) | set(request.exclude_ids)
    seed_rows = _run_query(_SEED_FEATURES_SQL, [list(request.seed_item_ids)])
    if not seed_rows:
        return BaselineResponse(items=[], ranker='metadata', seed_count=len(request.seed_item_ids))
    albums, artists, genres = extract_seed_feature_ids(seed_rows)
    cand_rows = _run_query(_METADATA_CANDIDATES_SQL, [albums, artists, genres])
    scored = score_metadata(seed_rows, cand_rows, exclude, request.limit)
    return BaselineResponse(
        items=[_as_item(s) for s in scored],
        ranker='metadata',
        seed_count=len(request.seed_item_ids),
    )


@app.post('/engine/recommend/cooccurrence', response_model=BaselineResponse)
def recommend_cooccurrence(request: BaselineRequest):
    exclude = set(request.seed_item_ids) | set(request.exclude_ids)
    seeds = list(request.seed_item_ids)
    rows = _run_query(_COOCCURRENCE_SQL, [seeds, seeds])
    scored = score_cooccurrence(rows, exclude, request.limit)
    return BaselineResponse(
        items=[_as_item(s) for s in scored],
        ranker='cooccurrence',
        seed_count=len(request.seed_item_ids),
    )

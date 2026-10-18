"""MusicBrainz Spotify track URLs -> canonical Spotify aliases (identity graph saturation, task B5).

Everything here is set-based. The database pool does about 65 random index lookups per second, so
no step probes an index row by row: the URL evidence is normalised once into a TEMP staging table,
and each large table (canonical items, redirects, aliases, hydration queue) is joined to it in a
single hash-join pass with nested loops and index scans switched off for that statement. The writes
are then applied in bounded batches (10k-100k rows per transaction) from the staged result, so they
are idempotent (``ON CONFLICT DO NOTHING``) and resumable by cursor.

Staging lives in TEMP tables (no schema change), so a resumed run rebuilds the workspace
deterministically and continues from the checkpointed cursors.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from django.db import connection, transaction

from mlcore.models import MusicBrainzRecordingURL, SourceIngestionRun
from mlcore.services.musicbrainz_bridge import BRIDGE_SOURCE_ID
from mlcore.services.spotify_ids import normalize_spotify_track_id
from mlcore.services.identity_safety import stage_holds, assert_hold_snapshot

ALGORITHM_VERSION = 'musicbrainz-url-alias-v2'
MATCH_SOURCE = 'musicbrainz_url'
MAX_REDIRECT_DEPTH = 8
STAGE_CHUNK_SIZE = 50_000

# Statuses assigned to every staged recording. Only ``new`` produces an alias.
STATUS_NEW = 'new'
STATUS_EXISTING_SAME = 'existing_same'
STATUS_CONFLICT_ALIAS = 'conflict_alias'
STATUS_API_DISAGREES = 'api_disagrees'
STATUS_SHARED_ID = 'shared_id'
STATUS_MULTIPLE_IDS = 'multiple_ids'
STATUS_UNRESOLVED = 'unresolved'
STATUS_REDIRECT_DEPTH = 'redirect_depth'

# Planner switches that force hash joins over sequential scans for one statement.
BULK_JOIN_SETTINGS = (
    'enable_nestloop',
    'enable_mergejoin',
    'enable_indexscan',
    'enable_indexonlyscan',
    'enable_bitmapscan',
)

TEMP_TABLES_SQL = (
    'DROP TABLE IF EXISTS tmp_mbu_stage, tmp_mbu_recording, tmp_mbu_alias, tmp_mbu_items, tmp_mbu_api, '
    'tmp_mbu_candidate, tmp_mbu_api_hold, tmp_mbu_hydra_items, tmp_mbu_phi, tmp_mbu_isrc',
    'CREATE TEMP TABLE tmp_mbu_stage (recording_mbid uuid NOT NULL, spotify_id text NOT NULL)',
    '''CREATE TEMP TABLE tmp_mbu_recording (
        recording_mbid uuid PRIMARY KEY, id_count integer NOT NULL, spotify_id text NOT NULL, item_id uuid)''',
    '''CREATE TEMP TABLE tmp_mbu_alias (
        source_id text PRIMARY KEY, owner_id uuid NOT NULL, status text NOT NULL, match_source text NOT NULL, held boolean NOT NULL)''',
    '''CREATE TEMP TABLE tmp_mbu_items (
        item_id uuid PRIMARY KEY, final_id uuid NOT NULL, depth integer NOT NULL DEFAULT 0)''',
    'CREATE TEMP TABLE tmp_mbu_api (final_id uuid NOT NULL, spotify_id text NOT NULL)',
    'CREATE TEMP TABLE tmp_mbu_api_hold (final_id uuid NOT NULL, spotify_id text NOT NULL)',
    '''CREATE TEMP TABLE tmp_mbu_candidate (
        recording_mbid uuid PRIMARY KEY, spotify_id text NOT NULL, final_id uuid, status text NOT NULL)''',
)

# Recording MBID -> canonical item: one hash join, build side is the (small) staged recording table.
RESOLVE_ITEMS_SQL = '''
    UPDATE tmp_mbu_recording r
    SET item_id = item.id
    FROM mlcore_canonical_item item
    WHERE item.canonical_key = 'recording_mbid:' || r.recording_mbid::text
'''

LOAD_SPOTIFY_ALIASES_SQL = '''
    INSERT INTO tmp_mbu_alias (source_id, owner_id, status, match_source, held)
    SELECT alias.source_id, alias.canonical_item_id, alias.status, COALESCE(alias.metadata->>'match_source', ''),
           EXISTS (SELECT 1 FROM tmp_identity_hold h WHERE h.scheme = 'spotify_track' AND h.value = alias.source_id)
           OR EXISTS (SELECT 1 FROM tmp_identity_hold h WHERE h.scheme = 'isrc'
                      AND h.value = alias.metadata->>'match_isrc')
    FROM mlcore_canonical_item_alias alias
    WHERE alias.source = 'spotify' AND alias.resource_type = 'track'
    ON CONFLICT (source_id) DO NOTHING
'''

# One redirect hop for every staged item; repeat until nothing moves (bounded by MAX_REDIRECT_DEPTH).
REDIRECT_HOP_SQL = '''
    UPDATE tmp_mbu_items t
    SET final_id = redirect.to_canonical_item_id, depth = t.depth + 1
    FROM mlcore_canonical_item_redirect redirect
    WHERE redirect.from_canonical_item_id = t.final_id
      AND redirect.status = 'active'
      AND t.depth < %s
'''

CLASSIFY_SQL = '''
    INSERT INTO tmp_mbu_candidate (recording_mbid, spotify_id, final_id, status)
    SELECT
        r.recording_mbid,
        r.spotify_id,
        it.final_id,
        CASE
            WHEN a.held THEN 'quarantined_reference'
            WHEN r.id_count > 1 THEN 'multiple_ids'
            WHEN r.item_id IS NULL THEN 'unresolved'
            WHEN it.depth >= %s THEN 'redirect_depth'
            WHEN a.source_id IS NOT NULL AND ao.final_id = it.final_id THEN 'existing_same'
            WHEN a.source_id IS NOT NULL THEN 'conflict_alias'
            WHEN EXISTS (SELECT 1 FROM tmp_mbu_api api
                         WHERE api.final_id = it.final_id AND api.spotify_id <> r.spotify_id) THEN 'api_disagrees'
            ELSE 'new'
        END
    FROM tmp_mbu_recording r
    LEFT JOIN tmp_mbu_items it ON it.item_id = r.item_id
    LEFT JOIN tmp_mbu_alias a ON a.source_id = r.spotify_id
    LEFT JOIN tmp_mbu_items ao ON ao.item_id = a.owner_id
'''

SHARED_ID_SQL = '''
    UPDATE tmp_mbu_candidate c
    SET status = 'shared_id'
    WHERE c.status = 'new'
      AND c.spotify_id IN (
          SELECT spotify_id FROM tmp_mbu_candidate
          WHERE status = 'new'
          GROUP BY spotify_id
          HAVING COUNT(DISTINCT final_id) > 1
      )
'''

ALIAS_BATCH_SELECT_SQL = '''
    SELECT recording_mbid, spotify_id, final_id
    FROM tmp_mbu_candidate
    WHERE status = 'new'
      AND (%s::uuid IS NULL OR recording_mbid > %s::uuid)
    ORDER BY recording_mbid
    LIMIT %s
'''

ALIAS_BATCH_INSERT_SQL = '''
    WITH batch AS MATERIALIZED (''' + ALIAS_BATCH_SELECT_SQL + '''),
    inserted AS (
        INSERT INTO mlcore_canonical_item_alias (
            id, canonical_item_id, source, resource_type, source_id, confidence, source_version,
            status, metadata, created_at, updated_at
        )
        SELECT DISTINCT ON (b.spotify_id)
            md5('spotify:track:' || b.spotify_id)::uuid,
            b.final_id,
            'spotify',
            'track',
            b.spotify_id,
            0.9,
            %s,
            'active',
            jsonb_build_object(
                'match_source', 'musicbrainz_url',
                'musicbrainz_source_version', %s,
                'recording_mbid', b.recording_mbid::text
            ),
            NOW(),
            NOW()
        FROM batch b
        ORDER BY b.spotify_id, b.recording_mbid
        ON CONFLICT (source, resource_type, source_id) DO NOTHING
        RETURNING 1
    )
    SELECT
        (SELECT COUNT(*) FROM batch),
        (SELECT recording_mbid::text FROM batch ORDER BY recording_mbid DESC LIMIT 1),
        (SELECT COUNT(*) FROM inserted)
'''

ALIAS_BATCH_DRY_RUN_SQL = '''
    WITH batch AS MATERIALIZED (''' + ALIAS_BATCH_SELECT_SQL + ''')
    SELECT
        COUNT(*),
        (SELECT recording_mbid::text FROM batch ORDER BY recording_mbid DESC LIMIT 1),
        COUNT(DISTINCT spotify_id)
    FROM batch
'''

# Hydration items to mark matched: items on the recording's own item, its final target, and items
# that redirect to the target in one hop. One hash-join scan of the queue, restricted to open work.
HYDRA_ITEMS_SQL = '''
    INSERT INTO tmp_mbu_hydra_items (item_id, spotify_id)
    SELECT DISTINCT ON (item_id) item_id, spotify_id FROM (
        SELECT it.item_id AS item_id, c.spotify_id, c.recording_mbid
        FROM tmp_mbu_candidate c
        JOIN tmp_mbu_recording r ON r.recording_mbid = c.recording_mbid
        JOIN tmp_mbu_items it ON it.item_id = r.item_id
        WHERE c.status IN ('new', 'existing_same')
        UNION ALL
        SELECT c.final_id, c.spotify_id, c.recording_mbid
        FROM tmp_mbu_candidate c
        WHERE c.status IN ('new', 'existing_same') AND c.final_id IS NOT NULL
        UNION ALL
        SELECT redirect.from_canonical_item_id, c.spotify_id, c.recording_mbid
        FROM mlcore_canonical_item_redirect redirect
        JOIN tmp_mbu_candidate c ON c.final_id = redirect.to_canonical_item_id
        WHERE c.status IN ('new', 'existing_same') AND redirect.status = 'active'
    ) pairs
    ORDER BY item_id, recording_mbid
'''

HYDRA_COLLECT_SQL = '''
    INSERT INTO tmp_mbu_phi (id, spotify_id)
    SELECT phi.id, h.spotify_id
    FROM mlcore_provider_hydration_item phi
    JOIN tmp_mbu_hydra_items h ON h.item_id = phi.canonical_item_id
    WHERE phi.provider = 'spotify'
      AND phi.status IN ('pending', 'retry')
'''

HYDRA_BATCH_SELECT_SQL = '''
    SELECT id, spotify_id FROM tmp_mbu_phi
    WHERE id > %s
    ORDER BY id
    LIMIT %s
'''

# FOR UPDATE SKIP LOCKED: never wait on, or fight, a row the hydration worker currently holds.
# Leased rows are skipped (not matched) so a live worker's lease is never overwritten.
HYDRA_BATCH_UPDATE_SQL = '''
    WITH batch AS MATERIALIZED (''' + HYDRA_BATCH_SELECT_SQL + '''),
    locked AS (
        SELECT phi.id, b.spotify_id
        FROM mlcore_provider_hydration_item phi
        JOIN batch b ON b.id = phi.id
        WHERE phi.status IN ('pending', 'retry')
          AND phi.leased_by = ''
          AND (phi.lease_expires_at IS NULL OR phi.lease_expires_at < NOW())
        FOR UPDATE OF phi SKIP LOCKED
    ), updated AS (
        UPDATE mlcore_provider_hydration_item phi
        SET status = 'matched',
            evidence = phi.evidence || jsonb_build_object(
                'matched_by', 'musicbrainz_url',
                'spotify_track_id', locked.spotify_id,
                'musicbrainz_source_version', %s
            ),
            next_attempt_at = NULL,
            updated_at = NOW()
        FROM locked
        WHERE phi.id = locked.id
        RETURNING 1
    )
    SELECT (SELECT COUNT(*) FROM batch), (SELECT id FROM batch ORDER BY id DESC LIMIT 1), (SELECT COUNT(*) FROM updated)
'''

HYDRA_BATCH_DRY_RUN_SQL = '''
    WITH batch AS MATERIALIZED (''' + HYDRA_BATCH_SELECT_SQL + ''')
    SELECT
        (SELECT COUNT(*) FROM batch),
        (SELECT id FROM batch ORDER BY id DESC LIMIT 1),
        (SELECT COUNT(*) FROM mlcore_provider_hydration_item phi JOIN batch b ON b.id = phi.id
         WHERE phi.status IN ('pending', 'retry') AND phi.leased_by = ''
           AND (phi.lease_expires_at IS NULL OR phi.lease_expires_at < NOW()))
'''

# Precision check: Spotify candidates that the ISRC search itself returned for the same item.
ISRC_CANDIDATES_SQL = '''
    INSERT INTO tmp_mbu_isrc (item_id, track_id)
    SELECT DISTINCT phi.canonical_item_id, candidate->>'track_id'
    FROM mlcore_provider_hydration_item phi
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(phi.evidence->'candidates') = 'array'
             THEN phi.evidence->'candidates' ELSE '[]'::jsonb END
    ) AS candidate
    WHERE phi.provider = 'spotify'
      AND phi.status IN ('matched', 'ambiguous')
      AND NOT (phi.evidence ? 'identity_reference_quarantine')
      AND NOT (phi.evidence ? 'validation_hold')
      AND NOT EXISTS (SELECT 1 FROM tmp_identity_hold h WHERE h.scheme = 'spotify_track'
                      AND h.value = candidate->>'track_id')
      AND NOT EXISTS (SELECT 1 FROM tmp_identity_hold h WHERE h.scheme = 'isrc' AND h.value = phi.identifier)
'''

PRECISION_SQL = '''
    SELECT
        CASE
            WHEN EXISTS (SELECT 1 FROM tmp_mbu_api api
                         WHERE api.final_id = c.final_id AND api.spotify_id = c.spotify_id) THEN 'same'
            WHEN EXISTS (SELECT 1 FROM tmp_mbu_isrc i
                         WHERE i.item_id IN (c.final_id, r.item_id) AND i.track_id = c.spotify_id)
                THEN 'different_same_isrc'
            ELSE 'different'
        END AS outcome,
        COUNT(*)
    FROM tmp_mbu_candidate c
    JOIN tmp_mbu_recording r ON r.recording_mbid = c.recording_mbid
    WHERE c.status IN ('new', 'existing_same', 'conflict_alias', 'api_disagrees', 'shared_id')
      AND EXISTS (SELECT 1 FROM tmp_mbu_api api WHERE api.final_id = c.final_id)
    GROUP BY 1
'''

PRECISION_EXAMPLES_SQL = '''
    SELECT c.recording_mbid::text, c.spotify_id, c.final_id::text,
           (SELECT MIN(api.spotify_id) FROM tmp_mbu_api api WHERE api.final_id = c.final_id)
    FROM tmp_mbu_candidate c
    WHERE c.status IN ('new', 'existing_same', 'conflict_alias', 'api_disagrees', 'shared_id')
      AND EXISTS (SELECT 1 FROM tmp_mbu_api api WHERE api.final_id = c.final_id)
      AND NOT EXISTS (SELECT 1 FROM tmp_mbu_api api WHERE api.final_id = c.final_id AND api.spotify_id = c.spotify_id)
    ORDER BY c.recording_mbid
    LIMIT %s
'''


@dataclass
class WorkspaceStats:
    source_version: str
    url_rows: int = 0
    invalid_urls: int = 0
    staged_pairs: int = 0
    recordings: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    explains: dict[str, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            'source_version': self.source_version,
            'url_rows': self.url_rows,
            'invalid_urls': self.invalid_urls,
            'staged_pairs': self.staged_pairs,
            'recordings': self.recordings,
            'status_counts': dict(self.status_counts),
        }


def latest_musicbrainz_url_source_version() -> str:
    source_version = (
        SourceIngestionRun.objects.filter(source=BRIDGE_SOURCE_ID, status='succeeded')
        .order_by('-completed_at', '-started_at')
        .values_list('source_version', flat=True)
        .first()
    )
    if not source_version:
        raise ValueError('No successful MusicBrainz identity bridge run is available.')
    if not MusicBrainzRecordingURL.objects.filter(source_version=source_version, provider='spotify').exists():
        raise ValueError(f'No Spotify recording URLs staged for MusicBrainz source version {source_version}.')
    return str(source_version)


def _bulk_join_mode(cursor) -> None:
    """Call inside a transaction: SET LOCAL ends with it, so other statements keep normal plans."""
    for setting in BULK_JOIN_SETTINGS:
        cursor.execute(f'SET LOCAL {setting} = off')


def _run_bulk(sql: str, params: Iterable[Any] | None = None) -> int:
    with transaction.atomic(), connection.cursor() as cursor:
        _bulk_join_mode(cursor)
        cursor.execute(sql, list(params or []))
        return max(cursor.rowcount, 0)


def _explain(sql: str, params: Iterable[Any] | None = None, *, bulk: bool = True) -> list[str]:
    with transaction.atomic(), connection.cursor() as cursor:
        if bulk:
            _bulk_join_mode(cursor)
        cursor.execute('EXPLAIN ' + sql, list(params or []))
        return [row[0] for row in cursor.fetchall()]


def build_workspace(
    source_version: str,
    *,
    mbid_prefix: str = '',
    explain: bool = False,
    progress: Callable[[str], None] | None = None,
) -> WorkspaceStats:
    """Stage and classify every Spotify track URL of ``source_version`` into TEMP tables.

    ``mbid_prefix`` restricts the run to recordings whose MBID starts with the given hex prefix (for
    example ``0a`` is roughly 1/256 of the data) so the plans and timings can be checked on a slice.
    """
    report = progress or (lambda _message: None)
    prefix = mbid_prefix.strip().lower().replace('-', '')
    stats = WorkspaceStats(source_version=source_version)
    started = time.monotonic()
    stage_holds()

    with connection.cursor() as cursor:
        for statement in TEMP_TABLES_SQL:
            cursor.execute(statement)

    queryset = MusicBrainzRecordingURL.objects.filter(source_version=source_version, provider='spotify')
    pending: set[tuple[str, str]] = set()
    for recording_mbid, url in queryset.values_list('recording_mbid', 'url').iterator(chunk_size=STAGE_CHUNK_SIZE):
        stats.url_rows += 1
        mbid_text = str(recording_mbid)
        if prefix and not mbid_text.replace('-', '').startswith(prefix):
            continue
        spotify_id = normalize_spotify_track_id(url)
        if not spotify_id:
            stats.invalid_urls += 1
            continue
        pending.add((mbid_text, spotify_id))
        if len(pending) >= STAGE_CHUNK_SIZE:
            stats.staged_pairs += _flush_stage(pending)
    stats.staged_pairs += _flush_stage(pending)
    report(f'stage urls={stats.url_rows} invalid={stats.invalid_urls} pairs={stats.staged_pairs} '
           f'elapsed={time.monotonic() - started:.0f}s')

    with connection.cursor() as cursor:
        cursor.execute('''
            INSERT INTO tmp_mbu_recording (recording_mbid, id_count, spotify_id)
            SELECT recording_mbid, COUNT(DISTINCT spotify_id), MIN(spotify_id)
            FROM tmp_mbu_stage GROUP BY recording_mbid
        ''')
        stats.recordings = cursor.rowcount
        cursor.execute('ANALYZE tmp_mbu_recording')
    if explain:
        stats.explains['resolve_items'] = _explain(RESOLVE_ITEMS_SQL)
    _run_bulk(RESOLVE_ITEMS_SQL)
    report(f'resolved items recordings={stats.recordings} elapsed={time.monotonic() - started:.0f}s')

    if explain:
        stats.explains['load_spotify_aliases'] = _explain(LOAD_SPOTIFY_ALIASES_SQL, bulk=False)
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(LOAD_SPOTIFY_ALIASES_SQL)
        cursor.execute('''
            INSERT INTO tmp_mbu_items (item_id, final_id)
            SELECT item_id, item_id FROM (
                SELECT item_id FROM tmp_mbu_recording WHERE item_id IS NOT NULL
                UNION
                SELECT owner_id FROM tmp_mbu_alias
            ) ids
        ''')
        cursor.execute('ANALYZE tmp_mbu_items')
        cursor.execute('ANALYZE tmp_mbu_alias')

    if explain:
        stats.explains['redirect_hop'] = _explain(REDIRECT_HOP_SQL, [MAX_REDIRECT_DEPTH])
    for hop in range(MAX_REDIRECT_DEPTH):
        moved = _run_bulk(REDIRECT_HOP_SQL, [MAX_REDIRECT_DEPTH])
        report(f'redirect hop={hop + 1} moved={moved} elapsed={time.monotonic() - started:.0f}s')
        if moved == 0:
            break

    with connection.cursor() as cursor:
        cursor.execute('''
            INSERT INTO tmp_mbu_api (final_id, spotify_id)
            SELECT it.final_id, a.source_id
            FROM tmp_mbu_alias a JOIN tmp_mbu_items it ON it.item_id = a.owner_id
            WHERE a.status = 'active' AND NOT a.held AND a.match_source = 'isrc'
        ''')
        cursor.execute('''INSERT INTO tmp_mbu_api_hold (final_id, spotify_id)
            SELECT it.final_id, a.source_id FROM tmp_mbu_alias a
            JOIN tmp_mbu_items it ON it.item_id = a.owner_id WHERE a.held AND a.match_source = 'isrc' ''')
        cursor.execute('ANALYZE tmp_mbu_api')
        cursor.execute(CLASSIFY_SQL, [MAX_REDIRECT_DEPTH])
        cursor.execute(SHARED_ID_SQL)
        cursor.execute('ANALYZE tmp_mbu_candidate')
        cursor.execute('SELECT status, COUNT(*) FROM tmp_mbu_candidate GROUP BY status')
        stats.status_counts = {status: int(count) for status, count in cursor.fetchall()}
    report(f'classified {stats.status_counts} elapsed={time.monotonic() - started:.0f}s')
    return stats


def _flush_stage(pending: set[tuple[str, str]]) -> int:
    if not pending:
        return 0
    mbids = [pair[0] for pair in pending]
    spotify_ids = [pair[1] for pair in pending]
    count = len(pending)
    pending.clear()
    with connection.cursor() as cursor:
        cursor.execute(
            'INSERT INTO tmp_mbu_stage (recording_mbid, spotify_id) '
            'SELECT * FROM unnest(%s::uuid[], %s::text[])',
            [mbids, spotify_ids],
        )
    return count


@dataclass(frozen=True)
class BatchResult:
    processed: int
    cursor_value: str | None
    changed: int


def apply_alias_batch(
    *,
    source_version: str,
    last_mbid: str | None,
    batch_size: int,
    write: bool,
) -> BatchResult:
    if batch_size < 1:
        raise ValueError('batch_size must be greater than zero')
    with transaction.atomic(), connection.cursor() as cursor:
        if write:
            assert_hold_snapshot()
            if connection.vendor == 'postgresql':
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext('mlcore-canonical-alias-materialization'))")
            cursor.execute(
                ALIAS_BATCH_INSERT_SQL,
                [last_mbid, last_mbid, batch_size, f'musicbrainz-url:{source_version}', source_version],
            )
        else:
            cursor.execute(ALIAS_BATCH_DRY_RUN_SQL, [last_mbid, last_mbid, batch_size])
        processed, cursor_value, changed = cursor.fetchone()
    return BatchResult(int(processed or 0), cursor_value, int(changed or 0))


def collect_hydration_targets(*, explain: bool = False) -> tuple[int, list[str]]:
    """Stage open Spotify hydration items that the candidate aliases resolve. Returns (count, plan)."""
    with connection.cursor() as cursor:
        cursor.execute('DROP TABLE IF EXISTS tmp_mbu_hydra_items, tmp_mbu_phi')
        cursor.execute('CREATE TEMP TABLE tmp_mbu_hydra_items (item_id uuid PRIMARY KEY, spotify_id text NOT NULL)')
        cursor.execute('CREATE TEMP TABLE tmp_mbu_phi (id bigint PRIMARY KEY, spotify_id text NOT NULL)')
    plan: list[str] = []
    if explain:
        plan = _explain(HYDRA_ITEMS_SQL) + [''] + _explain(HYDRA_COLLECT_SQL)
    _run_bulk(HYDRA_ITEMS_SQL)
    with connection.cursor() as cursor:
        cursor.execute('ANALYZE tmp_mbu_hydra_items')
    count = _run_bulk(HYDRA_COLLECT_SQL)
    with connection.cursor() as cursor:
        cursor.execute('ANALYZE tmp_mbu_phi')
    return count, plan


def apply_hydration_batch(
    *,
    source_version: str,
    last_id: int,
    batch_size: int,
    write: bool,
) -> BatchResult:
    if batch_size < 1:
        raise ValueError('batch_size must be greater than zero')
    with transaction.atomic(), connection.cursor() as cursor:
        if write:
            assert_hold_snapshot()
            cursor.execute(HYDRA_BATCH_UPDATE_SQL, [last_id, batch_size, source_version])
        else:
            cursor.execute(HYDRA_BATCH_DRY_RUN_SQL, [last_id, batch_size])
        processed, max_id, changed = cursor.fetchone()
    return BatchResult(int(processed or 0), None if max_id is None else str(max_id), int(changed or 0))


def precision_report(*, explain: bool = False, example_limit: int = 0) -> dict[str, Any]:
    """Compare MusicBrainz link IDs with API-hydrated aliases of the same final target (read-only)."""
    with connection.cursor() as cursor:
        cursor.execute('DROP TABLE IF EXISTS tmp_mbu_isrc')
        cursor.execute('CREATE TEMP TABLE tmp_mbu_isrc (item_id uuid NOT NULL, track_id text NOT NULL)')
    plan: dict[str, list[str]] = {}
    if explain:
        plan['isrc_candidates'] = _explain(ISRC_CANDIDATES_SQL)
    _run_bulk(ISRC_CANDIDATES_SQL)
    with connection.cursor() as cursor:
        cursor.execute('ANALYZE tmp_mbu_isrc')
    if explain:
        plan['precision'] = _explain(PRECISION_SQL)
    with transaction.atomic(), connection.cursor() as cursor:
        _bulk_join_mode(cursor)
        cursor.execute(PRECISION_SQL)
        counts = {outcome: int(count) for outcome, count in cursor.fetchall()}
        examples: list[dict[str, str]] = []
        if example_limit > 0:
            cursor.execute(PRECISION_EXAMPLES_SQL, [example_limit])
            examples = [
                {'recording_mbid': row[0], 'musicbrainz_spotify_id': row[1], 'canonical_item_id': row[2],
                 'api_spotify_id': row[3]}
                for row in cursor.fetchall()
            ]
    same = counts.get('same', 0)
    same_isrc = counts.get('different_same_isrc', 0)
    different = counts.get('different', 0)
    compared = same + same_isrc + different
    held = _held_reference_count()
    return {
        'compared': compared,
        'metric_kind': 'reference_agreement_not_independent_precision',
        'held_comparisons': held,
        'population': compared + held,
        'eligible_reference_agreement': ((same + same_isrc) / compared) if compared else None,
        'same': same,
        'different_same_isrc': same_isrc,
        'different': different,
        'strict_precision': (same / (compared + held)) if compared + held else None,
        'precision': ((same + same_isrc) / (compared + held)) if compared + held else None,
        'examples': examples,
        'explains': plan,
    }


def _held_reference_count():
    with connection.cursor() as c:
        c.execute("""SELECT COUNT(*) FROM tmp_mbu_candidate c WHERE
            ((c.status = 'quarantined_reference' AND (
                EXISTS (SELECT 1 FROM tmp_mbu_api_hold h WHERE h.final_id = c.final_id)
                OR EXISTS (SELECT 1 FROM tmp_mbu_api a WHERE a.final_id = c.final_id)))
             OR (EXISTS (SELECT 1 FROM tmp_mbu_api_hold h WHERE h.final_id = c.final_id)
                 AND NOT EXISTS (SELECT 1 FROM tmp_mbu_api a WHERE a.final_id = c.final_id)))
            AND c.status IN ('new','existing_same','conflict_alias','api_disagrees','shared_id','quarantined_reference')""")
        return c.fetchone()[0]

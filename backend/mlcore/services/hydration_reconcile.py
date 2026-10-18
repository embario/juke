"""Mark queued Spotify hydration items ``matched`` when their final (post-redirect) item already has a Spotify ID.

Identity-graph saturation moves Spotify IDs onto canonical items through aliases and redirects, so
many queued ISRCs now have an offline answer. This pass resolves those without an API call.

Set-based, per the pool's ~65 random lookups/s: the pending queue is staged once into a TEMP table,
resolved to final redirect targets by :func:`mlcore.services.redirect_writes.follow_redirects` (one
hash-join pass over the redirect table per hop), joined in memory to the staged active Spotify
aliases, and written back in ``item_id`` slices through the queue's primary key.

Idempotent and resumable: a matched row is no longer pending, so a rerun only sees what is left;
``after_id`` restarts the scan mid-queue. Rows that are running, leased, locked by a worker (SKIP
LOCKED) or terminal are never touched.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable

from django.db import connection, transaction

from mlcore.models import ProviderHydrationItem
from mlcore.services.identity_safety import stage_holds, assert_hold_snapshot
from mlcore.services.redirect_writes import MAX_REDIRECT_DEPTH, follow_redirects, run_bulk

PROVIDER = 'spotify'
RESOLVED_BY = 'final_target_spotify_alias'
RECONCILED_BY = 'reconcile_hydration_aliases'
STAGE_TABLE = 'mlcore_hydration_reconcile_stage'
ALIAS_TABLE = 'mlcore_hydration_reconcile_spotify'
DEFAULT_BATCH_SIZE = 50_000
IDENTIFIER_RE = r'^[A-Za-z_][A-Za-z0-9_]{0,62}$'


@dataclass(frozen=True)
class HydrationReconcileResult:
    staged: int
    resolvable: int
    unresolved_redirect_depth: int
    matched: int
    skipped_busy: int
    dry_run: bool
    elapsed_seconds: float


STAGE_PENDING_SQL = f'''
    INSERT INTO {STAGE_TABLE} (item_id, final_id, depth)
    SELECT i.id, i.canonical_item_id, 0
    FROM {ProviderHydrationItem._meta.db_table} i
    WHERE i.provider = %s
      AND i.status IN ('pending', 'retry')
      AND NOT (i.evidence ? 'identity_reference_quarantine')
      AND NOT EXISTS (SELECT 1 FROM tmp_identity_hold h WHERE h.scheme = 'isrc' AND h.value = i.identifier)
      AND (i.lease_expires_at IS NULL OR i.lease_expires_at <= NOW())
      AND i.id > %s
    ORDER BY i.id
'''

STAGE_SPOTIFY_ALIASES_SQL = f'''
    INSERT INTO {ALIAS_TABLE} (canonical_item_id, spotify_id)
    SELECT DISTINCT ON (a.canonical_item_id) a.canonical_item_id, a.source_id
    FROM mlcore_canonical_item_alias a
    WHERE a.source = 'spotify' AND a.resource_type = 'track' AND a.status = 'active'
      AND NOT (a.metadata ? 'identity_reference_quarantine')
    ORDER BY a.canonical_item_id, a.source_id
'''

# Joined once, both sides staged TEMP tables (hash join); rows without an answer are dropped.
RESOLVE_SQL = f'''
    UPDATE {STAGE_TABLE} stage
    SET spotify_id = alias.spotify_id
    FROM {ALIAS_TABLE} alias
    WHERE alias.canonical_item_id = stage.final_id AND stage.depth < %s
'''

# One locked, filtered subquery joined to the queue on its primary key (no CTE-to-CTE join: the planner
# cannot estimate CTE sizes and chose a quadratic nested loop in a measured run).
APPLY_SLICE_SQL = f'''
    UPDATE {ProviderHydrationItem._meta.db_table} i
    SET status = 'matched',
        evidence = i.evidence || jsonb_build_object(
            'resolved_by', %s,
            'final_canonical_item_id', picked.final_id::text,
            'spotify_id', picked.spotify_id,
            'reconciled_by', %s,
            'reconciled_at', NOW()::text
        ),
        last_error = '',
        next_attempt_at = NULL,
        leased_by = '',
        lease_expires_at = NULL,
        updated_at = NOW()
    FROM (
        SELECT q.id, stage.final_id, stage.spotify_id
        FROM {STAGE_TABLE} stage
        JOIN {ProviderHydrationItem._meta.db_table} q ON q.id = stage.item_id
        WHERE stage.spotify_id IS NOT NULL
          AND stage.item_id > %s AND stage.item_id <= %s
          AND q.id > %s AND q.id <= %s  -- a contiguous primary-key range scan, not per-row probes
          AND q.status IN ('pending', 'retry')
          AND (q.lease_expires_at IS NULL OR q.lease_expires_at <= NOW())
        ORDER BY q.id
        FOR UPDATE OF q SKIP LOCKED
    ) picked
    WHERE i.id = picked.id AND i.id > %s AND i.id <= %s
'''


def reconcile_hydration_with_spotify_aliases(
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    after_id: int = 0,
    limit: int | None = None,
    dry_run: bool = False,
    staging_tablespace: str | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> HydrationReconcileResult:
    if batch_size < 1:
        raise ValueError('batch_size must be greater than zero')
    if limit is not None and limit < 1:
        raise ValueError('limit must be greater than zero')
    started = time.monotonic()
    quote = connection.ops.quote_name
    if staging_tablespace is not None:
        if not re.match(IDENTIFIER_RE, staging_tablespace):
            raise ValueError(f'Invalid tablespace name: {staging_tablespace!r}')
    stage_holds()
    with connection.cursor() as cursor:
        if staging_tablespace:
            cursor.execute(f'SET temp_tablespaces = {quote(staging_tablespace)}')
        cursor.execute(f'DROP TABLE IF EXISTS {STAGE_TABLE}')
        cursor.execute(f'DROP TABLE IF EXISTS {ALIAS_TABLE}')
        cursor.execute(
            f'CREATE TEMP TABLE {STAGE_TABLE} ('
            'item_id bigint PRIMARY KEY, final_id uuid NOT NULL, depth integer NOT NULL, spotify_id varchar(512))'
        )
        cursor.execute(f'CREATE TEMP TABLE {ALIAS_TABLE} (canonical_item_id uuid PRIMARY KEY, spotify_id varchar(512) NOT NULL)')
    try:
        return _reconcile(
            batch_size=batch_size, after_id=after_id, limit=limit, dry_run=dry_run,
            started=started, progress_callback=progress_callback,
        )
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS {STAGE_TABLE}')
            cursor.execute(f'DROP TABLE IF EXISTS {ALIAS_TABLE}')
            if staging_tablespace:
                cursor.execute('RESET temp_tablespaces')


def _reconcile(*, batch_size, after_id, limit, dry_run, started, progress_callback) -> HydrationReconcileResult:
    sql = STAGE_PENDING_SQL + (' LIMIT %s' if limit is not None else '')
    params = [PROVIDER, after_id] + ([limit] if limit is not None else [])
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        staged = max(cursor.rowcount, 0)
        cursor.execute(STAGE_SPOTIFY_ALIASES_SQL)
        cursor.execute(f'ANALYZE {STAGE_TABLE}')
        cursor.execute(f'ANALYZE {ALIAS_TABLE}')
    _report(progress_callback, {'event': 'reconcile_staged', 'staged': staged})

    follow_redirects(STAGE_TABLE, progress=lambda message: _report(progress_callback, {'event': 'reconcile_hop', 'message': message}))
    run_bulk(RESOLVE_SQL, [MAX_REDIRECT_DEPTH])
    with connection.cursor() as cursor:
        cursor.execute(f'ANALYZE {STAGE_TABLE}')  # the slices below are planned from these counts
        cursor.execute(f'SELECT COUNT(*) FILTER (WHERE spotify_id IS NOT NULL), COUNT(*) FILTER (WHERE depth >= %s) FROM {STAGE_TABLE}',
                       [MAX_REDIRECT_DEPTH])
        resolvable, unresolved_depth = (int(value) for value in cursor.fetchone())
    _report(progress_callback, {'event': 'reconcile_resolved', 'resolvable': resolvable})

    matched = skipped = processed = 0
    lower = 0
    apply_started = time.monotonic()
    while not dry_run and processed < resolvable:
        with connection.cursor() as cursor:
            cursor.execute(
                f'''
                SELECT MAX(item_id), COUNT(*) FROM (
                    SELECT item_id FROM {STAGE_TABLE}
                    WHERE spotify_id IS NOT NULL AND item_id > %s ORDER BY item_id LIMIT %s
                ) next_slice
                ''',
                [lower, batch_size],
            )
            upper, slice_rows = cursor.fetchone()
        if not slice_rows:
            break
        with transaction.atomic(), connection.cursor() as cursor:
            assert_hold_snapshot()
            cursor.execute(APPLY_SLICE_SQL, [RESOLVED_BY, RECONCILED_BY, lower, upper, lower, upper, lower, upper])
            updated = max(cursor.rowcount, 0)
        matched += updated
        skipped += slice_rows - updated
        processed += slice_rows
        lower = upper
        elapsed = max(time.monotonic() - apply_started, 0.001)
        rate = processed / elapsed
        _report(progress_callback, {
            'event': 'reconcile_batch',
            'processed': processed,
            'resolvable': resolvable,
            'matched': matched,
            'last_item_id': upper,
            'rows_per_second': rate,
            'eta_seconds': (resolvable - processed) / rate if rate else None,
        })
    return HydrationReconcileResult(
        staged=staged,
        resolvable=resolvable,
        unresolved_redirect_depth=unresolved_depth,
        matched=matched,
        skipped_busy=skipped,
        dry_run=dry_run,
        elapsed_seconds=time.monotonic() - started,
    )


def _report(callback, payload) -> None:
    if callback is not None:
        callback(payload)

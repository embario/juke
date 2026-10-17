"""Shared set-based helpers for writing canonical redirects (identity graph saturation B6/B7).

Rules every bulk redirect writer follows:

* **Never change an existing active redirect.** New edges are inserted with
  ``ON CONFLICT (from_canonical_item_id) DO NOTHING``; a disagreeing existing edge is left alone and
  the caller counts it.
* **Flat.** Edges point at the final target. When an item that others redirect to (a *root*) gains
  its own redirect, its inbound active redirects are repointed at the new target in the same
  transaction, so chains stay one hop. That repoint is the only update ever made to an existing edge.
* **Set-based.** The pool manages about 65 random index lookups per second, so large tables are only
  ever joined to small staged TEMP tables in one hash-join pass (see :func:`bulk_join_mode`); the
  per-batch writes then go through primary keys only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from django.db import connection, transaction

MAX_REDIRECT_DEPTH = 8

# Planner switches that force hash joins over sequential scans for one statement.
BULK_JOIN_SETTINGS = (
    'enable_nestloop',
    'enable_mergejoin',
    'enable_indexscan',
    'enable_indexonlyscan',
    'enable_bitmapscan',
)


def bulk_join_mode(cursor) -> None:
    """Call inside a transaction: ``SET LOCAL`` ends with it, so other statements keep normal plans."""
    for setting in BULK_JOIN_SETTINGS:
        cursor.execute(f'SET LOCAL {setting} = off')


def run_bulk(sql: str, params: Sequence[Any] | None = None) -> int:
    """Run one statement in its own transaction with hash joins forced; return its row count."""
    with transaction.atomic(), connection.cursor() as cursor:
        bulk_join_mode(cursor)
        cursor.execute(sql, list(params or []))
        return max(cursor.rowcount, 0)


def explain(sql: str, params: Sequence[Any] | None = None, *, bulk: bool = True) -> list[str]:
    with transaction.atomic(), connection.cursor() as cursor:
        if bulk:
            bulk_join_mode(cursor)
        cursor.execute('EXPLAIN ' + sql, list(params or []))
        return [row[0] for row in cursor.fetchall()]


FOLLOW_REDIRECT_HOP_SQL = '''
    UPDATE {table} t
    SET final_id = redirect.to_canonical_item_id, depth = t.depth + 1
    FROM mlcore_canonical_item_redirect redirect
    WHERE redirect.from_canonical_item_id = t.final_id
      AND redirect.status = 'active'
      AND t.depth < %s
'''


def follow_redirects(table: str, *, max_depth: int = MAX_REDIRECT_DEPTH, progress=None) -> int:
    """Resolve ``table(item_id, final_id, depth)`` to final targets, one redirect-table pass per hop.

    Start with ``final_id = item_id`` and ``depth = 0``. Rows that still move at ``max_depth`` keep
    ``depth = max_depth``; callers treat those as unresolved (cycle or too deep). Returns hops run.
    """
    sql = FOLLOW_REDIRECT_HOP_SQL.format(table=table)
    for hop in range(max_depth):
        moved = run_bulk(sql, [max_depth])
        if progress is not None:
            progress(f'redirect hop={hop + 1} moved={moved}')
        if moved == 0:
            return hop + 1
    return max_depth


STAGE_INBOUND_SQL = '''
    INSERT INTO {inbound_table} (from_id, root_id)
    SELECT redirect.from_canonical_item_id, redirect.to_canonical_item_id
    FROM mlcore_canonical_item_redirect redirect
    JOIN {roots_table} roots ON roots.{root_column} = redirect.to_canonical_item_id
    WHERE redirect.status = 'active'
    ON CONFLICT (from_id) DO NOTHING
'''


def create_inbound_table(name: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'DROP TABLE IF EXISTS {name}')
        cursor.execute(f'CREATE TEMP TABLE {name} (from_id uuid PRIMARY KEY, root_id uuid NOT NULL)')


def stage_inbound_redirects(*, roots_table: str, root_column: str, inbound_table: str) -> int:
    """Collect active redirects that point at any staged root, in one hash-join scan of the redirects."""
    count = run_bulk(STAGE_INBOUND_SQL.format(
        inbound_table=inbound_table, roots_table=roots_table, root_column=root_column,
    ))
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE INDEX ON {inbound_table} (root_id)')
        cursor.execute(f'ANALYZE {inbound_table}')
    return count


@dataclass(frozen=True)
class RedirectBatchResult:
    processed: int
    last_key: str | None
    inserted: int
    repointed: int


# ``batch_sql`` must yield: from_id uuid, to_id uuid, confidence float, evidence jsonb, batch_key text.
INSERT_FLAT_REDIRECTS_SQL = '''
    WITH batch AS MATERIALIZED ({batch_sql}),
    inserted AS (
        INSERT INTO mlcore_canonical_item_redirect (
            from_canonical_item_id, to_canonical_item_id, relation, confidence, source, source_version,
            status, evidence, created_at, updated_at
        )
        SELECT b.from_id, b.to_id, 'same_recording', b.confidence, %s, %s, 'active', b.evidence, NOW(), NOW()
        FROM batch b
        WHERE b.from_id <> b.to_id
        ON CONFLICT (from_canonical_item_id) DO NOTHING
        RETURNING from_canonical_item_id, to_canonical_item_id
    ),
    repointed AS (
        UPDATE mlcore_canonical_item_redirect redirect
        SET to_canonical_item_id = ins.to_canonical_item_id,
            evidence = redirect.evidence || jsonb_build_object(
                'repointed_from', redirect.to_canonical_item_id::text,
                'repointed_by', %s
            ),
            updated_at = NOW()
        FROM {inbound_table} inbound
        JOIN inserted ins ON ins.from_canonical_item_id = inbound.root_id
        WHERE redirect.from_canonical_item_id = inbound.from_id
          AND redirect.to_canonical_item_id = inbound.root_id
          AND redirect.status = 'active'
          AND redirect.from_canonical_item_id <> ins.to_canonical_item_id
        RETURNING 1
    )
    SELECT
        (SELECT COUNT(*) FROM batch),
        (SELECT batch_key FROM batch ORDER BY batch_key DESC LIMIT 1),
        (SELECT COUNT(*) FROM inserted),
        (SELECT COUNT(*) FROM repointed)
'''

DRY_RUN_FLAT_REDIRECTS_SQL = '''
    WITH batch AS MATERIALIZED ({batch_sql})
    SELECT
        (SELECT COUNT(*) FROM batch),
        (SELECT batch_key FROM batch ORDER BY batch_key DESC LIMIT 1),
        (SELECT COUNT(*) FROM batch WHERE from_id <> to_id),
        (SELECT COUNT(*) FROM {inbound_table} inbound JOIN batch b ON b.from_id = inbound.root_id)
'''


def insert_flat_redirects(
    *,
    batch_sql: str,
    batch_params: Sequence[Any],
    source: str,
    source_version: str,
    inbound_table: str,
    write: bool,
) -> RedirectBatchResult:
    """Insert one batch of flat redirects and repoint the inbound edges of every root that moved.

    In dry-run mode nothing is written and ``inserted``/``repointed`` are upper bounds (an edge that
    appeared since staging would be skipped by the real insert).
    """
    with transaction.atomic(), connection.cursor() as cursor:
        if write:
            cursor.execute(
                INSERT_FLAT_REDIRECTS_SQL.format(batch_sql=batch_sql, inbound_table=inbound_table),
                [*batch_params, source, source_version, source],
            )
        else:
            cursor.execute(
                DRY_RUN_FLAT_REDIRECTS_SQL.format(batch_sql=batch_sql, inbound_table=inbound_table),
                list(batch_params),
            )
        processed, last_key, inserted, repointed = cursor.fetchone()
    return RedirectBatchResult(int(processed or 0), last_key, int(inserted or 0), int(repointed or 0))

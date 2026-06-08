"""
Co-occurrence trainer (arch §5.4, §7.2).

Produces symmetric pairwise PMI scores from behavioral baskets and
persists them to mlcore_item_cooccurrence. A basket is any collection
of canonical item ids observed together (same search session, same playlist, etc).

PMI(a,b) = log2(P(a,b) / (P(a) * P(b)))
  where P(x)   = count_baskets_containing_x / N
        P(a,b) = co_count / N
No smoothing needed: we only store pairs with co_count >= 1, and any
item in a stored pair has item_count >= 1, so the log is always finite.

Pairs are stored canonically (a < b lexicographic) so the table holds
exactly one row per unordered pair.
"""
from __future__ import annotations

import hashlib
import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable
from uuid import UUID

from catalog.models import SearchHistoryResource, Track
from django.db import connection, transaction
from django.utils import timezone
from mlcore.models import (
    ItemCoOccurrence,
    ListenBrainzSessionTrack,
    SourceIngestionRun,
    TrainingRun,
)
from mlcore.services.canonical_items import bulk_ensure_canonical_items_for_tracks
from mlcore.services.cooccurrence_progress import (
    ensure_cooccurrence_bucket_rows,
    mark_bucket_failed,
    mark_bucket_running,
    mark_bucket_succeeded,
    mark_prior_buckets_assumed_succeeded,
    pending_bucket_indices,
)

logger = logging.getLogger(__name__)

MIN_BASKET_SIZE = 2
_SPLIT_BUCKET_COUNT = 10
_TEST_BUCKET = 0
WRITE_BATCH_SIZE = 1000
DEFAULT_RESOURCE_TYPE = "track"
BEHAVIOR_SOURCE_SEARCH_HISTORY = 'search_history'
BEHAVIOR_SOURCE_LISTENBRAINZ = 'listenbrainz'
SUPPORTED_BEHAVIOR_SOURCES = (
    BEHAVIOR_SOURCE_SEARCH_HISTORY,
    BEHAVIOR_SOURCE_LISTENBRAINZ,
)
DEFAULT_BEHAVIOR_SOURCES = (
    BEHAVIOR_SOURCE_SEARCH_HISTORY,
    BEHAVIOR_SOURCE_LISTENBRAINZ,
)
SQL_TRAINING_HASH_VERSION = "listenbrainz_sql_v1"
SQL_PAIR_BUCKET_COUNT = 128
SQL_MAX_BASKET_ITEMS = 20
SQL_TRAINING_WORK_MEM = "512MB"
SQL_TRAINING_MAINTENANCE_WORK_MEM = "1GB"
SQL_TRAINING_MAX_PARALLEL_WORKERS = 4
SQL_LISTENBRAINZ_ALGORITHM_VERSION = f"{SQL_TRAINING_HASH_VERSION}_max{SQL_MAX_BASKET_ITEMS}"
SQL_PAIR_BUCKET_INDEX_EXPR = (
    "mod(abs(hashtextextended(encode(session_key, 'hex'), 0)), "
    f"{SQL_PAIR_BUCKET_COUNT})"
)


@dataclass
class TrainingResult:
    baskets_processed: int
    baskets_skipped: int
    items_seen: int
    pairs_written: int
    training_hash: str
    source_row_count: int
    training_run_id: UUID | None = None


def _canonical_pair(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    """Order a pair lexicographically so (a,b) and (b,a) collapse to one key."""
    return (a, b) if str(a) < str(b) else (b, a)


def _split_bucket(session_key: int | str | bytes | memoryview, bucket_count: int) -> int:
    if isinstance(session_key, int):
        return session_key % bucket_count

    if isinstance(session_key, memoryview):
        session_key = session_key.tobytes()

    if isinstance(session_key, bytes):
        digest = hashlib.sha256(session_key).hexdigest()
        return int(digest[:16], 16) % bucket_count

    digest = hashlib.sha256(str(session_key).encode('utf-8')).hexdigest()
    return int(digest[:16], 16) % bucket_count


def _is_in_split(session_key: int | str | bytes | memoryview, split: str, bucket_count: int) -> bool:
    bucket = _split_bucket(session_key, bucket_count)
    if split == "all":
        return True
    if split == "train":
        return bucket != _TEST_BUCKET
    if split == "test":
        return bucket == _TEST_BUCKET
    raise ValueError(f"Unknown split '{split}'; expected 'train', 'test', or 'all'")


def _baskets_to_hash(baskets: list[list[UUID]]) -> str:
    hasher = hashlib.sha256()
    lines = sorted(
        ",".join(sorted(str(item) for item in set(basket)))
        for basket in baskets
    )
    for line in lines:
        if line:
            hasher.update(line.encode("utf-8"))
            hasher.update(b"\n")
    return hasher.hexdigest()


def baskets_from_search_history(
    resource_type: str = DEFAULT_RESOURCE_TYPE,
    split: str = "all",
    split_buckets: int = _SPLIT_BUCKET_COUNT,
) -> list[list[UUID]]:
    """Back-compat wrapper for callers that only need baskets."""
    baskets, _ = baskets_from_search_history_with_count(resource_type, split, split_buckets)
    return baskets


def baskets_from_search_history_with_count(
    resource_type: str = DEFAULT_RESOURCE_TYPE,
    split: str = "all",
    split_buckets: int = _SPLIT_BUCKET_COUNT,
) -> tuple[list[list[UUID]], int]:
    return baskets_from_behavioral_sources_with_count(
        resource_type=resource_type,
        split=split,
        split_buckets=split_buckets,
        sources=[BEHAVIOR_SOURCE_SEARCH_HISTORY],
    )


def baskets_from_behavioral_sources(
    resource_type: str = DEFAULT_RESOURCE_TYPE,
    split: str = "all",
    split_buckets: int = _SPLIT_BUCKET_COUNT,
    sources: Iterable[str] | None = None,
) -> list[list[UUID]]:
    baskets, _ = baskets_from_behavioral_sources_with_count(
        resource_type=resource_type,
        split=split,
        split_buckets=split_buckets,
        sources=sources,
    )
    return baskets


def _normalized_sources(sources: Iterable[str] | None) -> tuple[str, ...]:
    if sources is None:
        return DEFAULT_BEHAVIOR_SOURCES

    normalized: list[str] = []
    for source in sources:
        if source not in SUPPORTED_BEHAVIOR_SOURCES:
            raise ValueError(
                f"Unknown behavior source '{source}'; expected one of {sorted(SUPPORTED_BEHAVIOR_SOURCES)}"
            )
        if source not in normalized:
            normalized.append(source)
    return tuple(normalized)


def _append_search_history_baskets(
    *,
    resource_type: str,
    split: str,
    split_buckets: int,
    session_to_jukes: dict[tuple[str, str | bytes], set[UUID]],
) -> int:
    rows = SearchHistoryResource.objects.filter(resource_type=resource_type).values_list(
        "search_history_id", "resource_id"
    )

    if not rows:
        return 0

    if resource_type != DEFAULT_RESOURCE_TYPE:
        raise ValueError(f"resource_type '{resource_type}' not supported in Phase 1")

    session_to_pks: dict[int, set[int]] = defaultdict(set)
    source_row_count = 0
    for session_id, pk in rows:
        if _is_in_split(session_id, split, split_buckets):
            session_to_pks[session_id].add(pk)
            source_row_count += 1

    all_pks: set[int] = set()
    for pks in session_to_pks.values():
        all_pks.update(pks)

    if not all_pks:
        return source_row_count

    tracks = list(Track.objects.filter(pk__in=all_pks))
    canonical_by_track_id = bulk_ensure_canonical_items_for_tracks(tracks)
    pk_to_canonical_item_id: dict[int, UUID] = {
        track.pk: canonical_by_track_id[track.juke_id].pk
        for track in tracks
        if track.juke_id in canonical_by_track_id
    }

    for session_id, pks in session_to_pks.items():
        session_to_jukes[(BEHAVIOR_SOURCE_SEARCH_HISTORY, str(session_id))].update(
            pk_to_canonical_item_id[pk] for pk in pks if pk in pk_to_canonical_item_id
        )

    return source_row_count


def _append_listenbrainz_session_track_baskets(
    *,
    split: str,
    split_buckets: int,
    session_to_jukes: dict[tuple[str, str | bytes], set[UUID]],
) -> int:
    rows = ListenBrainzSessionTrack.objects.values_list('session_key', 'canonical_item_id')
    source_row_count = 0
    for session_key, canonical_item_id in rows:
        if not _is_in_split(session_key, split, split_buckets):
            continue
        if canonical_item_id is None:
            continue
        normalized_session_key = session_key.tobytes() if isinstance(session_key, memoryview) else bytes(session_key)
        session_to_jukes[(BEHAVIOR_SOURCE_LISTENBRAINZ, normalized_session_key)].add(canonical_item_id)
        source_row_count += 1

    return source_row_count


def _sql_split_bucket_expr(bucket_count: int) -> str:
    if bucket_count <= 0:
        raise ValueError("split_buckets must be > 0")
    return f"mod(abs(hashtextextended(encode(session_key, 'hex'), 0)), {bucket_count})"


def _sql_pair_bucket_expr(alias: str = "session_key") -> str:
    session_key_sql = f"{alias}.session_key" if alias != "session_key" else alias
    return (
        "mod(abs(hashtextextended(encode("
        f"{session_key_sql}, 'hex'), 0)), {SQL_PAIR_BUCKET_COUNT})"
    )


def _sql_split_predicate(split: str, split_buckets: int) -> tuple[str, list[int]]:
    if split == "all":
        return "TRUE", []
    if split == "train":
        return f"{_sql_split_bucket_expr(split_buckets)} <> 0", []
    if split == "test":
        return f"{_sql_split_bucket_expr(split_buckets)} = 0", []
    raise ValueError(f"Unknown split '{split}'; expected 'train', 'test', or 'all'")


def _sql_listenbrainz_training_hash(
    *,
    split: str,
    split_buckets: int,
) -> str:
    latest_run = (
        SourceIngestionRun.objects.filter(source="listenbrainz", status="succeeded")
        .order_by("-started_at")
        .values_list("source_version", flat=True)
        .first()
        or ""
    )
    payload = (
        f"{SQL_TRAINING_HASH_VERSION}:"
        f"{split}:{split_buckets}:{SQL_MAX_BASKET_ITEMS}:{latest_run}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _train_cooccurrence_listenbrainz_sql(
    *,
    split: str,
    split_buckets: int,
    resume_training_run_id: UUID | None = None,
    start_bucket: int = 0,
    resume: bool = False,
) -> TrainingResult:
    if start_bucket < 0 or start_bucket >= SQL_PAIR_BUCKET_COUNT:
        raise ValueError(f"start_bucket must be between 0 and {SQL_PAIR_BUCKET_COUNT - 1}")

    split_predicate, split_params = _sql_split_predicate(split, split_buckets)

    training_hash = _sql_listenbrainz_training_hash(
        split=split,
        split_buckets=split_buckets,
    )

    result = TrainingResult(
        baskets_processed=0,
        baskets_skipped=0,
        items_seen=0,
        pairs_written=0,
        training_hash=training_hash,
        source_row_count=0,
    )

    if resume_training_run_id is None:
        run = TrainingRun.objects.create(
            ranker_label="cooccurrence",
            training_hash=training_hash,
            baskets_processed=result.baskets_processed,
            baskets_skipped=result.baskets_skipped,
            items_seen=result.items_seen,
            pairs_written=result.pairs_written,
            source_row_count=result.source_row_count,
        )
        should_truncate_pairs = True
    else:
        run = TrainingRun.objects.get(pk=resume_training_run_id, ranker_label="cooccurrence")
        training_hash = run.training_hash
        result.training_hash = training_hash
        should_truncate_pairs = False
    result.training_run_id = run.pk

    ensure_cooccurrence_bucket_rows(
        training_run=run,
        source=BEHAVIOR_SOURCE_LISTENBRAINZ,
        algorithm_version=SQL_LISTENBRAINZ_ALGORITHM_VERSION,
        bucket_count=SQL_PAIR_BUCKET_COUNT,
    )
    if start_bucket > 0:
        mark_prior_buckets_assumed_succeeded(
            training_run=run,
            start_bucket=start_bucket,
            bucket_count=SQL_PAIR_BUCKET_COUNT,
            reason=(
                "manual resume from committed pre-metadata buckets"
                if resume_training_run_id is not None
                else "manual start bucket"
            ),
        )

    staging_counts_sql = """
        SELECT
            EXISTS (
                SELECT 1
                FROM mlcore_cooccurrence_training_basket
                WHERE training_run_id = %s
                LIMIT 1
            ),
            EXISTS (
                SELECT 1
                FROM mlcore_cooccurrence_training_session_item
                WHERE training_run_id = %s
                LIMIT 1
            )
    """
    clear_staging_sql = [
        "DELETE FROM mlcore_cooccurrence_training_pair WHERE training_run_id = %s",
        "DELETE FROM mlcore_cooccurrence_training_session_item WHERE training_run_id = %s",
        "DELETE FROM mlcore_cooccurrence_training_basket WHERE training_run_id = %s",
    ]
    create_basket_staging_sql = f"""
        INSERT INTO mlcore_cooccurrence_training_basket (
            training_run_id,
            source,
            algorithm_version,
            bucket_count,
            bucket_index,
            session_key,
            item_count,
            created_at
        )
        WITH eligible AS (
            SELECT session_key, COUNT(*)::integer AS item_count
            FROM mlcore_listenbrainz_session_track
            WHERE canonical_item_id IS NOT NULL
              AND {split_predicate}
            GROUP BY session_key
            HAVING COUNT(*) >= %s
               AND COUNT(*) <= %s
        )
        SELECT
            %s,
            %s,
            %s,
            %s,
            {_sql_pair_bucket_expr("eligible")}::integer,
            session_key,
            item_count,
            NOW()
        FROM eligible
        ON CONFLICT DO NOTHING
    """
    create_session_item_staging_sql = """
        INSERT INTO mlcore_cooccurrence_training_session_item (
            training_run_id,
            bucket_count,
            bucket_index,
            session_key,
            item_id,
            created_at
        )
        SELECT
            b.training_run_id,
            b.bucket_count,
            b.bucket_index,
            st.session_key,
            st.canonical_item_id,
            NOW()
        FROM mlcore_listenbrainz_session_track st
        JOIN mlcore_cooccurrence_training_basket b
          ON b.session_key = st.session_key
        WHERE b.training_run_id = %s
          AND st.canonical_item_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """
    counts_sql = """
        SELECT
            (SELECT COUNT(*)::integer FROM mlcore_cooccurrence_training_basket WHERE training_run_id = %s),
            (SELECT COUNT(*)::integer FROM mlcore_cooccurrence_training_session_item WHERE training_run_id = %s),
            (SELECT COUNT(DISTINCT item_id)::integer FROM mlcore_cooccurrence_training_session_item WHERE training_run_id = %s)
    """
    pair_bucket_sql = """
        WITH pair_counts AS (
            SELECT
                LEAST(a.item_id, b.item_id) AS item_a_juke_id,
                GREATEST(a.item_id, b.item_id) AS item_b_juke_id,
                COUNT(*)::integer AS co_count
            FROM mlcore_cooccurrence_training_session_item a
            JOIN mlcore_cooccurrence_training_session_item b
              ON a.training_run_id = b.training_run_id
             AND a.bucket_count = b.bucket_count
             AND a.bucket_index = b.bucket_index
             AND a.session_key = b.session_key
             AND a.item_id < b.item_id
            WHERE a.training_run_id = %s
              AND a.bucket_count = %s
              AND a.bucket_index = %s
            GROUP BY 1, 2
        )
        INSERT INTO mlcore_cooccurrence_training_pair (
            training_run_id,
            bucket_count,
            bucket_index,
            item_a_juke_id,
            item_b_juke_id,
            co_count,
            created_at
        )
        SELECT
            %s,
            %s,
            %s,
            item_a_juke_id,
            item_b_juke_id,
            co_count,
            NOW()
        FROM pair_counts
    """
    merge_staged_pair_bucket_sql = """
        INSERT INTO mlcore_item_cooccurrence (
            item_a_juke_id,
            item_b_juke_id,
            co_count,
            pmi_score,
            training_run_id,
            updated_at
        )
        SELECT
            item_a_juke_id,
            item_b_juke_id,
            co_count,
            0.0,
            %s,
            NOW()
        FROM mlcore_cooccurrence_training_pair
        WHERE training_run_id = %s
          AND bucket_count = %s
          AND bucket_index = %s
        ON CONFLICT (item_a_juke_id, item_b_juke_id)
        DO UPDATE SET
            co_count = mlcore_item_cooccurrence.co_count + EXCLUDED.co_count,
            pmi_score = 0.0,
            updated_at = EXCLUDED.updated_at,
            training_run_id = EXCLUDED.training_run_id
    """
    merged_bucket_count_sql = """
        SELECT COUNT(*)::integer
        FROM mlcore_cooccurrence_training_bucket
        WHERE training_run_id = %s
          AND bucket_count = %s
          AND metadata ? 'merged_at'
    """
    unmerged_bucket_indices_sql = """
        SELECT bucket_index
        FROM mlcore_cooccurrence_training_bucket
        WHERE training_run_id = %s
          AND bucket_count = %s
          AND status IN ('succeeded', 'assumed_succeeded')
          AND NOT (metadata ? 'merged_at')
        ORDER BY bucket_index
    """
    mark_bucket_merged_sql = """
        UPDATE mlcore_cooccurrence_training_bucket
        SET metadata = metadata || jsonb_build_object(
            'merged_at', %s,
            'merged_rows', %s
        )
        WHERE training_run_id = %s
          AND bucket_count = %s
          AND bucket_index = %s
    """
    pmi_bucket_count_sql = """
        SELECT COUNT(*)::integer
        FROM mlcore_cooccurrence_training_bucket
        WHERE training_run_id = %s
          AND bucket_count = %s
          AND metadata ? 'pmi_at'
    """
    unpmi_bucket_indices_sql = """
        SELECT bucket_index
        FROM mlcore_cooccurrence_training_bucket
        WHERE training_run_id = %s
          AND bucket_count = %s
          AND status IN ('succeeded', 'assumed_succeeded')
          AND metadata ? 'merged_at'
          AND NOT (metadata ? 'pmi_at')
        ORDER BY bucket_index
    """
    mark_bucket_pmi_sql = """
        UPDATE mlcore_cooccurrence_training_bucket
        SET metadata = metadata || jsonb_build_object(
            'pmi_at', %s,
            'pmi_rows', %s
        )
        WHERE training_run_id = %s
          AND bucket_count = %s
          AND bucket_index = %s
    """
    pmi_id_bounds_sql = """
        SELECT COALESCE(MIN(id), 0)::bigint, COALESCE(MAX(id), 0)::bigint
        FROM mlcore_item_cooccurrence
        WHERE training_run_id = %s
    """
    drop_pmi_item_counts_sql = "DROP TABLE IF EXISTS pg_temp.mlcore_pmi_item_count"
    create_pmi_item_counts_sql = """
        CREATE TEMP TABLE mlcore_pmi_item_count ON COMMIT PRESERVE ROWS AS
        SELECT
            item_id,
            COUNT(*)::double precision AS item_count
        FROM mlcore_cooccurrence_training_session_item
        WHERE training_run_id = %s
        GROUP BY item_id
    """
    index_pmi_item_counts_sql = """
        CREATE UNIQUE INDEX mlcore_pmi_item_count_item_id_idx
        ON mlcore_pmi_item_count (item_id)
    """
    analyze_pmi_item_counts_sql = "ANALYZE mlcore_pmi_item_count"
    update_pmi_bucket_sql = """
        UPDATE mlcore_item_cooccurrence ic
        SET
            pmi_score = (
                LN(
                    (ic.co_count / %s::double precision)
                    / ((ia.item_count / %s::double precision) * (ib.item_count / %s::double precision))
                ) / LN(2.0)
            )::double precision,
            training_run_id = %s,
            updated_at = NOW()
        FROM pg_temp.mlcore_pmi_item_count ia
        JOIN pg_temp.mlcore_pmi_item_count ib
          ON TRUE
        WHERE ia.item_id = ic.item_a_juke_id
          AND ib.item_id = ic.item_b_juke_id
          AND ic.training_run_id = %s
          AND ic.id >= %s
          AND ic.id < %s
    """
    delete_staged_pairs_sql = "DELETE FROM mlcore_cooccurrence_training_pair WHERE training_run_id = %s"
    with connection.cursor() as cursor:
        cursor.execute("SET work_mem = %s", [SQL_TRAINING_WORK_MEM])
        cursor.execute("SET maintenance_work_mem = %s", [SQL_TRAINING_MAINTENANCE_WORK_MEM])
        cursor.execute("SET max_parallel_workers_per_gather = %s", [SQL_TRAINING_MAX_PARALLEL_WORKERS])
        cursor.execute(staging_counts_sql, [str(run.pk), str(run.pk)])
        staged_baskets_present, staged_items_present = cursor.fetchone()

    if not staged_baskets_present or not staged_items_present:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET work_mem = %s", [SQL_TRAINING_WORK_MEM])
                cursor.execute("SET maintenance_work_mem = %s", [SQL_TRAINING_MAINTENANCE_WORK_MEM])
                cursor.execute("SET max_parallel_workers_per_gather = %s", [SQL_TRAINING_MAX_PARALLEL_WORKERS])
                for statement in clear_staging_sql:
                    cursor.execute(statement, [str(run.pk)])
                cursor.execute(
                    create_basket_staging_sql,
                    [
                        *split_params,
                        MIN_BASKET_SIZE,
                        SQL_MAX_BASKET_ITEMS,
                        str(run.pk),
                        BEHAVIOR_SOURCE_LISTENBRAINZ,
                        SQL_LISTENBRAINZ_ALGORITHM_VERSION,
                        SQL_PAIR_BUCKET_COUNT,
                    ],
                )
                cursor.execute(create_session_item_staging_sql, [str(run.pk)])
        baskets_skipped = 0
        with connection.cursor() as cursor:
            cursor.execute(counts_sql, [str(run.pk), str(run.pk), str(run.pk)])
            baskets_processed, source_row_count, items_seen = cursor.fetchone()
    else:
        baskets_skipped = 0
        if resume_training_run_id is not None and run.baskets_processed and run.source_row_count and run.items_seen:
            baskets_processed = run.baskets_processed
            source_row_count = run.source_row_count
            items_seen = run.items_seen
        else:
            with connection.cursor() as cursor:
                cursor.execute(counts_sql, [str(run.pk), str(run.pk), str(run.pk)])
                baskets_processed, source_row_count, items_seen = cursor.fetchone()

    run.baskets_processed = baskets_processed
    run.baskets_skipped = baskets_skipped
    run.items_seen = items_seen
    run.source_row_count = source_row_count
    run.save(
        update_fields=[
            "baskets_processed",
            "baskets_skipped",
            "items_seen",
            "source_row_count",
        ]
    )

    if should_truncate_pairs:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE mlcore_item_cooccurrence")

    bucket_indices = pending_bucket_indices(
        training_run=run,
        bucket_count=SQL_PAIR_BUCKET_COUNT,
        start_bucket=start_bucket,
        resume=resume,
    )
    for bucket in bucket_indices:
        mark_bucket_running(
            training_run_id=run.pk,
            bucket_count=SQL_PAIR_BUCKET_COUNT,
            bucket_index=bucket,
        )
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(delete_staged_pairs_sql + " AND bucket_index = %s", [str(run.pk), bucket])
                    cursor.execute(
                        pair_bucket_sql,
                        [
                            str(run.pk),
                            SQL_PAIR_BUCKET_COUNT,
                            bucket,
                            str(run.pk),
                            SQL_PAIR_BUCKET_COUNT,
                            bucket,
                        ],
                    )
                    rows_written = max(cursor.rowcount, 0)
        except Exception as exc:
            mark_bucket_failed(
                training_run_id=run.pk,
                bucket_count=SQL_PAIR_BUCKET_COUNT,
                bucket_index=bucket,
                error=exc,
            )
            raise
        mark_bucket_succeeded(
            training_run_id=run.pk,
            bucket_count=SQL_PAIR_BUCKET_COUNT,
            bucket_index=bucket,
            rows_written=rows_written,
        )
        logger.info(
            "train_cooccurrence_listenbrainz_sql: completed pair bucket %d/%d rows=%d run=%s",
            bucket + 1,
            SQL_PAIR_BUCKET_COUNT,
            rows_written,
            run.pk,
        )

    if resume_training_run_id is not None and run.pairs_written:
        pairs_written = run.pairs_written
        logger.info(
            "train_cooccurrence_listenbrainz_sql: skipping staged pair merge for already-merged run=%s pairs=%d",
            run.pk,
            pairs_written,
        )
    else:
        with connection.cursor() as cursor:
            cursor.execute(merged_bucket_count_sql, [str(run.pk), SQL_PAIR_BUCKET_COUNT])
            (merged_bucket_count,) = cursor.fetchone()
            cursor.execute(unmerged_bucket_indices_sql, [str(run.pk), SQL_PAIR_BUCKET_COUNT])
            merge_bucket_indices = [row[0] for row in cursor.fetchall()]

        if merged_bucket_count == 0 and merge_bucket_indices:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("TRUNCATE TABLE mlcore_item_cooccurrence RESTART IDENTITY")

        for bucket in merge_bucket_indices:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET work_mem = %s", [SQL_TRAINING_WORK_MEM])
                    cursor.execute("SET maintenance_work_mem = %s", [SQL_TRAINING_MAINTENANCE_WORK_MEM])
                    cursor.execute("SET max_parallel_workers_per_gather = %s", [SQL_TRAINING_MAX_PARALLEL_WORKERS])
                    cursor.execute(
                        merge_staged_pair_bucket_sql,
                        [str(run.pk), str(run.pk), SQL_PAIR_BUCKET_COUNT, bucket],
                    )
                    rows_merged = max(cursor.rowcount, 0)
                    cursor.execute(
                        mark_bucket_merged_sql,
                        [timezone.now().isoformat(), rows_merged, str(run.pk), SQL_PAIR_BUCKET_COUNT, bucket],
                    )
            logger.info(
                "train_cooccurrence_listenbrainz_sql: merged pair bucket %d/%d rows=%d run=%s",
                bucket + 1,
                SQL_PAIR_BUCKET_COUNT,
                rows_merged,
                run.pk,
            )

        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*)::bigint FROM mlcore_item_cooccurrence")
            (pairs_written,) = cursor.fetchone()

        run.baskets_processed = baskets_processed
        run.baskets_skipped = baskets_skipped
        run.items_seen = items_seen
        run.pairs_written = pairs_written
        run.source_row_count = source_row_count
        run.save(
            update_fields=[
                "baskets_processed",
                "baskets_skipped",
                "items_seen",
                "pairs_written",
                "source_row_count",
            ]
        )

    with connection.cursor() as cursor:
        cursor.execute(pmi_bucket_count_sql, [str(run.pk), SQL_PAIR_BUCKET_COUNT])
        (pmi_bucket_count,) = cursor.fetchone()
        cursor.execute(unpmi_bucket_indices_sql, [str(run.pk), SQL_PAIR_BUCKET_COUNT])
        pmi_bucket_indices = [row[0] for row in cursor.fetchall()]

    if pmi_bucket_indices:
        with connection.cursor() as cursor:
            cursor.execute("SET work_mem = %s", ["128MB"])
            cursor.execute("SET maintenance_work_mem = %s", [SQL_TRAINING_MAINTENANCE_WORK_MEM])
            cursor.execute("SET max_parallel_workers_per_gather = 0")
            cursor.execute(drop_pmi_item_counts_sql)
            cursor.execute(create_pmi_item_counts_sql, [str(run.pk)])
            cursor.execute(index_pmi_item_counts_sql)
            cursor.execute(analyze_pmi_item_counts_sql)
            cursor.execute(pmi_id_bounds_sql, [str(run.pk)])
            min_pair_id, max_pair_id = cursor.fetchone()

        if max_pair_id:
            bucket_width = max(1, ((max_pair_id - min_pair_id + 1) + SQL_PAIR_BUCKET_COUNT - 1) // SQL_PAIR_BUCKET_COUNT)
            for bucket in pmi_bucket_indices:
                lower_id = min_pair_id + (bucket * bucket_width)
                upper_id = max_pair_id + 1 if bucket == SQL_PAIR_BUCKET_COUNT - 1 else lower_id + bucket_width
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET work_mem = %s", [SQL_TRAINING_WORK_MEM])
                        cursor.execute("SET maintenance_work_mem = %s", [SQL_TRAINING_MAINTENANCE_WORK_MEM])
                        cursor.execute("SET max_parallel_workers_per_gather = %s", [SQL_TRAINING_MAX_PARALLEL_WORKERS])
                        cursor.execute(
                            update_pmi_bucket_sql,
                            [
                                baskets_processed,
                                baskets_processed,
                                baskets_processed,
                                str(run.pk),
                                str(run.pk),
                                lower_id,
                                upper_id,
                            ],
                        )
                        rows_pmi = max(cursor.rowcount, 0)
                        cursor.execute(
                            mark_bucket_pmi_sql,
                            [timezone.now().isoformat(), rows_pmi, str(run.pk), SQL_PAIR_BUCKET_COUNT, bucket],
                        )
                logger.info(
                    "train_cooccurrence_listenbrainz_sql: updated PMI bucket %d/%d rows=%d run=%s",
                    bucket + 1,
                    SQL_PAIR_BUCKET_COUNT,
                    rows_pmi,
                    run.pk,
                )
    else:
        logger.info(
            "train_cooccurrence_listenbrainz_sql: skipping PMI update for already-updated run=%s buckets=%d",
            run.pk,
            pmi_bucket_count,
        )

    run.baskets_processed = baskets_processed
    run.baskets_skipped = baskets_skipped
    run.items_seen = items_seen
    run.pairs_written = pairs_written
    run.source_row_count = source_row_count
    run.save(
        update_fields=[
            "baskets_processed",
            "baskets_skipped",
            "items_seen",
            "pairs_written",
            "source_row_count",
        ]
    )

    result.baskets_processed = baskets_processed
    result.baskets_skipped = baskets_skipped
    result.source_row_count = source_row_count
    result.items_seen = items_seen
    result.pairs_written = pairs_written

    if baskets_processed == 0:
        logger.info(
            "train_cooccurrence_listenbrainz_sql: no baskets to write (split=%s run=%s)",
            split,
            run.pk,
        )
        return result

    logger.info(
        "train_cooccurrence_listenbrainz_sql: wrote %d pairs from %d baskets (%d items) run=%s",
        result.pairs_written,
        result.baskets_processed,
        result.items_seen,
        run.pk,
    )
    return result


def baskets_from_behavioral_sources_with_count(
    resource_type: str = DEFAULT_RESOURCE_TYPE,
    split: str = "all",
    split_buckets: int = _SPLIT_BUCKET_COUNT,
    sources: Iterable[str] | None = None,
) -> tuple[list[list[UUID]], int]:
    normalized_sources = _normalized_sources(sources)
    session_to_jukes: dict[tuple[str, str | bytes], set[UUID]] = defaultdict(set)
    source_row_count = 0

    if BEHAVIOR_SOURCE_SEARCH_HISTORY in normalized_sources:
        source_row_count += _append_search_history_baskets(
            resource_type=resource_type,
            split=split,
            split_buckets=split_buckets,
            session_to_jukes=session_to_jukes,
        )

    if BEHAVIOR_SOURCE_LISTENBRAINZ in normalized_sources:
        source_row_count += _append_listenbrainz_session_track_baskets(
            split=split,
            split_buckets=split_buckets,
            session_to_jukes=session_to_jukes,
        )

    baskets: list[list[UUID]] = []
    for session_key in sorted(session_to_jukes.keys()):
        juke_ids = sorted(session_to_jukes[session_key], key=str)
        if len(juke_ids) >= MIN_BASKET_SIZE:
            baskets.append(juke_ids)

    return baskets, source_row_count


def compute_pmi_table(
    baskets: Iterable[list[UUID]]
) -> tuple[dict[tuple[UUID, UUID], tuple[int, float]], TrainingResult]:
    """
    Count pairs and compute PMI. Returns (pair_table, result_stats)
    where pair_table maps canonical (a,b) -> (co_count, pmi_score).

    Pure function: no DB writes. Makes the math independently testable.
    """
    item_count: Counter[UUID] = Counter()
    pair_count: Counter[tuple[UUID, UUID]] = Counter()
    n_baskets = 0
    skipped = 0

    for basket in baskets:
        unique = set(basket)
        if len(unique) < MIN_BASKET_SIZE:
            skipped += 1
            continue
        n_baskets += 1
        for item in unique:
            item_count[item] += 1
        for a, b in combinations(unique, 2):
            pair_count[_canonical_pair(a, b)] += 1

    table: dict[tuple[UUID, UUID], tuple[int, float]] = {}
    if n_baskets == 0:
        return table, TrainingResult(0, skipped, 0, 0, _baskets_to_hash([]), 0)

    for (a, b), co in pair_count.items():
        p_ab = co / n_baskets
        p_a = item_count[a] / n_baskets
        p_b = item_count[b] / n_baskets
        pmi = math.log2(p_ab / (p_a * p_b))
        table[(a, b)] = (co, pmi)

    result = TrainingResult(
        baskets_processed=n_baskets,
        baskets_skipped=skipped,
        items_seen=len(item_count),
        pairs_written=len(table),
        training_hash="",
        source_row_count=0,
    )
    return table, result


def train_cooccurrence(
    baskets: Iterable[list[UUID]] | None = None,
    split: str = "train",
    split_buckets: int = _SPLIT_BUCKET_COUNT,
    sources: Iterable[str] | None = None,
    resume_training_run_id: UUID | None = None,
    start_bucket: int = 0,
    resume: bool = False,
) -> TrainingResult:
    """
    Full pipeline: extract baskets (or use supplied ones), compute PMI,
    persist to mlcore_item_cooccurrence.

    Idempotent: re-running with the same baskets produces identical rows
    (update_conflicts overwrites co_count + pmi_score on collision).
    """
    normalized_sources = _normalized_sources(sources)

    if (
        baskets is None
        and normalized_sources == (BEHAVIOR_SOURCE_LISTENBRAINZ,)
    ):
        return _train_cooccurrence_listenbrainz_sql(
            split=split,
            split_buckets=split_buckets,
            resume_training_run_id=resume_training_run_id,
            start_bucket=start_bucket,
            resume=resume,
        )

    if resume_training_run_id is not None or start_bucket or resume:
        raise ValueError("Bucket resume options are only supported for listenbrainz-only SQL training")

    if baskets is None:
        baskets, source_row_count = baskets_from_behavioral_sources_with_count(
            split=split,
            split_buckets=split_buckets,
            sources=normalized_sources,
        )
    else:
        baskets = list(baskets)
        source_row_count = len(baskets)

    training_hash = _baskets_to_hash(list(baskets))
    table, result = compute_pmi_table(baskets)
    result.training_hash = training_hash
    result.source_row_count = source_row_count

    run = TrainingRun.objects.create(
        ranker_label="cooccurrence",
        training_hash=training_hash,
        baskets_processed=result.baskets_processed,
        baskets_skipped=result.baskets_skipped,
        items_seen=result.items_seen,
        pairs_written=result.pairs_written,
        source_row_count=source_row_count,
    )
    result.training_run_id = run.pk

    if not table:
        logger.info(
            "train_cooccurrence: no pairs to write (baskets=%d skipped=%d run=%s)",
            result.baskets_processed,
            result.baskets_skipped,
            run.pk,
        )
        return result

    rows = [
        ItemCoOccurrence(
            item_a_juke_id=a,
            item_b_juke_id=b,
            co_count=co,
            pmi_score=pmi,
            training_run=run,
        )
        for (a, b), (co, pmi) in table.items()
    ]

    for i in range(0, len(rows), WRITE_BATCH_SIZE):
        batch = rows[i:i + WRITE_BATCH_SIZE]
        ItemCoOccurrence.objects.bulk_create(
            batch,
            update_conflicts=True,
            unique_fields=["item_a_juke_id", "item_b_juke_id"],
            update_fields=["co_count", "pmi_score", "updated_at", "training_run"],
        )

    logger.info(
        "train_cooccurrence: wrote %d pairs from %d baskets (%d items, %d skipped) run=%s",
        result.pairs_written,
        result.baskets_processed,
        result.items_seen,
        result.baskets_skipped,
        run.pk,
    )
    return result

from __future__ import annotations

from dataclasses import dataclass

from django.db import connection, transaction

from mlcore.services.musicbrainz_bridge import BRIDGE_SOURCE_ID
from mlcore.models import SourceIngestionRun


ALGORITHM_VERSION = 'musicbrainz-isrc-alias-v1'


@dataclass(frozen=True)
class MusicBrainzISRCAliasBatchResult:
    processed_count: int
    last_isrc: str | None
    created_count: int
    existing_count: int
    ambiguous_count: int
    unresolved_count: int
    existing_alias_conflict_count: int


def latest_musicbrainz_isrc_source_version() -> str:
    source_version = (
        SourceIngestionRun.objects.filter(source=BRIDGE_SOURCE_ID, status='succeeded')
        .order_by('-completed_at', '-started_at')
        .values_list('source_version', flat=True)
        .first()
    )
    if not source_version:
        raise ValueError('No successful MusicBrainz identity bridge run is available.')
    return str(source_version)


def count_musicbrainz_isrcs(source_version: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            '''
            SELECT COUNT(DISTINCT isrc)
            FROM mlcore_musicbrainz_recording_isrc
            WHERE source_version = %s
            ''',
            [source_version],
        )
        return int(cursor.fetchone()[0])


def materialize_musicbrainz_isrc_alias_batch(
    *,
    source_version: str,
    last_isrc: str | None,
    batch_size: int,
) -> MusicBrainzISRCAliasBatchResult:
    if batch_size < 1:
        raise ValueError('batch_size must be greater than zero')

    with transaction.atomic(), connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('mlcore-canonical-alias-materialization'))")
        cursor.execute(
            '''
            WITH batch_isrcs AS MATERIALIZED (
                SELECT DISTINCT isrc
                FROM mlcore_musicbrainz_recording_isrc
                WHERE source_version = %s
                  AND (%s::text IS NULL OR isrc > %s::text)
                ORDER BY isrc
                LIMIT %s
            ), resolved AS MATERIALIZED (
                SELECT
                    batch.isrc,
                    COUNT(DISTINCT evidence.recording_mbid) AS mbid_count,
                    MIN(item.id::text)::uuid AS canonical_item_id
                FROM batch_isrcs batch
                JOIN mlcore_musicbrainz_recording_isrc evidence
                  ON evidence.isrc = batch.isrc
                 AND evidence.source_version = %s
                LEFT JOIN mlcore_canonical_item item
                  ON item.canonical_key = 'recording_mbid:' || evidence.recording_mbid::text
                GROUP BY batch.isrc
            ), candidates AS MATERIALIZED (
                SELECT isrc, canonical_item_id
                FROM resolved
                WHERE mbid_count = 1
                  AND canonical_item_id IS NOT NULL
            ), existing AS MATERIALIZED (
                SELECT
                    candidate.isrc,
                    candidate.canonical_item_id,
                    COALESCE(redirect.to_canonical_item_id, alias.canonical_item_id) AS existing_canonical_item_id
                FROM candidates candidate
                JOIN mlcore_canonical_item_alias alias
                  ON alias.source = 'isrc'
                 AND alias.resource_type = 'recording'
                 AND alias.source_id = candidate.isrc
                LEFT JOIN mlcore_canonical_item_redirect redirect
                  ON redirect.from_canonical_item_id = alias.canonical_item_id
                 AND redirect.status = 'active'
            ), inserted AS (
                INSERT INTO mlcore_canonical_item_alias (
                    id,
                    canonical_item_id,
                    source,
                    resource_type,
                    source_id,
                    confidence,
                    source_version,
                    status,
                    metadata,
                    created_at,
                    updated_at
                )
                SELECT
                    md5('isrc:recording:' || candidate.isrc)::uuid,
                    candidate.canonical_item_id,
                    'isrc',
                    'recording',
                    candidate.isrc,
                    1.0,
                    %s,
                    'active',
                    jsonb_build_object(
                        'match_source', 'musicbrainz',
                        'musicbrainz_source_version', %s
                    ),
                    NOW(),
                    NOW()
                FROM candidates candidate
                ON CONFLICT (source, resource_type, source_id) DO NOTHING
                RETURNING 1
            )
            SELECT
                (SELECT COUNT(*) FROM batch_isrcs),
                (SELECT MAX(isrc) FROM batch_isrcs),
                (SELECT COUNT(*) FROM inserted),
                (
                    SELECT COUNT(*)
                    FROM existing
                    WHERE existing_canonical_item_id = canonical_item_id
                ),
                (SELECT COUNT(*) FROM resolved WHERE mbid_count > 1),
                (
                    SELECT COUNT(*)
                    FROM resolved
                    WHERE mbid_count = 1
                      AND canonical_item_id IS NULL
                ),
                (
                    SELECT COUNT(*)
                    FROM existing
                    WHERE existing_canonical_item_id <> canonical_item_id
                )
            ''',
            [
                source_version,
                last_isrc,
                last_isrc,
                batch_size,
                source_version,
                source_version,
                source_version,
            ],
        )
        values = cursor.fetchone()

    return MusicBrainzISRCAliasBatchResult(
        processed_count=int(values[0] or 0),
        last_isrc=str(values[1]) if values[1] else None,
        created_count=int(values[2] or 0),
        existing_count=int(values[3] or 0),
        ambiguous_count=int(values[4] or 0),
        unresolved_count=int(values[5] or 0),
        existing_alias_conflict_count=int(values[6] or 0),
    )

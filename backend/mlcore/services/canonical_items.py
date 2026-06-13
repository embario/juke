from __future__ import annotations

import uuid
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import time
from typing import Iterable
from uuid import UUID

from django.db import connection, transaction

from catalog.models import Track, TrackExternalIdentifier
from mlcore.models import CanonicalItem, CanonicalItemAlias

CANONICAL_ITEM_NAMESPACE = UUID('9f291c3d-bb5c-4fd7-a1cd-730f4f9dc9b7')
ITEM_TYPE_RECORDING_MBID = 'recording_mbid'
ITEM_TYPE_SPOTIFY_TRACK = 'spotify_track'
ITEM_TYPE_RECORDING_MSID = 'recording_msid'
ITEM_TYPE_CATALOG_TRACK = 'catalog_track'

ALIAS_SOURCE_SPOTIFY = 'spotify'
ALIAS_SOURCE_MUSICBRAINZ = 'musicbrainz'
ALIAS_SOURCE_LISTENBRAINZ = 'listenbrainz'
ALIAS_RESOURCE_TRACK = 'track'
ALIAS_RESOURCE_RECORDING = 'recording'
ALIAS_STATUS_ACTIVE = 'active'
ALIAS_STATUS_CONFLICT = 'conflict'

@dataclass(frozen=True)
class CanonicalItemIdentity:
    item_type: str
    canonical_key: str
    item_id: UUID


@dataclass(frozen=True)
class CanonicalItemAliasIdentity:
    source: str
    resource_type: str
    source_id: str
    alias_id: UUID

    @property
    def key(self) -> tuple[str, str, str]:
        return self.source, self.resource_type, self.source_id


@dataclass(frozen=True)
class CanonicalAliasConflict:
    source: str
    resource_type: str
    source_id: str
    existing_canonical_item_id: UUID | None
    desired_canonical_item_id: UUID
    reason: str


@dataclass(frozen=True)
class AliasMaterializationResult:
    created_count: int = 0
    existing_count: int = 0
    conflict_count: int = 0
    conflicts: list[CanonicalAliasConflict] = field(default_factory=list)


@dataclass(frozen=True)
class CanonicalAliasSourceMapping:
    item_type: str
    canonical_key_prefix: str
    source: str
    resource_type: str


CANONICAL_ALIAS_SOURCE_MAPPINGS = (
    CanonicalAliasSourceMapping(
        item_type=ITEM_TYPE_RECORDING_MBID,
        canonical_key_prefix=f'{ITEM_TYPE_RECORDING_MBID}:',
        source=ALIAS_SOURCE_MUSICBRAINZ,
        resource_type=ALIAS_RESOURCE_RECORDING,
    ),
    CanonicalAliasSourceMapping(
        item_type=ITEM_TYPE_RECORDING_MSID,
        canonical_key_prefix=f'{ITEM_TYPE_RECORDING_MSID}:',
        source=ALIAS_SOURCE_LISTENBRAINZ,
        resource_type=ALIAS_RESOURCE_RECORDING,
    ),
    CanonicalAliasSourceMapping(
        item_type=ITEM_TYPE_SPOTIFY_TRACK,
        canonical_key_prefix=f'{ITEM_TYPE_SPOTIFY_TRACK}:',
        source=ALIAS_SOURCE_SPOTIFY,
        resource_type=ALIAS_RESOURCE_TRACK,
    ),
)


@dataclass
class AliasMaterializationProgress:
    status: str
    total_items: int
    processed_items: int = 0
    created_count: int = 0
    existing_count: int = 0
    conflict_count: int = 0
    batch_size: int = 0
    batches_processed: int = 0
    wall_started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    monotonic_started_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    source_version: str = ''
    phase: str = ''
    run_id: UUID | None = None
    algorithm_version: str = 'canonical-alias-v2'

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.monotonic_started_at)

    @property
    def tracks_per_second(self) -> float:
        elapsed = self.elapsed_seconds
        if elapsed <= 0:
            return 0.0
        return self.processed_items / elapsed

    @property
    def progress_fraction(self) -> float:
        if self.total_items <= 0:
            return 0.0
        return min(1.0, self.processed_items / self.total_items)

    @property
    def eta_seconds(self) -> float:
        rate = self.tracks_per_second
        if rate <= 0 or self.total_items <= 0 or self.status != 'running':
            return 0.0
        return max(0.0, (self.total_items - self.processed_items) / rate)


def write_alias_materialization_metrics(
    progress: AliasMaterializationProgress,
    *,
    metrics_path: str | Path | None,
) -> Path | None:
    if not metrics_path:
        return None

    path = Path(metrics_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + '.tmp')

    def _escape_label(value: str) -> str:
        return value.replace('\\', '\\\\').replace('"', '\\"')

    generated_at = datetime.now(tz=UTC).isoformat()
    labels = (
        f'status="{_escape_label(progress.status)}",'
        f'source_version="{_escape_label(progress.source_version)}",'
        f'phase="{_escape_label(progress.phase)}",'
        f'algorithm_version="{_escape_label(progress.algorithm_version)}",'
        f'run_id="{_escape_label(str(progress.run_id or ""))}"'
    )
    lines = [
        '# HELP mlcore_canonical_alias_materialization_active Whether canonical alias materialization is currently active.',
        '# TYPE mlcore_canonical_alias_materialization_active gauge',
        f'mlcore_canonical_alias_materialization_active{{{labels}}} {1 if progress.status == "running" else 0}',
        '# HELP mlcore_canonical_alias_materialization_info Metadata for the latest canonical alias materialization run.',
        '# TYPE mlcore_canonical_alias_materialization_info gauge',
        (
            'mlcore_canonical_alias_materialization_info{'
            f'{labels},'
            f'started_at="{_escape_label(progress.wall_started_at.isoformat())}",'
            f'generated_at="{_escape_label(generated_at)}"'
            '} 1'
        ),
        '# HELP mlcore_canonical_alias_materialization_items_total Total source items to scan.',
        '# TYPE mlcore_canonical_alias_materialization_items_total gauge',
        f'mlcore_canonical_alias_materialization_items_total{{{labels}}} {progress.total_items}',
        '# HELP mlcore_canonical_alias_materialization_items_processed Source items scanned so far.',
        '# TYPE mlcore_canonical_alias_materialization_items_processed gauge',
        f'mlcore_canonical_alias_materialization_items_processed{{{labels}}} {progress.processed_items}',
        '# HELP mlcore_canonical_alias_materialization_progress_fraction Fraction of source items scanned.',
        '# TYPE mlcore_canonical_alias_materialization_progress_fraction gauge',
        f'mlcore_canonical_alias_materialization_progress_fraction{{{labels}}} {progress.progress_fraction}',
        '# HELP mlcore_canonical_alias_materialization_elapsed_seconds Wall-clock seconds elapsed.',
        '# TYPE mlcore_canonical_alias_materialization_elapsed_seconds gauge',
        f'mlcore_canonical_alias_materialization_elapsed_seconds{{{labels}}} {progress.elapsed_seconds}',
        '# HELP mlcore_canonical_alias_materialization_eta_seconds Estimated seconds until completion.',
        '# TYPE mlcore_canonical_alias_materialization_eta_seconds gauge',
        f'mlcore_canonical_alias_materialization_eta_seconds{{{labels}}} {progress.eta_seconds}',
        '# HELP mlcore_canonical_alias_materialization_items_per_second Current source item scan throughput.',
        '# TYPE mlcore_canonical_alias_materialization_items_per_second gauge',
        f'mlcore_canonical_alias_materialization_items_per_second{{{labels}}} {progress.tracks_per_second}',
        '# HELP mlcore_canonical_alias_materialization_batches_processed Batches processed so far.',
        '# TYPE mlcore_canonical_alias_materialization_batches_processed gauge',
        f'mlcore_canonical_alias_materialization_batches_processed{{{labels}}} {progress.batches_processed}',
        '# HELP mlcore_canonical_alias_materialization_batch_size Configured track batch size.',
        '# TYPE mlcore_canonical_alias_materialization_batch_size gauge',
        f'mlcore_canonical_alias_materialization_batch_size{{{labels}}} {progress.batch_size}',
        '# HELP mlcore_canonical_alias_materialization_aliases_created Canonical alias rows created so far.',
        '# TYPE mlcore_canonical_alias_materialization_aliases_created gauge',
        f'mlcore_canonical_alias_materialization_aliases_created{{{labels}}} {progress.created_count}',
        '# HELP mlcore_canonical_alias_materialization_aliases_existing Canonical alias rows already present so far.',
        '# TYPE mlcore_canonical_alias_materialization_aliases_existing gauge',
        f'mlcore_canonical_alias_materialization_aliases_existing{{{labels}}} {progress.existing_count}',
        '# HELP mlcore_canonical_alias_materialization_alias_conflicts Canonical alias conflicts observed so far.',
        '# TYPE mlcore_canonical_alias_materialization_alias_conflicts gauge',
        f'mlcore_canonical_alias_materialization_alias_conflicts{{{labels}}} {progress.conflict_count}',
        '',
    ]
    temp_path.write_text('\n'.join(lines), encoding='utf-8')
    temp_path.replace(path)
    return path


def canonical_item_uuid(*, item_type: str, key_value: str) -> UUID:
    normalized = f'{item_type}:{str(key_value).strip()}'
    return uuid.uuid5(CANONICAL_ITEM_NAMESPACE, normalized)


def canonical_item_alias_uuid(*, source: str, resource_type: str, source_id: str) -> UUID:
    normalized = ':'.join([
        str(source).strip().lower(),
        str(resource_type).strip().lower(),
        str(source_id).strip(),
    ])
    digest = hashlib.md5(f'canonical-alias:{normalized}'.encode('utf-8'), usedforsecurity=False)
    return UUID(hex=digest.hexdigest())


def identity_from_parts(*, item_type: str, key_value: str) -> CanonicalItemIdentity:
    normalized_key = f'{item_type}:{str(key_value).strip()}'
    return CanonicalItemIdentity(
        item_type=item_type,
        canonical_key=normalized_key,
        item_id=canonical_item_uuid(item_type=item_type, key_value=key_value),
    )


def alias_identity_from_parts(*, source: str, resource_type: str, source_id: str) -> CanonicalItemAliasIdentity | None:
    normalized_source = str(source or '').strip().lower()
    normalized_resource_type = str(resource_type or '').strip().lower()
    normalized_source_id = str(source_id or '').strip()
    if not normalized_source or not normalized_resource_type or not normalized_source_id:
        return None
    return CanonicalItemAliasIdentity(
        source=normalized_source,
        resource_type=normalized_resource_type,
        source_id=normalized_source_id,
        alias_id=canonical_item_alias_uuid(
            source=normalized_source,
            resource_type=normalized_resource_type,
            source_id=normalized_source_id,
        ),
    )


def identity_from_track(track: Track) -> CanonicalItemIdentity:
    if track.mbid is not None:
        return identity_from_parts(item_type=ITEM_TYPE_RECORDING_MBID, key_value=str(track.mbid))

    spotify_id = str(track.spotify_id or '').strip()
    if spotify_id:
        return identity_from_parts(item_type=ITEM_TYPE_SPOTIFY_TRACK, key_value=spotify_id)

    return identity_from_parts(item_type=ITEM_TYPE_CATALOG_TRACK, key_value=str(track.juke_id))


def identity_from_listenbrainz_candidates(
    *,
    recording_mbid: str = '',
    spotify_id: str = '',
    recording_msid: str = '',
) -> CanonicalItemIdentity | None:
    normalized_mbid = str(recording_mbid or '').strip()
    if normalized_mbid:
        return identity_from_parts(item_type=ITEM_TYPE_RECORDING_MBID, key_value=normalized_mbid)

    normalized_msid = str(recording_msid or '').strip()
    if normalized_msid:
        return identity_from_parts(item_type=ITEM_TYPE_RECORDING_MSID, key_value=normalized_msid)

    normalized_spotify = str(spotify_id or '').strip()
    if normalized_spotify:
        return identity_from_parts(item_type=ITEM_TYPE_SPOTIFY_TRACK, key_value=normalized_spotify)

    return None


def bulk_ensure_canonical_items(
    identity_assignments: Iterable[tuple[CanonicalItemIdentity, UUID | None]],
) -> dict[str, CanonicalItem]:
    assignments: dict[str, tuple[CanonicalItemIdentity, UUID | None]] = {}
    for identity, track_id in identity_assignments:
        if identity.canonical_key in assignments:
            existing_identity, existing_track_id = assignments[identity.canonical_key]
            assignments[identity.canonical_key] = (
                existing_identity,
                existing_track_id or track_id,
            )
            continue
        assignments[identity.canonical_key] = (identity, track_id)

    if not assignments:
        return {}

    existing_items = {
        item.canonical_key: item
        for item in CanonicalItem.objects.filter(canonical_key__in=list(assignments.keys()))
    }

    rows_to_create: list[CanonicalItem] = []
    rows_to_update: list[CanonicalItem] = []
    for canonical_key, (identity, track_id) in assignments.items():
        existing = existing_items.get(canonical_key)
        if existing is None:
            rows_to_create.append(
                CanonicalItem(
                    id=identity.item_id,
                    item_type=identity.item_type,
                    canonical_key=identity.canonical_key,
                    track_id=track_id,
                )
            )
            continue

        if existing.track_id is None and track_id is not None:
            existing.track_id = track_id
            rows_to_update.append(existing)

    if rows_to_create:
        CanonicalItem.objects.bulk_create(rows_to_create, ignore_conflicts=True)
        existing_items = {
            item.canonical_key: item
            for item in CanonicalItem.objects.filter(canonical_key__in=list(assignments.keys()))
        }
    if rows_to_update:
        CanonicalItem.objects.bulk_update(rows_to_update, ['track'])

    return existing_items


def bulk_ensure_canonical_items_for_tracks(tracks: Iterable[Track]) -> dict[UUID, CanonicalItem]:
    materialized_tracks = list(tracks)
    track_identities = [
        (track, identity_from_track(track))
        for track in materialized_tracks
    ]
    ensured = bulk_ensure_canonical_items(
        (identity, track.juke_id)
        for track, identity in track_identities
    )
    return {
        track.juke_id: ensured[identity.canonical_key]
        for track, identity in track_identities
    }


def _alias_assignments_for_track(track: Track, canonical_item: CanonicalItem) -> list[tuple[CanonicalItemAliasIdentity, CanonicalItem]]:
    assignments: list[tuple[CanonicalItemAliasIdentity, CanonicalItem]] = []

    spotify_alias = alias_identity_from_parts(
        source=ALIAS_SOURCE_SPOTIFY,
        resource_type=ALIAS_RESOURCE_TRACK,
        source_id=track.spotify_id,
    )
    if spotify_alias is not None:
        assignments.append((spotify_alias, canonical_item))

    mbid_alias = alias_identity_from_parts(
        source=ALIAS_SOURCE_MUSICBRAINZ,
        resource_type=ALIAS_RESOURCE_RECORDING,
        source_id=str(track.mbid or ''),
    )
    if mbid_alias is not None:
        assignments.append((mbid_alias, canonical_item))

    return assignments


def merge_alias_materialization_results(
    current: AliasMaterializationResult,
    next_result: AliasMaterializationResult,
) -> AliasMaterializationResult:
    return AliasMaterializationResult(
        created_count=current.created_count + next_result.created_count,
        existing_count=current.existing_count + next_result.existing_count,
        conflict_count=current.conflict_count + next_result.conflict_count,
        conflicts=[*current.conflicts, *next_result.conflicts],
    )


def _iter_track_batches(tracks: Iterable[Track], *, batch_size: int) -> Iterable[list[Track]]:
    batch: list[Track] = []
    for track in tracks:
        batch.append(track)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _uuid_sql_from_alias_parts() -> str:
    digest = "md5('canonical-alias:' || source || ':' || resource_type || ':' || source_id)"
    return (
        "concat("
        f"substr({digest}, 1, 8), '-',"
        f"substr({digest}, 9, 4), '-',"
        f"substr({digest}, 13, 4), '-',"
        f"substr({digest}, 17, 4), '-',"
        f"substr({digest}, 21, 12)"
        ")::uuid"
    )


def _acquire_alias_materialization_lock() -> None:
    if connection.vendor != 'postgresql':
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('mlcore-canonical-alias-materialization'))")


def count_canonical_alias_source_items(mappings: Iterable[CanonicalAliasSourceMapping]) -> int:
    item_types = [mapping.item_type for mapping in mappings]
    if not item_types:
        return 0
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM mlcore_canonical_item
            WHERE item_type = ANY(%s)
            """,
            [item_types],
        )
        return int(cursor.fetchone()[0])


def _materialize_canonical_item_alias_batch(
    mapping: CanonicalAliasSourceMapping,
    *,
    last_id: UUID | None,
    batch_size: int,
    source_version: str,
) -> tuple[AliasMaterializationResult, UUID | None, int]:
    alias_uuid_sql = _uuid_sql_from_alias_parts()
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH candidates AS MATERIALIZED (
                SELECT
                    id AS canonical_item_id,
                    %s::text AS source,
                    %s::text AS resource_type,
                    substring(canonical_key from %s)::text AS source_id
                FROM mlcore_canonical_item
                WHERE item_type = %s
                  AND (%s::uuid IS NULL OR id > %s::uuid)
                ORDER BY id
                LIMIT %s
            ),
            existing AS MATERIALIZED (
                SELECT
                    c.canonical_item_id,
                    a.canonical_item_id AS existing_canonical_item_id
                FROM candidates c
                JOIN mlcore_canonical_item_alias a
                  ON a.source = c.source
                 AND a.resource_type = c.resource_type
                 AND a.source_id = c.source_id
            ),
            inserted AS (
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
                    {alias_uuid_sql},
                    canonical_item_id,
                    source,
                    resource_type,
                    source_id,
                    1.0,
                    %s,
                    %s,
                    '{{}}'::jsonb,
                    now(),
                    now()
                FROM candidates
                ON CONFLICT (source, resource_type, source_id) DO NOTHING
                RETURNING 1
            )
            SELECT
                count(*)::bigint AS processed_count,
                (
                    SELECT canonical_item_id
                    FROM candidates
                    ORDER BY canonical_item_id DESC
                    LIMIT 1
                )::uuid AS last_id,
                (SELECT count(*)::bigint FROM inserted) AS created_count,
                (
                    SELECT count(*)::bigint
                    FROM existing
                    WHERE existing_canonical_item_id = canonical_item_id
                ) AS existing_count,
                (
                    SELECT count(*)::bigint
                    FROM existing
                    WHERE existing_canonical_item_id <> canonical_item_id
                ) AS conflict_count
            FROM candidates
            """,
            [
                mapping.source,
                mapping.resource_type,
                len(mapping.canonical_key_prefix) + 1,
                mapping.item_type,
                last_id,
                last_id,
                batch_size,
                source_version,
                ALIAS_STATUS_ACTIVE,
            ],
        )
        processed_count, next_last_id, created_count, existing_count, conflict_count = cursor.fetchone()

    return (
        AliasMaterializationResult(
            created_count=int(created_count or 0),
            existing_count=int(existing_count or 0),
            conflict_count=int(conflict_count or 0),
        ),
        next_last_id,
        int(processed_count or 0),
    )


def materialize_canonical_item_self_aliases(
    *,
    source_version: str = '',
    batch_size: int = 100_000,
    progress_callback: Callable[[AliasMaterializationProgress], None] | None = None,
    mappings: Iterable[CanonicalAliasSourceMapping] = CANONICAL_ALIAS_SOURCE_MAPPINGS,
    start_after_by_item_type: dict[str, UUID | str] | None = None,
    checkpoint_callback: Callable[
        [CanonicalAliasSourceMapping, UUID, AliasMaterializationProgress],
        None,
    ] | None = None,
) -> AliasMaterializationResult:
    """
    Materialize aliases directly from MLCore canonical keys.

    This is the Neptune-scale path: it turns canonical keys like
    ``recording_msid:<id>`` into external lookup aliases without copying the
    100M+ row corpus into Python.
    """
    if batch_size < 1:
        raise ValueError('batch_size must be greater than 0')

    materialized_mappings = list(mappings)
    checkpoints = start_after_by_item_type or {}
    result = AliasMaterializationResult()
    progress = AliasMaterializationProgress(
        status='running',
        total_items=count_canonical_alias_source_items(materialized_mappings),
        batch_size=batch_size,
        source_version=source_version,
    )
    if progress_callback is not None:
        progress_callback(progress)

    for mapping in materialized_mappings:
        checkpoint = checkpoints.get(mapping.item_type)
        last_id = UUID(str(checkpoint)) if checkpoint else None
        progress.phase = f'canonical:{mapping.item_type}'
        while True:
            with transaction.atomic():
                _acquire_alias_materialization_lock()
                batch_result, next_last_id, processed_count = _materialize_canonical_item_alias_batch(
                    mapping,
                    last_id=last_id,
                    batch_size=batch_size,
                    source_version=source_version,
                )
                if processed_count:
                    last_id = next_last_id
                    result = merge_alias_materialization_results(result, batch_result)
                    progress.processed_items += processed_count
                    progress.created_count = result.created_count
                    progress.existing_count = result.existing_count
                    progress.conflict_count = result.conflict_count
                    progress.batches_processed += 1
                    progress.updated_at = time.monotonic()
                    if checkpoint_callback is not None and last_id is not None:
                        checkpoint_callback(mapping, last_id, progress)
            if processed_count == 0:
                break
            if progress_callback is not None:
                progress_callback(progress)

    progress.status = 'succeeded'
    progress.updated_at = time.monotonic()
    if progress_callback is not None:
        progress_callback(progress)
    return result


@transaction.atomic
def _materialize_track_alias_batch(
    track_list: list[Track],
    *,
    source_version: str = '',
) -> AliasMaterializationResult:
    """
    Build external-ID aliases for one batch of shared MLCore serving tracks.

    Existing aliases are never reassigned here. If incoming catalog metadata
    disagrees with an active mapping, the conflict is reported for operators to
    inspect and the current read path remains stable.
    """
    if not track_list:
        return AliasMaterializationResult()

    _acquire_alias_materialization_lock()

    canonical_items_by_track_id = bulk_ensure_canonical_items_for_tracks(track_list)

    desired: dict[tuple[str, str, str], tuple[CanonicalItemAliasIdentity, CanonicalItem]] = {}
    conflicts: list[CanonicalAliasConflict] = []

    def add_assignment(alias: CanonicalItemAliasIdentity | None, canonical_item: CanonicalItem):
        if alias is None:
            return
        existing = desired.get(alias.key)
        if existing is not None and existing[1].pk != canonical_item.pk:
            conflicts.append(
                CanonicalAliasConflict(
                    source=alias.source,
                    resource_type=alias.resource_type,
                    source_id=alias.source_id,
                    existing_canonical_item_id=existing[1].pk,
                    desired_canonical_item_id=canonical_item.pk,
                    reason='incoming_duplicate',
                )
            )
            return
        desired[alias.key] = (alias, canonical_item)

    prefetched_external_ids = {}
    track_ids = [track.juke_id for track in track_list]
    for external_id in TrackExternalIdentifier.objects.filter(track_id__in=track_ids).order_by('source', 'external_id'):
        prefetched_external_ids.setdefault(external_id.track_id, []).append(external_id)

    for track in track_list:
        canonical_item = canonical_items_by_track_id[track.juke_id]
        for alias, item in _alias_assignments_for_track(track, canonical_item):
            add_assignment(alias, item)
        for external_id in prefetched_external_ids.get(track.juke_id, []):
            add_assignment(
                alias_identity_from_parts(
                    source=external_id.source,
                    resource_type=ALIAS_RESOURCE_TRACK,
                    source_id=external_id.external_id,
                ),
                canonical_item,
            )

    if not desired:
        return AliasMaterializationResult(conflict_count=len(conflicts), conflicts=conflicts)

    source_values = sorted({key[0] for key in desired})
    resource_type_values = sorted({key[1] for key in desired})
    source_id_values = sorted({key[2] for key in desired})
    existing_aliases = {
        (alias.source, alias.resource_type, alias.source_id): alias
        for alias in CanonicalItemAlias.objects.filter(
            source__in=source_values,
            resource_type__in=resource_type_values,
            source_id__in=source_id_values,
        )
    }

    rows_to_create = []
    existing_count = 0
    for key, (alias, canonical_item) in desired.items():
        existing_alias = existing_aliases.get(key)
        if existing_alias is None:
            rows_to_create.append(
                CanonicalItemAlias(
                    id=alias.alias_id,
                    canonical_item=canonical_item,
                    source=alias.source,
                    resource_type=alias.resource_type,
                    source_id=alias.source_id,
                    confidence=1.0,
                    source_version=source_version,
                    status=ALIAS_STATUS_ACTIVE,
                )
            )
            continue

        existing_count += 1
        if existing_alias.canonical_item_id != canonical_item.pk:
            conflicts.append(
                CanonicalAliasConflict(
                    source=alias.source,
                    resource_type=alias.resource_type,
                    source_id=alias.source_id,
                    existing_canonical_item_id=existing_alias.canonical_item_id,
                    desired_canonical_item_id=canonical_item.pk,
                    reason='existing_mapping',
                )
            )

    created_count = 0
    if rows_to_create:
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH incoming AS (
                        SELECT *
                        FROM unnest(
                            %s::uuid[], %s::uuid[], %s::text[], %s::text[], %s::text[]
                        ) AS values(id, canonical_item_id, source, resource_type, source_id)
                    )
                    INSERT INTO mlcore_canonical_item_alias (
                        id, canonical_item_id, source, resource_type, source_id,
                        confidence, source_version, status, metadata, created_at, updated_at
                    )
                    SELECT
                        id, canonical_item_id, source, resource_type, source_id,
                        1.0, %s, %s, '{}'::jsonb, now(), now()
                    FROM incoming
                    ON CONFLICT (source, resource_type, source_id) DO NOTHING
                    RETURNING id
                    """,
                    [
                        [row.id for row in rows_to_create],
                        [row.canonical_item_id for row in rows_to_create],
                        [row.source for row in rows_to_create],
                        [row.resource_type for row in rows_to_create],
                        [row.source_id for row in rows_to_create],
                        source_version,
                        ALIAS_STATUS_ACTIVE,
                    ],
                )
                created_count = len(cursor.fetchall())
        else:  # pragma: no cover - production and CI use PostgreSQL
            CanonicalItemAlias.objects.bulk_create(rows_to_create, ignore_conflicts=True)
            created_count = len(rows_to_create)

    return AliasMaterializationResult(
        created_count=created_count,
        existing_count=existing_count,
        conflict_count=len(conflicts),
        conflicts=conflicts,
    )


def materialize_track_aliases(
    tracks: Iterable[Track] | None = None,
    *,
    source_version: str = '',
    batch_size: int = 10_000,
    progress_callback: Callable[[AliasMaterializationProgress], None] | None = None,
    start_after_track_id: UUID | str | None = None,
    checkpoint_callback: Callable[[UUID, AliasMaterializationProgress], None] | None = None,
) -> AliasMaterializationResult:
    """
    Build external-ID aliases for shared MLCore serving.

    The default path streams tracks in bounded batches so this can run against
    the shared Neptune corpus without loading the full catalog into Python
    memory or generating one huge alias lookup query.
    """
    if batch_size < 1:
        raise ValueError('batch_size must be greater than 0')

    if tracks is None:
        queryset = Track.objects.order_by('juke_id')
        if start_after_track_id:
            queryset = queryset.filter(juke_id__gt=start_after_track_id)
        total_tracks = queryset.count()
        track_iterable = queryset.iterator(chunk_size=batch_size)
    else:
        total_tracks = len(tracks) if hasattr(tracks, '__len__') else 0
        track_iterable = iter(tracks)

    result = AliasMaterializationResult()
    progress = AliasMaterializationProgress(
        status='running',
        total_items=total_tracks,
        batch_size=batch_size,
        source_version=source_version,
        phase='catalog_tracks',
    )
    if progress_callback is not None:
        progress_callback(progress)

    for track_batch in _iter_track_batches(track_iterable, batch_size=batch_size):
        with transaction.atomic():
            batch_result = _materialize_track_alias_batch(track_batch, source_version=source_version)
            result = merge_alias_materialization_results(result, batch_result)
            progress.processed_items += len(track_batch)
            progress.created_count = result.created_count
            progress.existing_count = result.existing_count
            progress.conflict_count = result.conflict_count
            progress.batches_processed += 1
            progress.updated_at = time.monotonic()
            if checkpoint_callback is not None:
                checkpoint_callback(track_batch[-1].juke_id, progress)
        if progress_callback is not None:
            progress_callback(progress)

    progress.status = 'succeeded'
    progress.updated_at = time.monotonic()
    if progress_callback is not None:
        progress_callback(progress)
    return result

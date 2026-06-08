from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Iterable
from uuid import UUID

from django.db import transaction

from catalog.models import Track, TrackExternalIdentifier
from mlcore.models import CanonicalItem, CanonicalItemAlias

CANONICAL_ITEM_NAMESPACE = UUID('9f291c3d-bb5c-4fd7-a1cd-730f4f9dc9b7')
CANONICAL_ITEM_ALIAS_NAMESPACE = UUID('d6b68b7d-0c2e-4d47-ae60-2cd035b71e50')
ITEM_TYPE_RECORDING_MBID = 'recording_mbid'
ITEM_TYPE_SPOTIFY_TRACK = 'spotify_track'
ITEM_TYPE_RECORDING_MSID = 'recording_msid'
ITEM_TYPE_CATALOG_TRACK = 'catalog_track'

ALIAS_SOURCE_SPOTIFY = 'spotify'
ALIAS_SOURCE_MUSICBRAINZ = 'musicbrainz'
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


def canonical_item_uuid(*, item_type: str, key_value: str) -> UUID:
    normalized = f'{item_type}:{str(key_value).strip()}'
    return uuid.uuid5(CANONICAL_ITEM_NAMESPACE, normalized)


def canonical_item_alias_uuid(*, source: str, resource_type: str, source_id: str) -> UUID:
    normalized = ':'.join([
        str(source).strip().lower(),
        str(resource_type).strip().lower(),
        str(source_id).strip(),
    ])
    return uuid.uuid5(CANONICAL_ITEM_ALIAS_NAMESPACE, normalized)


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


def materialize_track_aliases(
    tracks: Iterable[Track] | None = None,
    *,
    source_version: str = '',
) -> AliasMaterializationResult:
    """
    Build external-ID aliases for shared MLCore serving.

    Existing aliases are never reassigned here. If incoming catalog metadata
    disagrees with an active mapping, the conflict is reported for operators to
    inspect and the current read path remains stable.
    """
    if tracks is None:
        track_list = list(Track.objects.all().prefetch_related('external_ids'))
    else:
        track_list = list(tracks)

    if not track_list:
        return AliasMaterializationResult()

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

    if rows_to_create:
        with transaction.atomic():
            CanonicalItemAlias.objects.bulk_create(rows_to_create, ignore_conflicts=True)

    return AliasMaterializationResult(
        created_count=len(rows_to_create),
        existing_count=existing_count,
        conflict_count=len(conflicts),
        conflicts=conflicts,
    )

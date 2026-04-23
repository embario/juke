from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from catalog.models import Track
from mlcore.models import CanonicalItem

CANONICAL_ITEM_NAMESPACE = UUID('9f291c3d-bb5c-4fd7-a1cd-730f4f9dc9b7')
ITEM_TYPE_RECORDING_MBID = 'recording_mbid'
ITEM_TYPE_SPOTIFY_TRACK = 'spotify_track'
ITEM_TYPE_RECORDING_MSID = 'recording_msid'
ITEM_TYPE_CATALOG_TRACK = 'catalog_track'


@dataclass(frozen=True)
class CanonicalItemIdentity:
    item_type: str
    canonical_key: str
    item_id: UUID


def canonical_item_uuid(*, item_type: str, key_value: str) -> UUID:
    normalized = f'{item_type}:{str(key_value).strip()}'
    return uuid.uuid5(CANONICAL_ITEM_NAMESPACE, normalized)


def identity_from_parts(*, item_type: str, key_value: str) -> CanonicalItemIdentity:
    normalized_key = f'{item_type}:{str(key_value).strip()}'
    return CanonicalItemIdentity(
        item_type=item_type,
        canonical_key=normalized_key,
        item_id=canonical_item_uuid(item_type=item_type, key_value=key_value),
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

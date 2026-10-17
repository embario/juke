"""Priority boosts for hydration items that Juke users themselves reference (round 3, S2).

Order of the queue, lowest ``priority`` first:

* library (saved to the library, or reacted to): -29..-20, more distinct users earlier;
* playback (played, completed, recognized, a station seed, a clicked search result): -19..-10;
* everything else: the corpus listen score from ``provider_hydration`` (1..99), unscored 100.

Vibe memories are end-to-end encrypted (``VibeEncryptedRecord.ciphertext``), so the server cannot see
which songs a memory holds and they are not a boost source. ``MusicProfile.favorite_tracks`` holds
free-text names, not provider ids, so it is not used either.

A referenced Spotify track reaches its queued canonical item three ways: the catalog ``Track`` linked
to a ``CanonicalItem`` (FK), the ``recording_mbid:<Track.mbid>`` canonical key, and the ISRC kept in
``Track.spotify_data['external_ids']`` matched to the queue's own ISRC identifier. On the dev data
inspected read-only (2026-10-16) none of these resolve yet; see the PR for the follow-up.
"""
from collections import defaultdict

from django.db.models import Count, Q

from catalog.models import SearchHistoryResource, Track, TrackExternalIdentifier
from mlcore.models import CanonicalItem, ProviderHydrationItem
from mlcore.services.provider_hydration import normalize_isrc
from radio.models import ListeningEvent, Station, TrackReaction

LIBRARY_PRIORITY = -20
PLAYBACK_PRIORITY = -10
MAX_USER_STEPS = 9
LIBRARY_EVENTS = ('save',)
PLAYBACK_EVENTS = ('play', 'complete', 'recognized')
RESOLVE_CHUNK = 500


def boost_priority(base, users):
    """``base`` minus one step per extra distinct user (capped), so wider interest claims earlier."""
    return base - min(MAX_USER_STEPS, max(0, users - 1))


def collect_referenced_spotify_tracks():
    """Return ``{spotify_track_id: priority}`` for every track users have referenced.

    The user count per source is a distinct-user count; across sources the largest one is used (a lower
    bound of the union, which is all the priority steps need).
    """
    counts = {'library': defaultdict(int), 'playback': defaultdict(int)}

    def note(tier, spotify_id, users):
        if spotify_id:
            counts[tier][spotify_id] = max(counts[tier][spotify_id], users)

    events = ListeningEvent.objects.order_by().values('spotify_track_id')
    for row in events.filter(event__in=LIBRARY_EVENTS).annotate(n=Count('user_id', distinct=True)):
        note('library', row['spotify_track_id'], row['n'])
    reactions = TrackReaction.objects.exclude(reactions=[]).order_by().values('spotify_track_id')
    for row in reactions.annotate(n=Count('user_id', distinct=True)):
        note('library', row['spotify_track_id'], row['n'])

    for row in events.filter(event__in=PLAYBACK_EVENTS).annotate(n=Count('user_id', distinct=True)):
        note('playback', row['spotify_track_id'], row['n'])
    seed_users = defaultdict(set)
    for user_id, seeds in Station.objects.exclude(seeds=[]).values_list('user_id', 'seeds').iterator():
        for seed in seeds or []:
            if isinstance(seed, dict) and seed.get('kind') == 'track' and seed.get('spotifyId'):
                seed_users[seed['spotifyId']].add(user_id)
    for spotify_id, users in seed_users.items():
        note('playback', spotify_id, len(users))
    clicks = {
        row['resource_id']: row['n']
        for row in SearchHistoryResource.objects.filter(resource_type='track').order_by().values('resource_id')
        .annotate(n=Count('search_history__user_id', distinct=True))
    }
    for pk_chunk in _chunks(list(clicks), RESOLVE_CHUNK):
        for pk, spotify_id in Track.objects.filter(pk__in=pk_chunk, spotify_id__isnull=False).values_list(
            'pk', 'spotify_id',
        ):
            note('playback', spotify_id, clicks[pk])

    result = {}
    for tier, base in (('playback', PLAYBACK_PRIORITY), ('library', LIBRARY_PRIORITY)):
        for spotify_id, users in counts[tier].items():
            result[spotify_id] = boost_priority(base, users)  # library is written last, so it wins
    return result


def referenced_canonical_priorities(spotify_priorities=None):
    """Map the referenced Spotify tracks onto canonical items; the lowest priority wins."""
    spotify_priorities = collect_referenced_spotify_tracks() if spotify_priorities is None else spotify_priorities
    result = {}
    for ids in _chunks(list(spotify_priorities), RESOLVE_CHUNK):
        tracks = {}
        isrcs = {}
        for juke_id, mbid, spotify_id, data in Track.objects.filter(spotify_id__in=ids).values_list(
            'juke_id', 'mbid', 'spotify_id', 'spotify_data',
        ):
            tracks[juke_id] = (mbid, spotify_id)
            isrc = normalize_isrc(((data or {}).get('external_ids') or {}).get('isrc'))
            if isrc:
                isrcs[isrc] = spotify_id
        for canonical_id, identifier in ProviderHydrationItem.objects.filter(
            provider='spotify', identifier_type='isrc', identifier__in=list(isrcs),
        ).values_list('canonical_item_id', 'identifier'):
            priority = spotify_priorities[isrcs[identifier]]
            result[canonical_id] = min(priority, result.get(canonical_id, priority))
        for juke_id, spotify_id in TrackExternalIdentifier.objects.filter(
            source='spotify', external_id__in=ids,
        ).values_list('track_id', 'external_id'):
            tracks.setdefault(juke_id, (None, spotify_id))
        if not tracks:
            continue
        keys = {f'recording_mbid:{mbid}': spotify_id for mbid, spotify_id in tracks.values() if mbid}
        query = Q(track_id__in=list(tracks)) | Q(canonical_key__in=list(keys))
        for canonical_id, track_id, canonical_key in CanonicalItem.objects.filter(query).values_list(
            'id', 'track_id', 'canonical_key',
        ):
            spotify_id = keys.get(canonical_key) or tracks[track_id][1]
            priority = spotify_priorities[spotify_id]
            result[canonical_id] = min(priority, result.get(canonical_id, priority))
    return result


def apply_referenced_boosts(canonical_priorities):
    """Write the boosts onto pending/retry hydration rows. Bounded: one UPDATE per priority per chunk."""
    by_priority = defaultdict(list)
    for canonical_id, priority in canonical_priorities.items():
        by_priority[priority].append(canonical_id)
    updated = 0
    for priority, canonical_ids in by_priority.items():
        for chunk in _chunks(canonical_ids, RESOLVE_CHUNK):
            updated += (
                ProviderHydrationItem.objects.filter(
                    provider='spotify', canonical_item_id__in=chunk, status__in=['pending', 'retry'],
                )
                .exclude(priority=priority)
                .update(priority=priority)
            )
    return updated


def _chunks(values, size):
    for start in range(0, len(values), size):
        yield values[start:start + size]

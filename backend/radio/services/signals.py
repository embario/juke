"""Listening history, learned seeds, exclusions and session boundaries for radio."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, Iterable, List, Optional

from django.db.models import Q

from radio.models import Exclusion, ListeningEvent, Station, TrackReaction

RECENT_HISTORY_LIMIT = 50
SESSION_GAP = timedelta(minutes=30)
POSITIVE_EVENTS = ('complete', 'save', 'recognized')
LEARNED_SEED_LIMIT = 15


def recent_track_ids(user, limit: int = RECENT_HISTORY_LIMIT) -> List[str]:
    """The user's last ``limit`` distinct tracks across every event type (plays, queues, skips …)."""
    seen: Dict[str, None] = {}
    rows = ListeningEvent.objects.filter(user=user).order_by('-created_at').values_list('spotify_track_id', flat=True)
    # Over-fetch a bounded window so repeated events for one track don't shrink the history.
    for track_id in rows[:limit * 4]:
        if track_id and track_id not in seen:
            seen[track_id] = None
            if len(seen) >= limit:
                break
    return list(seen)


def learned_track_ids(user, station: Optional[Station] = None, limit: int = LEARNED_SEED_LIMIT) -> List[str]:
    """Recent positive signals (completed plays, saves, recognitions, reacted tracks), newest first.

    ``station`` narrows the signals to one station (custom stations that keep learning);
    the personal station learns from everything.
    """
    events = ListeningEvent.objects.filter(user=user, event__in=POSITIVE_EVENTS)
    reactions = TrackReaction.objects.filter(user=user).exclude(reactions=[])
    negatives = ListeningEvent.objects.filter(user=user, event__in=('less', 'never_artist', 'not_on_station'))
    if station is not None:
        events = events.filter(station=station)
        reactions = reactions.filter(station=station)
    blocked = set(negatives.order_by('-created_at').values_list('spotify_track_id', flat=True)[:200])
    timeline = [(row.created_at, row.spotify_track_id) for row in events.order_by('-created_at')[:limit * 3]]
    timeline += [(row.updated_at, row.spotify_track_id) for row in reactions.order_by('-updated_at')[:limit * 2]]
    timeline.sort(key=lambda item: item[0], reverse=True)
    ordered: Dict[str, None] = {}
    for _, track_id in timeline:
        if track_id and track_id not in blocked:
            ordered.setdefault(track_id, None)
    return list(ordered)[:limit]


def memory_song_ids(user, limit: int = 10) -> List[str]:
    from vibe.memory_services import memory_recommendation_context

    ids: Dict[str, None] = {}
    for signal in memory_recommendation_context(user):
        for song in (signal or {}).get('songs') or []:
            if (song.get('provider') or '').lower() == 'spotify' and song.get('providerTrackID'):
                ids.setdefault(song['providerTrackID'], None)
    return list(ids)[:limit]


def memory_tags(user, limit: int = 5) -> List[str]:
    from vibe.memory_services import memory_recommendation_context

    counts: Dict[str, int] = {}
    for signal in memory_recommendation_context(user):
        for tag in (signal or {}).get('tags') or []:
            counts[tag] = counts.get(tag, 0) + 1
    return [tag for tag, _ in sorted(counts.items(), key=lambda item: -item[1])][:limit]


def applicable_exclusions(user, station: Optional[Station]):
    query = Q(station__isnull=True)
    if station is not None:
        query |= Q(station=station)
    return Exclusion.objects.filter(user=user).filter(query)


@dataclass
class ExclusionFilter:
    track_ids: set = field(default_factory=set)
    artist_ids: set = field(default_factory=set)
    artist_names: set = field(default_factory=set)
    phrases: List[str] = field(default_factory=list)

    @classmethod
    def build(cls, exclusions: Iterable[Exclusion], recent_ids: Iterable[str] = ()):
        flt = cls(track_ids=set(recent_ids))
        for exclusion in exclusions:
            value = (exclusion.value or '').strip()
            if not value:
                continue
            if exclusion.kind == 'track':
                flt.track_ids.add(value)
            elif exclusion.kind == 'artist':
                flt.artist_ids.add(value)
                flt.artist_names.add(value.casefold())
                if exclusion.label:
                    flt.artist_names.add(exclusion.label.strip().casefold())
            else:
                # genre/text: best-effort phrase match against track metadata (Spotify no longer
                # exposes reliable per-track genres to new apps).
                flt.phrases.append(value.casefold())
        return flt

    def blocks_id(self, track_id: str) -> bool:
        return track_id in self.track_ids

    def blocks_track(self, track: Dict) -> bool:
        if not track or self.blocks_id(track.get('spotifyId', '')):
            return True
        if track.get('artistId') and track['artistId'] in self.artist_ids:
            return True
        artist_names = {name.strip().casefold() for name in (track.get('artist') or '').split(',') if name.strip()}
        if artist_names & self.artist_names:
            return True
        if self.phrases:
            haystack = ' '.join(str(track.get(key) or '') for key in ('title', 'artist', 'album')).casefold()
            return any(phrase in haystack for phrase in self.phrases)
        return False


def current_session_events(user) -> List[ListeningEvent]:
    """Events since the last ≥30 minute gap, oldest first."""
    session: List[ListeningEvent] = []
    previous = None
    for event in ListeningEvent.objects.filter(user=user).order_by('-created_at')[:2000]:
        if previous is not None and previous.created_at - event.created_at >= SESSION_GAP:
            break
        session.append(event)
        previous = event
    session.reverse()
    return session

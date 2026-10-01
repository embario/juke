"""Radio recommendation pipeline.

Seeds → MLCore co-occurrence (→ Spotify aliases) → MLCore metadata → seed artists' top
tracks → Spotify search on feelings/keywords → the seeds themselves. Every source is
filtered by exclusions and recent history, then hydrated into ``Track`` payloads.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from django.conf import settings

from mlcore.models import CanonicalItemAlias
from radio.models import Station
from radio.services import signals, spotify

logger = logging.getLogger(__name__)

MAX_IDENTITY_ITEMS = 100
MAX_SEEDS = 25
# The co-occurrence query cost grows sharply with seed count (measured on neptune: 1–2 seeds
# ≈0.1–2 s, 7 seeds >60 s), so only the strongest few seeds go to MLCore, with a short timeout.
MLCORE_SEED_LIMIT = int(getattr(settings, 'RADIO_MLCORE_SEED_LIMIT', 3))
MLCORE_TIMEOUT_SECONDS = float(getattr(settings, 'RADIO_MLCORE_TIMEOUT_SECONDS', 6))
# One overall budget for picking tracks (seed expansion, both MLCore rankers, hydration,
# fallbacks). When it runs out we return what we have, using alias evidence for tracks
# Spotify hasn't hydrated yet.
NEXT_BUDGET_SECONDS = float(getattr(settings, 'RADIO_NEXT_BUDGET_SECONDS', 4))
MIN_ENGINE_SECONDS = 0.3

# Emoji feelings → search keywords. Free-text feelings are used as search terms directly.
FEELING_KEYWORDS = {
    '🌙': 'late night', '🌃': 'late night', '☕': 'slow morning', '🌅': 'sunrise', '🌄': 'morning',
    '🌧️': 'rainy day', '🌧': 'rainy day', '☔': 'rainy day', '❄️': 'winter', '☀️': 'sunny', '🌞': 'summer',
    '🏖️': 'beach', '💃': 'dance', '🕺': 'dance', '🪩': 'disco', '🎉': 'party', '🔥': 'hype', '⚡': 'energy',
    '🏃': 'running', '💪': 'workout', '🚗': 'road trip', '🛣️': 'road trip', '😌': 'chill', '🧘': 'calm',
    '😴': 'sleep', '🛌': 'sleep', '📚': 'focus', '🧠': 'focus', '💻': 'focus', '❤️': 'love', '💕': 'love',
    '💔': 'heartbreak', '😢': 'sad', '😭': 'sad', '🥲': 'bittersweet', '😊': 'happy', '😄': 'happy',
    '🤘': 'rock', '🎸': 'guitar', '🎹': 'piano', '🎷': 'jazz', '🎻': 'strings', '🌴': 'tropical',
    '🍂': 'autumn', '🌸': 'spring', '🌊': 'ocean', '✨': 'dreamy', '🌈': 'feel good', '🕯️': 'cozy',
    '🍷': 'dinner', '🎄': 'holiday', '👀': 'discover',
}
DEFAULT_KEYWORDS = ('feel good', 'chill')


def feeling_keyword(feeling: str) -> str:
    feeling = (feeling or '').strip()
    return FEELING_KEYWORDS.get(feeling) or FEELING_KEYWORDS.get(feeling.replace('️', '')) or feeling


@dataclass
class Recommendation:
    tracks: List[Dict] = field(default_factory=list)
    source: str = 'search'


@dataclass
class _Context:
    station: Station
    seed_track_ids: List[str]
    seed_artist_ids: List[str]
    keywords: List[str]
    flt: signals.ExclusionFilter


def _seed_ids(seeds: Sequence[Dict], kind: str) -> List[str]:
    return [seed['spotifyId'] for seed in seeds if seed.get('kind') == kind and seed.get('spotifyId')]


def resolve_station_seeds(station: Station) -> tuple[List[str], List[str]]:
    """Explicit station seeds → (track ids, artist ids). Artist/album seeds expand to a few tracks."""
    seeds = station.seeds or []
    track_ids = _seed_ids(seeds, 'track')
    artist_ids = _seed_ids(seeds, 'artist')
    for artist_id in artist_ids:
        track_ids += [track['spotifyId'] for track in spotify.artist_top_tracks(artist_id)[:3]]
    for album_id in _seed_ids(seeds, 'album'):
        track_ids += spotify.album_track_ids(album_id, limit=3)
    return list(dict.fromkeys(track_ids)), artist_ids


def build_context(user, station: Station, recent_ids: Iterable[str] = ()) -> _Context:
    recent = list(dict.fromkeys(list(recent_ids) + signals.recent_track_ids(user)))
    flt = signals.ExclusionFilter.build(signals.applicable_exclusions(user, station), recent)
    seed_tracks: List[str] = []
    seed_artists: List[str] = []
    if station.is_personal:
        if station.learning:
            seed_tracks += signals.learned_track_ids(user)
        seed_tracks += signals.memory_song_ids(user)
        if not seed_tracks:
            seed_tracks, seed_artists = resolve_station_seeds(station)
    else:
        seed_tracks, seed_artists = resolve_station_seeds(station)
        if station.learning:
            seed_tracks += signals.learned_track_ids(user, station=station)
    keywords = [feeling_keyword(feeling) for feeling in station.feelings or []]
    if not keywords:
        keywords = [seed.get('subtitle') or seed.get('title') for seed in station.seeds or []
                    if seed.get('kind') == 'artist' or seed.get('subtitle')]
        keywords = [keyword for keyword in keywords if keyword][:3]
    if not keywords and station.is_personal:
        keywords = signals.memory_tags(user, limit=3)
    return _Context(
        station=station,
        seed_track_ids=list(dict.fromkeys(seed_tracks))[:MAX_SEEDS],
        seed_artist_ids=list(dict.fromkeys(seed_artists)),
        keywords=list(dict.fromkeys(keywords)) or list(DEFAULT_KEYWORDS),
        flt=flt,
    )


def _identity(track_id: str) -> Dict[str, str]:
    return {'source': 'spotify', 'resource_type': 'track', 'source_id': track_id}


def spotify_ids_for_canonical(canonical_ids: Sequence[str]) -> Dict[str, Dict]:
    """canonical_item_id → {spotifyId, evidence}. Uses the canonical_item index only.

    Filtering source/resource_type/status in SQL makes Postgres pick the (source,
    resource_type, source_id) index and scan every Spotify track alias (measured ~280k
    rows on neptune); looking up by canonical_item_id touches a handful of rows, so the
    remaining predicates are applied in Python.
    """
    if not canonical_ids:
        return {}
    rows = CanonicalItemAlias.objects.filter(canonical_item_id__in=list(canonical_ids)).values_list(
        'canonical_item_id', 'source', 'resource_type', 'status', 'source_id', 'confidence', 'metadata')
    best: Dict[str, tuple] = {}
    for canonical_id, source, resource_type, status, source_id, confidence, metadata in rows:
        if source != 'spotify' or resource_type != 'track' or status != 'active':
            continue
        key = str(canonical_id)
        if key not in best or confidence > best[key][0]:
            best[key] = (confidence, source_id, metadata or {})
    return {key: {'spotifyId': value[1], 'evidence': (value[2].get('evidence') or {})} for key, value in best.items()}


def _evidence_track(spotify_id: str, evidence: Dict) -> Dict:
    artists = [artist for artist in evidence.get('artists') or [] if isinstance(artist, str) and artist]
    return {
        'spotifyId': spotify_id,
        'uri': evidence.get('uri') or f'spotify:track:{spotify_id}',
        'title': evidence.get('name') or '',
        'artist': ', '.join(artists),
        'artistId': '',
        'artistIds': [],
        'artistNames': artists,
        'album': '',
        'albumId': '',
        'artworkUrl': None,
        'durationMs': int(evidence.get('duration_ms') or 0),
    }


def mlcore_seed_sample(seed_ids: Sequence[str]) -> List[str]:
    """The strongest (first) seed plus a rotating sample of the rest, so picks vary between calls."""
    seed_ids = list(dict.fromkeys(seed_ids))
    if len(seed_ids) <= MLCORE_SEED_LIMIT:
        return seed_ids
    return seed_ids[:1] + random.sample(seed_ids[1:], MLCORE_SEED_LIMIT - 1)


def mlcore_track_ids(ranker: str, seed_ids: Sequence[str], exclude_ids: Sequence[str], limit: int) -> List[tuple[str, Dict]]:
    """Ranked (spotifyId, evidence) pairs from an MLCore identity ranker; [] on any failure."""
    from recommender.services import client

    if not seed_ids:
        return []
    timeout = MLCORE_TIMEOUT_SECONDS
    left = spotify.remaining()
    if left is not None:
        if left < MIN_ENGINE_SECONDS:
            return []
        timeout = min(timeout, left)
    payload = {
        'seed_items': [_identity(track_id) for track_id in mlcore_seed_sample(seed_ids)],
        'exclude_items': [_identity(track_id) for track_id in list(exclude_ids)[:MAX_IDENTITY_ITEMS]],
        'limit': max(1, min(limit, MAX_IDENTITY_ITEMS)),
    }
    try:
        response = client.fetch_identity_recommendations(ranker, payload, timeout=timeout)
    except Exception as exc:  # engine outages fall through to the next source
        logger.warning('MLCore %s ranker unavailable for radio: %s', ranker, exc)
        return []
    canonical_ids = [str(item.get('canonical_item_id')) for item in (response or {}).get('items') or []
                     if item.get('canonical_item_id')]
    aliases = spotify_ids_for_canonical(canonical_ids)
    return [(aliases[cid]['spotifyId'], aliases[cid]['evidence']) for cid in canonical_ids if cid in aliases]


class _Picker:
    """Accumulates filtered, hydrated, artist-diverse tracks across sources."""

    def __init__(self, ctx: _Context, count: int):
        self.ctx = ctx
        self.count = count
        self.tracks: List[Dict] = []
        self.overflow: List[tuple[str, Dict]] = []
        self.source: Optional[str] = None
        self.seen: set = set()

    @property
    def done(self) -> bool:
        return len(self.tracks) >= self.count

    @staticmethod
    def artist_key(track: Dict) -> str:
        """One de-dup key per track: primary artist id, else primary artist name."""
        ids = track.get('artistIds') or ([track['artistId']] if track.get('artistId') else [])
        if ids:
            return f'id:{ids[0]}'
        names = track.get('artistNames') or [track.get('artist') or '']
        return f'name:{(names[0] if names else "").strip().casefold()}'

    def _artists(self) -> set:
        return {self.artist_key(track) for track in self.tracks}

    def offer(self, source: str, candidates: Iterable[Dict]) -> None:
        for track in candidates:
            if self.done:
                return
            track_id = track.get('spotifyId')
            if not track_id or track_id in self.seen or self.ctx.flt.blocks_track(track):
                continue
            self.seen.add(track_id)
            if self.artist_key(track) in self._artists():
                self.overflow.append((source, track))
                continue
            self.tracks.append(track)
            self.source = self.source or source

    def offer_ids(self, source: str, ids_with_evidence: Sequence[tuple[str, Dict]]) -> None:
        ids = [(track_id, evidence) for track_id, evidence in ids_with_evidence
               if track_id not in self.seen and not self.ctx.flt.blocks_id(track_id)]
        if not ids:
            return
        # Hydrate a bounded window at a time to keep Spotify calls proportional to need.
        window = max(self.count * 3, 10)
        for start in range(0, len(ids), window):
            chunk = ids[start:start + window]
            # Out of budget: get_tracks only serves the cache; the rest fall back to alias evidence.
            hydrated = spotify.get_tracks([track_id for track_id, _ in chunk])
            self.offer(source, [hydrated.get(track_id) or _evidence_track(track_id, evidence) for track_id, evidence in chunk])
            if self.done:
                return

    def finish(self) -> Recommendation:
        # Not enough distinct artists: allow repeats rather than coming up short.
        for source, track in self.overflow:
            if self.done:
                break
            self.tracks.append(track)
            self.source = self.source or source
        return Recommendation(tracks=self.tracks[:self.count], source=self.source or 'search')


def next_tracks(user, station: Station, count: int = 3, recent_ids: Iterable[str] = ()) -> Recommendation:
    with spotify.budget(NEXT_BUDGET_SECONDS):
        return _next_tracks(user, station, count, recent_ids)


def _next_tracks(user, station: Station, count: int, recent_ids: Iterable[str]) -> Recommendation:
    ctx = build_context(user, station, recent_ids)
    picker = _Picker(ctx, count)
    exclude = ctx.flt.engine_exclusions(MAX_IDENTITY_ITEMS)
    want = min(MAX_IDENTITY_ITEMS, count * 5 + 10)

    for ranker, source in (('cooccurrence', 'mlcore'), ('metadata', 'metadata')):
        if picker.done or spotify.out_of_time(MIN_ENGINE_SECONDS):
            break
        picker.offer_ids(source, mlcore_track_ids(ranker, ctx.seed_track_ids, exclude, want))

    if not picker.done and not spotify.out_of_time():
        artist_ids = list(ctx.seed_artist_ids)
        seed_tracks = spotify.get_tracks(ctx.seed_track_ids[:10]) if ctx.seed_track_ids else {}
        artist_ids += [track['artistId'] for track in seed_tracks.values() if track.get('artistId')]
        for artist_id in list(dict.fromkeys(artist_ids))[:8]:
            if picker.done or spotify.out_of_time():
                break
            picker.offer('artist', spotify.artist_top_tracks(artist_id))

    for keyword in ctx.keywords:
        if picker.done or spotify.out_of_time():
            break
        picker.offer('search', spotify.search_tracks(keyword))

    if not picker.done and ctx.seed_track_ids:
        hydrated = spotify.get_tracks(ctx.seed_track_ids)  # cache-only once the budget is spent
        picker.offer('seed', [hydrated[track_id] for track_id in ctx.seed_track_ids if track_id in hydrated])

    return picker.finish()


def crate_track_picks(user, seed_ids: Sequence[str], limit: int) -> List[Dict]:
    """MLCore co-occurrence picks for the crate, hydrated, without exclusions/recency rules."""
    with spotify.budget(NEXT_BUDGET_SECONDS):
        pairs = mlcore_track_ids('cooccurrence', list(seed_ids)[:MAX_SEEDS], [], limit)
    hydrated = spotify.get_tracks([track_id for track_id, _ in pairs])
    return [hydrated.get(track_id) or _evidence_track(track_id, evidence) for track_id, evidence in pairs]

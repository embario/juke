"""Radio recommendation pipeline.

Stations with seeds stay close to them. Shortfalls are filled in this order:

1. MLCore co-occurrence on the seeds (→ Spotify aliases);
2. a second co-occurrence hop seeded with the first good picks;
3. the MLCore metadata ranker;
4. top tracks of the seed artists (every credited artist);
5. top tracks of artists that co-occur (artists of the MLCore picks);
6. Spotify search on *sound* (genre filters from the station's feelings, or the seed
   artists' genres);
7. the seeds themselves.

Feelings on a seeded station re-rank the candidate pool by artist-genre affinity rather than
injecting songs whose titles happen to contain the feeling's words. Feeling-only stations
search genre filters (``feelings.py``), drop literal title matches that don't fit and
diversify artists. Every source is filtered by exclusions and recent history.
"""
from __future__ import annotations

import logging
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from django.conf import settings

from mlcore.models import CanonicalItemAlias
from radio.models import Station
from radio.services import feelings as feeling_rules
from radio.services import signals, spotify
from radio.services.feelings import FEELING_KEYWORDS, feeling_keyword  # noqa: F401 - re-exported

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
# MLCore may not spend the whole budget: keep this much for the (fast, ~0.1–0.3 s per call)
# Spotify fallbacks — seed artists' top tracks, hydration — which give far better radio than
# an empty or single-artist batch. Measured on neptune: a cold second co-occurrence hop can
# exceed 2 s and used to starve every later source.
MLCORE_RESERVE_SECONDS = float(getattr(settings, 'RADIO_MLCORE_RESERVE_SECONDS', 1.5))
MAX_ARTIST_EXPANSION = 4
MAX_SEARCH_QUERIES = 8
POOL_FACTOR = 2  # seeded + feelings: gather 2× candidates, then re-rank by feeling affinity
LAST_RESORT_TIERS = {'search': 1, 'seed': 2}

# Public source names (the ``source`` enum of the API contract).
SOURCES = ('mlcore', 'metadata', 'artist', 'search', 'seed')


@dataclass
class Recommendation:
    tracks: List[Dict] = field(default_factory=list)
    source: str = 'search'


@dataclass
class _Context:
    station: Station
    seed_track_ids: List[str]
    seed_artist_ids: List[str]
    feelings: List[str]
    flt: signals.ExclusionFilter
    fallback_feelings: List[str] = field(default_factory=list)  # personal: memory tags

    @property
    def has_seeds(self) -> bool:
        return bool(self.seed_track_ids or self.seed_artist_ids)


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
    station_feelings = [feeling for feeling in station.feelings or [] if feeling.strip()]
    memory_feelings = signals.memory_tags(user, limit=3) if station.is_personal and not station_feelings else []
    if not station_feelings and not seed_tracks and not seed_artists:
        station_feelings = memory_feelings
    return _Context(
        station=station,
        seed_track_ids=list(dict.fromkeys(seed_tracks))[:MAX_SEEDS],
        seed_artist_ids=list(dict.fromkeys(seed_artists)),
        feelings=list(dict.fromkeys(station_feelings)),
        flt=flt,
        fallback_feelings=memory_feelings,
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


def mlcore_track_ids(ranker: str, seed_ids: Sequence[str], exclude_ids: Sequence[str], limit: int, *,
                     reserve: float = MLCORE_RESERVE_SECONDS) -> List[tuple[str, Dict]]:
    """Ranked (spotifyId, evidence) pairs from an MLCore identity ranker; [] on any failure.

    ``reserve`` seconds of the current budget are left for the callers' Spotify fallbacks.
    """
    from recommender.services import client

    if not seed_ids:
        return []
    timeout = MLCORE_TIMEOUT_SECONDS
    left = spotify.remaining()
    if left is not None:
        left -= reserve
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


def coarse(source: str) -> str:
    return source.split(':', 1)[0]


class _Picker:
    """Accumulates filtered, hydrated, artist-diverse tracks across sources.

    Sources are detailed labels (``mlcore:hop2``, ``artist:cooccur``, ``search:genre`` …);
    the API's ``source`` uses the part before the colon.
    """

    def __init__(self, ctx: _Context, count: int, target: Optional[int] = None):
        self.ctx = ctx
        self.count = count
        self.target = max(count, target or count)
        self.tracks: List[Dict] = []
        self.overflow: List[Dict] = []
        self.sources: Dict[str, List[str]] = {}
        self.seen: set = set()

    @property
    def done(self) -> bool:
        return len(self.tracks) >= self.target

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

    def picked_from(self, *prefixes: str) -> List[Dict]:
        """Accepted and overflow tracks whose first source starts with one of ``prefixes``."""
        return [track for track in self.tracks + self.overflow
                if any(self.sources[track['spotifyId']][0].startswith(prefix) for prefix in prefixes)]

    def offer(self, source: str, candidates: Iterable[Dict]) -> None:
        self.offer_pairs((source, track) for track in candidates)

    def offer_pairs(self, pairs: Iterable[Tuple[str, Dict]]) -> None:
        for source, track in pairs:
            track_id = (track or {}).get('spotifyId')
            if not track_id:
                continue
            if track_id in self.sources and source not in self.sources[track_id]:
                self.sources[track_id].append(source)  # also suggested by a later source
            if self.done:
                continue
            if track_id in self.seen or self.ctx.flt.blocks_track(track):
                continue
            self.seen.add(track_id)
            self.sources[track_id] = [source]
            if self.artist_key(track) in self._artists():
                self.overflow.append(track)
                continue
            self.tracks.append(track)

    def offer_ids(self, source: str, ids_with_evidence: Sequence[tuple[str, Dict]]) -> None:
        ids = [(track_id, evidence) for track_id, evidence in ids_with_evidence
               if track_id not in self.seen and not self.ctx.flt.blocks_id(track_id)]
        if not ids:
            return
        # Hydrate a bounded window at a time to keep Spotify calls proportional to need.
        window = max(self.target * 3, 10)
        for start in range(0, len(ids), window):
            chunk = ids[start:start + window]
            # Out of budget: get_tracks only serves the cache; the rest fall back to alias evidence.
            hydrated = spotify.get_tracks([track_id for track_id, _ in chunk])
            self.offer(source, [hydrated.get(track_id) or _evidence_track(track_id, evidence) for track_id, evidence in chunk])
            if self.done:
                return

    def finish(self, rank: Optional[Callable[[List[Dict]], List[Dict]]] = None) -> Recommendation:
        pool = list(self.tracks)
        # Not enough distinct artists: allow repeats rather than coming up short.
        for track in self.overflow:
            if len(pool) >= self.count:
                break
            pool.append(track)
        if rank is not None and len(pool) > self.count:
            pool = rank(pool)
        chosen = pool[:self.count]
        tracks = [{**track, 'sources': list(self.sources[track['spotifyId']])} for track in chosen]
        return Recommendation(tracks=tracks, source=majority_source(tracks))


def majority_source(tracks: Sequence[Dict]) -> str:
    """The public source that supplied most of the batch; ties go to the earliest track."""
    firsts = [coarse(track['sources'][0]) for track in tracks if track.get('sources')]
    if not firsts:
        return 'search'
    counts = Counter(firsts)
    best = max(counts.values())
    return next(source for source in firsts if counts[source] == best)


def _feeling_ranker(feelings: Sequence[str], sources: Dict[str, List[str]]) -> Optional[Callable[[List[Dict]], List[Dict]]]:
    wanted = feeling_rules.feeling_genres(feelings)
    if not wanted:
        return None

    def rank(pool: List[Dict]) -> List[Dict]:
        artist_ids = [artist_id for track in pool for artist_id in (track.get('artistIds') or [])[:2]]
        genres = spotify.artist_genres(artist_ids)
        if not genres:
            return pool  # nothing known about the sound: keep source order

        def affinity(track):
            return max((feeling_rules.genre_affinity(genres.get(artist_id, []), wanted)
                        for artist_id in (track.get('artistIds') or [])[:2]), default=0)

        def tier(track):
            # Discoveries near the seeds first, sound-search fill next, the seeds themselves last;
            # feelings only reorder within a tier.
            source = sources[track['spotifyId']][0]
            return LAST_RESORT_TIERS.get(coarse(source), 0)

        # Stable: within equal tier and affinity the source order (seed closeness) is kept.
        return sorted(pool, key=lambda track: (tier(track), -affinity(track)))
    return rank


def _sound_search(picker: _Picker, feelings: Sequence[str], extra_genres: Sequence[str] = (),
                  extra_queries: Sequence[Tuple[str, str]] = ()) -> None:
    """Search Spotify by sound (genre filters), round-robin across queries for variety.

    ``extra_queries`` are tried first, e.g. ``('artist:"Name"', 'artist')`` for seed artists.
    Page 2 is only fetched for queries whose first page was full, which bounds the worst case.
    """
    queries = list(dict.fromkeys(list(extra_queries) + feeling_rules.search_queries(feelings, extra_genres=extra_genres)))
    queries = queries[:MAX_SEARCH_QUERIES]
    if not queries:
        return
    wanted = feeling_rules.feeling_genres(feelings) | {genre.casefold() for genre in extra_genres}
    max_duration = feeling_rules.max_duration_ms(feelings)
    artist_names = {query: query.split(':', 1)[1].strip('"').casefold() for query, kind in queries if kind == 'artist'}
    for offset in (0, spotify.SEARCH_LIMIT):
        if picker.done or spotify.out_of_time() or not queries:
            return
        columns = []
        full_pages = []
        for query, kind in queries:
            if spotify.out_of_time():
                break
            results = spotify.search_tracks(query, offset=offset)
            if len(results) >= spotify.SEARCH_LIMIT:
                full_pages.append((query, kind))
            if kind == 'artist':
                # An artist filter can still surface songs that merely mention the name.
                name = artist_names[query]
                results = [track for track in results
                           if name in {artist.casefold() for artist in track.get('artistNames') or []}]
            columns.append([(f'search:{kind}', track) for track in results])
        queries = full_pages
        literal = [track for column in columns for source, track in column
                   if source == 'search:text' and feeling_rules.literal_title_match(track, feelings)]
        literal_genres = spotify.artist_genres([(track.get('artistIds') or [''])[0] for track in literal]) if literal else {}
        seen_titles = set()
        pairs = []
        for row in range(max((len(column) for column in columns), default=0)):
            for column in columns:
                if row >= len(column):
                    continue
                source, track = column[row]
                if not feeling_rules.looks_like_music(track, max_duration_ms=max_duration):
                    continue
                title_key = ((track.get('title') or '').casefold(), picker.artist_key(track))
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                if source == 'search:text' and feeling_rules.literal_title_match(track, feelings):
                    # "Late Night" by anyone is not late-night music; keep it only if the artist fits.
                    artist_genres = literal_genres.get((track.get('artistIds') or [''])[0], [])
                    if feeling_rules.genre_affinity(artist_genres, wanted) == 0:
                        continue
                pairs.append((source, track))
        picker.offer_pairs(pairs)


def _seed_artist_names(ctx: _Context, seed_artists: Sequence[str]) -> List[str]:
    """Names of the seed artists from cached track payloads and the station's artist seeds."""
    names: List[str] = []
    for track in spotify.cached_tracks(ctx.seed_track_ids[:10]).values():
        for artist_id, name in zip(track.get('artistIds') or [], track.get('artistNames') or []):
            if artist_id in seed_artists and name:
                names.append(name)
    names += [seed.get('title') or '' for seed in ctx.station.seeds or [] if seed.get('kind') == 'artist']
    return [name for name in dict.fromkeys(names) if name and '"' not in name]


def next_tracks(user, station: Station, count: int = 3, recent_ids: Iterable[str] = ()) -> Recommendation:
    with spotify.budget(NEXT_BUDGET_SECONDS):
        return _next_tracks(user, station, count, recent_ids)


def _next_tracks(user, station: Station, count: int, recent_ids: Iterable[str]) -> Recommendation:
    ctx = build_context(user, station, recent_ids)
    if not ctx.has_seeds:
        picker = _Picker(ctx, count)
        _sound_search(picker, ctx.feelings or list(feeling_rules.DEFAULT_FEELINGS))
        return picker.finish()

    rerank = bool(ctx.feelings and feeling_rules.feeling_genres(ctx.feelings))
    picker = _Picker(ctx, count, target=min(20, count * POOL_FACTOR) if rerank else count)
    rank = _feeling_ranker(ctx.feelings, picker.sources) if rerank else None
    exclude = ctx.flt.engine_exclusions(MAX_IDENTITY_ITEMS)
    want = min(MAX_IDENTITY_ITEMS, picker.target * 5 + 10)

    def engine_time() -> bool:
        return not picker.done and not spotify.out_of_time(MIN_ENGINE_SECONDS + MLCORE_RESERVE_SECONDS)

    cooccurrence: List[tuple[str, Dict]] = []
    if engine_time():
        cooccurrence = mlcore_track_ids('cooccurrence', ctx.seed_track_ids, exclude, want)
        picker.offer_ids('mlcore', cooccurrence)

    if engine_time() and cooccurrence:
        # Second hop: the first good picks become seeds, reaching past one album or artist.
        good = [track['spotifyId'] for track in picker.picked_from('mlcore')] or [track_id for track_id, _ in cooccurrence]
        hop_seeds = [track_id for track_id in good if track_id not in ctx.seed_track_ids][:MLCORE_SEED_LIMIT]
        if hop_seeds:
            # User exclusions first so truncation only ever drops the least important ids.
            hop_exclude = list(dict.fromkeys(ctx.flt.excluded_track_ids + ctx.seed_track_ids + exclude
                                             + list(picker.seen)))[:MAX_IDENTITY_ITEMS]
            picker.offer_ids('mlcore:hop2', mlcore_track_ids('cooccurrence', hop_seeds, hop_exclude, want))

    if engine_time():
        picker.offer_ids('metadata', mlcore_track_ids('metadata', ctx.seed_track_ids, exclude, want))

    seed_artists = list(ctx.seed_artist_ids)
    if not picker.done and not spotify.out_of_time():
        seed_tracks = spotify.get_tracks(ctx.seed_track_ids[:10]) if ctx.seed_track_ids else {}
        seed_artists += [artist_id for track in seed_tracks.values() for artist_id in track.get('artistIds') or []]
        seed_artists = list(dict.fromkeys(seed_artists))
        for artist_id in seed_artists[:MAX_ARTIST_EXPANSION]:
            if picker.done or spotify.out_of_time():
                break
            picker.offer('artist:seed', spotify.artist_top_tracks(artist_id))

    if not picker.done and not spotify.out_of_time():
        cooccurring = [artist_id for track in picker.picked_from('mlcore') for artist_id in (track.get('artistIds') or [])[:1]]
        cooccurring = [artist_id for artist_id in dict.fromkeys(cooccurring) if artist_id not in seed_artists]
        for artist_id in cooccurring[:MAX_ARTIST_EXPANSION]:
            if picker.done or spotify.out_of_time():
                break
            picker.offer('artist:cooccur', spotify.artist_top_tracks(artist_id))

    # Sound search only fills a real shortfall (fewer seed-related tracks than requested),
    # never the extra re-ranking pool.
    if len(picker.tracks) < count and not spotify.out_of_time():
        if ctx.feelings:
            _sound_search(picker, ctx.feelings)
        else:
            genres = spotify.artist_genres(seed_artists[:MAX_ARTIST_EXPANSION]) if seed_artists else {}
            seed_genres = list(dict.fromkeys(genre for artist_id in seed_artists for genre in genres.get(artist_id, [])))[:3]
            # Spotify often has no genres for an artist (or refuses the lookup): then search the seed
            # artists by name, and fall back to memory tags (personal) or the default profile.
            artist_queries = [(f'artist:"{name}"', 'artist') for name in _seed_artist_names(ctx, seed_artists)[:3]]
            fallback = ctx.fallback_feelings or ([] if seed_genres else list(feeling_rules.DEFAULT_FEELINGS))
            _sound_search(picker, fallback, seed_genres, extra_queries=[] if seed_genres else artist_queries)

    # The seeds themselves only fill a real shortfall and rank last.
    if len(picker.tracks) < count and ctx.seed_track_ids:
        hydrated = spotify.get_tracks(ctx.seed_track_ids)  # cache-only once the budget is spent
        picker.offer('seed', [hydrated[track_id] for track_id in ctx.seed_track_ids if track_id in hydrated])

    return picker.finish(rank)


def crate_track_picks(user, seed_ids: Sequence[str], limit: int) -> List[Dict]:
    """MLCore co-occurrence picks for the crate, hydrated, without exclusions/recency rules."""
    with spotify.budget(NEXT_BUDGET_SECONDS):
        # The crate has no Spotify fallbacks after MLCore, so it keeps the whole budget.
        pairs = mlcore_track_ids('cooccurrence', list(seed_ids)[:MAX_SEEDS], [], limit, reserve=0)
        hydrated = spotify.get_tracks([track_id for track_id, _ in pairs])
    return [hydrated.get(track_id) or _evidence_track(track_id, evidence) for track_id, evidence in pairs]

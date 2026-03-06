"""
Pure-Python scoring functions for Phase 1 baseline rankers (arch §7.1, §7.2).

Zero third-party deps — stdlib only — so these are testable from the
Django backend test runner without numpy/fastapi/psycopg installed.
main.py wires SQL I/O and HTTP serialization around these.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping
from uuid import UUID

# Metadata scoring weights (arch §7.1).
W_SAME_ARTIST = 1.0
W_SAME_ALBUM = 0.8
W_SHARED_GENRE = 0.5
W_SHARED_WORK = 0.4  # no work-relation data in Phase 1 — reserved


@dataclass
class ScoredItem:
    juke_id: UUID
    score: float
    components: dict[str, float] = field(default_factory=dict)


def _rank(items: list[ScoredItem], limit: int) -> list[ScoredItem]:
    """Score desc, juke_id asc for deterministic tie-break."""
    items.sort(key=lambda i: (-i.score, str(i.juke_id)))
    return items[:limit]


# --- metadata scorer ---

def score_metadata(
    seed_feature_rows: Iterable[Mapping],
    candidate_feature_rows: Iterable[Mapping],
    exclude: set[UUID],
    limit: int,
) -> list[ScoredItem]:
    """
    Score candidates by metadata overlap with seeds.

    Each row (seed or candidate) is {juke_id, album_id, artist_id, genre_id}.
    One track may appear in multiple rows due to M2M join cross-product
    (multi-artist albums, multi-genre artists) — we union features per track.

    Final score = max(artist_hit, album_hit, genre_hit). Max aggregation
    is more explainable than sum ("this is 1.0 because same artist as seed X").
    """
    seed_albums: set = set()
    seed_artists: set = set()
    seed_genres: set = set()
    for r in seed_feature_rows:
        if r['album_id'] is not None:
            seed_albums.add(r['album_id'])
        if r['artist_id'] is not None:
            seed_artists.add(r['artist_id'])
        if r['genre_id'] is not None:
            seed_genres.add(r['genre_id'])

    if not (seed_albums or seed_artists or seed_genres):
        return []

    cand_albums: dict[UUID, set] = defaultdict(set)
    cand_artists: dict[UUID, set] = defaultdict(set)
    cand_genres: dict[UUID, set] = defaultdict(set)
    for r in candidate_feature_rows:
        jid = r['juke_id']
        if r['album_id'] is not None:
            cand_albums[jid].add(r['album_id'])
        if r['artist_id'] is not None:
            cand_artists[jid].add(r['artist_id'])
        if r['genre_id'] is not None:
            cand_genres[jid].add(r['genre_id'])

    items: list[ScoredItem] = []
    for jid in cand_albums.keys() | cand_artists.keys() | cand_genres.keys():
        if jid in exclude:
            continue
        artist_hit = W_SAME_ARTIST if (cand_artists[jid] & seed_artists) else 0.0
        album_hit = W_SAME_ALBUM if (cand_albums[jid] & seed_albums) else 0.0
        genre_hit = W_SHARED_GENRE if (cand_genres[jid] & seed_genres) else 0.0
        score = max(artist_hit, album_hit, genre_hit)
        if score <= 0.0:
            continue
        items.append(ScoredItem(
            juke_id=jid,
            score=score,
            components={
                'same_artist': artist_hit,
                'same_album': album_hit,
                'shared_genre': genre_hit,
                'shared_work': 0.0,
            },
        ))

    return _rank(items, limit)


def extract_seed_feature_ids(seed_rows: Iterable[Mapping]) -> tuple[list, list, list]:
    """Pull album/artist/genre ID lists from seed rows for SQL ANY() params."""
    albums: set = set()
    artists: set = set()
    genres: set = set()
    for r in seed_rows:
        if r['album_id'] is not None:
            albums.add(r['album_id'])
        if r['artist_id'] is not None:
            artists.add(r['artist_id'])
        if r['genre_id'] is not None:
            genres.add(r['genre_id'])
    # Sentinel -1 for empty sets so ANY([-1]) matches nothing but stays valid SQL.
    return (list(albums) or [-1], list(artists) or [-1], list(genres) or [-1])


# --- co-occurrence scorer ---

def score_cooccurrence(
    neighbour_rows: Iterable[Mapping],
    exclude: set[UUID],
    limit: int,
) -> list[ScoredItem]:
    """
    Aggregate PMI scores across seeds.

    Each row is {neighbour, pmi_score, co_count}. The same neighbour may
    appear multiple times (co-occurred with multiple seeds) — sum their PMIs.
    """
    agg_pmi: dict[UUID, float] = defaultdict(float)
    agg_count: dict[UUID, int] = defaultdict(int)
    for r in neighbour_rows:
        jid = r['neighbour']
        if jid in exclude:
            continue
        agg_pmi[jid] += float(r['pmi_score'])
        agg_count[jid] += int(r['co_count'])

    items = [
        ScoredItem(
            juke_id=jid,
            score=pmi,
            components={'pmi_sum': pmi, 'co_count_sum': float(agg_count[jid])},
        )
        for jid, pmi in agg_pmi.items()
    ]
    return _rank(items, limit)

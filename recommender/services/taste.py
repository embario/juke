from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

from juke_auth.models import MusicProfile


def _normalized_list(values: Iterable[str | None]) -> List[str]:
    return sorted({value.strip() for value in values if value})


def profile_to_payload(profile: MusicProfile) -> Dict[str, Sequence[str]]:
    return {
        'artists': _normalized_list(profile.favorite_artists or []),
        'albums': _normalized_list(profile.favorite_albums or []),
        'tracks': _normalized_list(profile.favorite_tracks or []),
        'genres': _normalized_list(profile.favorite_genres or []),
    }


def mixed_payload(*, artists=None, albums=None, tracks=None, genres=None) -> Dict[str, Sequence[str]]:
    return {
        'artists': _normalized_list(artists or []),
        'albums': _normalized_list(albums or []),
        'tracks': _normalized_list(tracks or []),
        'genres': _normalized_list(genres or []),
    }

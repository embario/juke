import logging
import os
import time
from typing import Any, Dict, List

from django.conf import settings
from django.core.cache import cache

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from catalog import spotify_stub

logger = logging.getLogger(__name__)

FEATURED_GENRES = [
    {"id": "hiphop", "name": "Hip-Hop", "spotify_seed": "hip-hop"},
    {"id": "pop", "name": "Pop", "spotify_seed": "pop"},
    {"id": "rock", "name": "Rock", "spotify_seed": "rock"},
    {"id": "rnb", "name": "R&B", "spotify_seed": "r&b"},
    {"id": "electronic", "name": "Electronic", "spotify_seed": "electronic"},
    {"id": "country", "name": "Country", "spotify_seed": "country"},
    {"id": "jazz", "name": "Jazz", "spotify_seed": "jazz"},
    {"id": "classical", "name": "Classical", "spotify_seed": "classical"},
    {"id": "latin", "name": "Latin", "spotify_seed": "latin"},
    {"id": "indie", "name": "Indie", "spotify_seed": "indie"},
    {"id": "metal", "name": "Metal", "spotify_seed": "metal"},
    {"id": "reggae", "name": "Reggae", "spotify_seed": "reggae"},
    {"id": "folk", "name": "Folk", "spotify_seed": "folk"},
    {"id": "blues", "name": "Blues", "spotify_seed": "blues"},
    {"id": "funk", "name": "Funk", "spotify_seed": "funk"},
    {"id": "punk", "name": "Punk", "spotify_seed": "punk"},
    {"id": "soul", "name": "Soul", "spotify_seed": "soul"},
    {"id": "rap", "name": "Rap", "spotify_seed": "rap"},
    {"id": "edm", "name": "EDM", "spotify_seed": "edm"},
    {"id": "house", "name": "House", "spotify_seed": "house"},
]
FEATURED_GENRES_CACHE_KEY = "catalog:featured_genres"
FEATURED_GENRES_CACHE_TTL_SECONDS = 60 * 60 * 24
FEATURED_GENRES_FETCH_BUDGET_SECONDS = int(os.environ.get("FEATURED_GENRES_FETCH_BUDGET_SECONDS", "6"))
SPOTIFY_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("SPOTIFY_REQUEST_TIMEOUT_SECONDS", "2"))


def _spotify_client() -> spotipy.Spotify | None:
    if getattr(settings, "SPOTIFY_USE_STUB_DATA", False):
        return None
    return spotipy.Spotify(
        client_credentials_manager=SpotifyClientCredentials(),
        requests_timeout=SPOTIFY_REQUEST_TIMEOUT_SECONDS,
        retries=0,
    )


def _artist_image_url(artist: Dict[str, Any]) -> str:
    images = artist.get("images") or []
    if images:
        return images[0].get("url") or ""
    return ""


def _search_artists_by_genre(client: spotipy.Spotify | None, genre_seed: str, limit: int) -> List[Dict[str, Any]]:
    if client is None:
        data = spotify_stub.search_response("artist")
        return list(data.get("items", []))[:limit]
    query = f'genre:"{genre_seed}"'
    response = client.search(q=query, type="artist", limit=max(10, limit))
    return response.get("artists", {}).get("items", [])[:limit]


def _build_featured_genres_payload(
    client: spotipy.Spotify | None,
    top_artists: int,
    *,
    enforce_budget: bool = True,
) -> List[Dict[str, Any]]:
    payload = []
    deadline = (
        time.monotonic() + FEATURED_GENRES_FETCH_BUDGET_SECONDS
        if enforce_budget and FEATURED_GENRES_FETCH_BUDGET_SECONDS > 0
        else None
    )

    for idx, genre in enumerate(FEATURED_GENRES):
        if deadline is not None and time.monotonic() > deadline:
            logger.warning("Featured genres fetch exceeded time budget; returning partial data.")
            for remaining in FEATURED_GENRES[idx:]:
                payload.append({
                    "id": remaining["id"],
                    "name": remaining["name"],
                    "spotify_id": remaining["spotify_seed"],
                    "top_artists": [],
                })
            break

        try:
            artists = _search_artists_by_genre(client, genre["spotify_seed"], top_artists)
        except Exception:
            logger.exception("Failed to fetch artists for genre seed '%s'", genre["spotify_seed"])
            artists = []

        payload.append({
            "id": genre["id"],
            "name": genre["name"],
            "spotify_id": genre["spotify_seed"],
            "top_artists": [
                {
                    "id": artist.get("id", ""),
                    "name": artist.get("name", ""),
                    "image_url": _artist_image_url(artist),
                }
                for artist in artists
            ],
        })

    return payload


def refresh_featured_genres(top_artists: int = 3, *, enforce_budget: bool = True) -> List[Dict[str, Any]]:
    client = _spotify_client()
    payload = _build_featured_genres_payload(client, top_artists, enforce_budget=enforce_budget)
    cache.set(FEATURED_GENRES_CACHE_KEY, payload, FEATURED_GENRES_CACHE_TTL_SECONDS)
    return payload


def get_featured_genres(top_artists: int = 3) -> List[Dict[str, Any]]:
    cached = cache.get(FEATURED_GENRES_CACHE_KEY)
    if cached is not None:
        return cached
    return refresh_featured_genres(top_artists=top_artists, enforce_budget=True)

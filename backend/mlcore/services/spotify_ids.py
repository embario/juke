"""Normalisation of Spotify track identifiers found in third-party data.

ListenBrainz clients and MusicBrainz URL relations carry the same 22-character base62 track ID in
many shapes (bare, ``spotify:track:`` URIs, ``open.spotify.com`` links with locale prefixes and
query strings). Every consumer that wants the ID uses :func:`normalize_spotify_track_id`.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

SPOTIFY_TRACK_ID_RE = re.compile(r'^[0-9A-Za-z]{22}$')
_SPOTIFY_HOSTS = {'open.spotify.com', 'play.spotify.com'}
_LOCALE_SEGMENT_RE = re.compile(r'^intl-[a-z]{2}(?:-[a-z]{2,4})?$', re.IGNORECASE)


def normalize_spotify_track_id(value: Any) -> str:
    """Return the bare 22-character track ID, or ``''`` for anything that is not a Spotify track."""
    text = str(value or '').strip()
    if not text:
        return ''
    if SPOTIFY_TRACK_ID_RE.match(text):
        return text

    if text.lower().startswith('spotify:'):
        parts = text.split(':')
        # spotify:track:<id>; user playlists are spotify:user:<u>:playlist:<id>
        if len(parts) == 3 and parts[1].lower() == 'track':
            return _bare(parts[2])
        return ''

    candidate = text if '://' in text else ('https://' + text if text.lower().startswith(tuple(_SPOTIFY_HOSTS)) else '')
    if not candidate:
        return ''
    try:
        split = urlsplit(candidate)
    except ValueError:
        return ''
    host = (split.hostname or '').lower()
    if host not in _SPOTIFY_HOSTS:
        return ''
    segments = [segment for segment in split.path.split('/') if segment]
    if segments and _LOCALE_SEGMENT_RE.match(segments[0]):
        segments = segments[1:]
    if len(segments) == 2 and segments[0].lower() == 'track':
        return _bare(segments[1])
    return ''


def _bare(candidate: str) -> str:
    candidate = candidate.split('?')[0].split('#')[0].strip()
    return candidate if SPOTIFY_TRACK_ID_RE.match(candidate) else ''

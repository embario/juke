"""Feelings → sound. Maps emoji and short phrases to genre profiles for Spotify search.

Search uses ``genre:"…"`` (and sometimes ``year:``) filters instead of the feeling's literal
words, which only matched song titles ("late night" → five songs called "Late Night").
Everything here is deterministic so picks are testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Emoji → canonical feeling phrase (also used by station suggestions: 🌙 ≈ "late night").
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


@dataclass(frozen=True)
class Profile:
    genres: Tuple[str, ...]
    years: Optional[str] = None  # Spotify ``year:`` filter, e.g. "1974-1983"
    max_minutes: int = 12  # longer results are usually not songs (mixes, audiobooks)


LONG_FORM_MINUTES = 40  # ambient/drone/classical pieces run long


_LATE_NIGHT = Profile(('chillwave', 'downtempo', 'trip hop', 'neo soul', 'ambient', 'lo-fi'))
_MORNING = Profile(('acoustic', 'indie folk', 'bossa nova', 'soft rock', 'folk'))
_RAINY = Profile(('slowcore', 'lo-fi', 'indie folk', 'ambient', 'jazz'))
_DANCE = Profile(('house', 'nu disco', 'dance pop', 'funk', 'disco'))
_HYPE = Profile(('hip hop', 'trap', 'edm', 'electro house'))
_WORKOUT = Profile(('edm', 'drum and bass', 'hip hop', 'electro house'))
_CHILL = Profile(('chillhop', 'lo-fi', 'chillwave', 'downtempo', 'indie pop'))
_CALM = Profile(('ambient', 'new age', 'neo-classical', 'drone'), max_minutes=LONG_FORM_MINUTES)
_FOCUS = Profile(('lo-fi', 'ambient', 'post-rock', 'neo-classical', 'minimal techno'), max_minutes=LONG_FORM_MINUTES)
_LOVE = Profile(('r&b', 'neo soul', 'soul', 'quiet storm'))
_SAD = Profile(('sadcore', 'singer-songwriter', 'indie folk', 'slowcore'))
_HAPPY = Profile(('funk', 'soul', 'indie pop', 'motown', 'reggae'))
_COZY = Profile(('indie folk', 'chamber folk', 'jazz', 'acoustic'))
_DREAMY = Profile(('dream pop', 'shoegaze', 'chillwave'))

PROFILES: Dict[str, Profile] = {
    'late night': _LATE_NIGHT, 'night': _LATE_NIGHT, 'midnight': _LATE_NIGHT,
    'slow morning': _MORNING, 'morning': _MORNING, 'sunrise': _MORNING, 'coffee': _MORNING,
    'rainy day': _RAINY, 'rain': _RAINY, 'rainy': _RAINY,
    'dance': _DANCE, 'party': Profile(('dance pop', 'hip hop', 'house', 'reggaeton')),
    'disco': Profile(('disco', 'funk', 'nu disco'), years='1974-1983'),
    'hype': _HYPE, 'energy': _HYPE, 'running': _WORKOUT, 'workout': _WORKOUT,
    'road trip': Profile(('classic rock', 'indie rock', 'heartland rock', 'country rock')),
    'chill': _CHILL, 'calm': _CALM, 'sleep': Profile(('ambient', 'sleep', 'drone', 'neo-classical'), max_minutes=LONG_FORM_MINUTES),
    'focus': _FOCUS, 'study': _FOCUS, 'love': _LOVE, 'romantic': _LOVE,
    'heartbreak': _SAD, 'sad': _SAD, 'bittersweet': Profile(('indie folk', 'dream pop', 'slowcore')),
    'happy': _HAPPY, 'feel good': _HAPPY, 'sunny': _HAPPY, 'summer': Profile(('indie pop', 'reggae', 'funk', 'surf rock')),
    'beach': Profile(('surf rock', 'reggae', 'tropical house', 'bossa nova')),
    'tropical': Profile(('tropical house', 'reggae', 'dancehall', 'bossa nova')),
    'rock': Profile(('rock', 'alternative rock', 'hard rock', 'classic rock')),
    'guitar': Profile(('blues rock', 'indie rock', 'fingerstyle', 'surf rock')),
    'piano': Profile(('neo-classical', 'jazz piano', 'classical piano'), max_minutes=LONG_FORM_MINUTES),
    'jazz': Profile(('jazz', 'cool jazz', 'bebop', 'nu jazz')),
    'strings': Profile(('classical', 'chamber pop', 'neo-classical'), max_minutes=LONG_FORM_MINUTES),
    'winter': _COZY, 'autumn': _COZY, 'cozy': _COZY, 'spring': Profile(('indie pop', 'folk', 'acoustic')),
    'ocean': Profile(('ambient', 'dream pop', 'surf rock')), 'dreamy': _DREAMY,
    'dinner': Profile(('jazz', 'bossa nova', 'soul', 'lounge')), 'holiday': Profile(('christmas',)),
    'discover': Profile(('indie', 'alternative', 'art pop')),
}
DEFAULT_FEELINGS = ('chill',)
_WORD = re.compile(r'[\w&\'-]+', re.UNICODE)
# Audiobook-style titles ("Chapter 85 - …", "Kapitel 3", "Capítulo 2"). "Part 2"/"Teil 2" are
# common song titles, so those only count together with a long duration (see looks_like_music).
_AUDIOBOOK = re.compile(r'^(chapter|kapitel|chapitre|capítulo|capitolo|hoofdstuk)\s+\d+|\bchapter\s+\d+', re.IGNORECASE)
_LONG_PART = re.compile(r'^(part|teil|partie|parte)\s+\d+', re.IGNORECASE)
LONG_PART_MS = 8 * 60_000
MIN_DURATION_MS = 60_000
MAX_DURATION_MS = 12 * 60_000


def normalize(value: str) -> str:
    return (value or '').strip().replace('️', '').casefold()


def feeling_keyword(feeling: str) -> str:
    """Canonical phrase for a feeling: emoji → phrase; text is returned as typed."""
    feeling = (feeling or '').strip()
    return FEELING_KEYWORDS.get(feeling) or FEELING_KEYWORDS.get(feeling.replace('️', '')) or feeling


def profile_for(feeling: str) -> Optional[Profile]:
    phrase = normalize(feeling_keyword(feeling))
    if phrase in PROFILES:
        return PROFILES[phrase]
    # "rainy sunday" → rainy; longest known phrase contained in the text wins.
    # Free text containing a known phrase as whole words ("rainy sunday" → rainy, "late night
    # drive" → late night) borrows that profile; the longest known phrase wins so "late night"
    # beats "night". Substrings inside other words don't count ("drainy" ≠ "rainy").
    for known in sorted(PROFILES, key=len, reverse=True):
        if re.search(rf'\b{re.escape(known)}\b', phrase):
            return PROFILES[known]
    return None


def _quote(genre: str) -> str:
    return f'genre:"{genre}"' if ' ' in genre or '-' in genre or '&' in genre else f'genre:{genre}'


def search_queries(feelings: Sequence[str], *, extra_genres: Iterable[str] = ()) -> List[Tuple[str, str]]:
    """Ordered (query, kind) pairs: genre filters round-robin across feelings, then free text.

    ``kind`` is ``genre`` for filter queries and ``text`` for unknown phrases searched as typed
    (their literal-title matches are filtered out later).
    """
    per_feeling: List[List[Tuple[str, str]]] = []
    for feeling in feelings:
        profile = profile_for(feeling)
        if profile is not None:
            year = f' year:{profile.years}' if profile.years else ''
            per_feeling.append([(_quote(genre) + year, 'genre') for genre in profile.genres])
        else:
            phrase = feeling_keyword(feeling).strip()
            if phrase:
                per_feeling.append([(_quote(phrase.casefold()), 'genre'), (phrase, 'text')])
    if extra_genres:
        per_feeling.append([(_quote(genre), 'genre') for genre in extra_genres])
    queries: List[Tuple[str, str]] = []
    for row in range(max((len(items) for items in per_feeling), default=0)):
        for items in per_feeling:
            if row < len(items):
                queries.append(items[row])
    return list(dict.fromkeys(queries))


def feeling_genres(feelings: Sequence[str]) -> set:
    genres = set()
    for feeling in feelings:
        profile = profile_for(feeling)
        if profile is not None:
            genres.update(profile.genres)
        else:
            genres.add(normalize(feeling_keyword(feeling)))
    return {genre for genre in genres if genre}


def genre_affinity(artist_genres: Iterable[str], wanted: set) -> int:
    """How many wanted genres an artist's Spotify genres touch (substring either way)."""
    genres = [normalize(genre) for genre in artist_genres]
    return sum(1 for want in wanted if any(want in genre or genre in want for genre in genres if genre))


def feeling_words(feelings: Sequence[str]) -> List[str]:
    words = []
    for feeling in feelings:
        phrase = normalize(feeling_keyword(feeling))
        if phrase:
            words.append(phrase)
            words.extend(word for word in _WORD.findall(phrase) if len(word) >= 4)
    return list(dict.fromkeys(words))


def literal_title_match(track: Dict, feelings: Sequence[str]) -> bool:
    title = normalize(track.get('title') or '')
    return any(re.search(rf'\b{re.escape(word)}\b', title) for word in feeling_words(feelings))


def max_duration_ms(feelings: Sequence[str]) -> int:
    """Longest acceptable result for these feelings (calm/sleep/focus allow long pieces)."""
    minutes = [profile.max_minutes for profile in (profile_for(feeling) for feeling in feelings) if profile]
    return max(minutes, default=MAX_DURATION_MS // 60_000) * 60_000


def looks_like_music(track: Dict, *, max_duration_ms: int = MAX_DURATION_MS) -> bool:
    """Drop audiobook chapters and other non-song results genre search sometimes returns."""
    duration = int(track.get('durationMs') or 0)
    if duration and not MIN_DURATION_MS <= duration <= max_duration_ms:
        return False
    title = track.get('title') or ''
    if _LONG_PART.search(title) and duration > LONG_PART_MS:
        return False
    return not _AUDIOBOOK.search(title)

"""Conservative metadata checks: compatible names are corroboration, never audio proof."""

import re
import unicodedata

VERSION = re.compile(
    r'\b(remaster(?:ed)?|master(?:ed)?|live|remix|acoustic|instrumental|edit|demo|karaoke|mono|stereo|version|mix)\b', re.I
)


def normalized(value):
    value = str(value or '').casefold().replace('ı', 'i').replace('œ', 'oe').replace('æ', 'ae')
    return ''.join(c for c in unicodedata.normalize('NFKD', value) if c.isalnum())


def version_context(title):
    chunks = re.findall(r'\([^)]*\)|\[[^]]*\]|\s[-–—]\s.*$', title)
    context = ' '.join(c for c in chunks if VERSION.search(c))
    tags = {'master' if x.lower() in {'remaster', 'remastered', 'master', 'mastered'} else x.lower() for x in VERSION.findall(context)}
    return tags, set(re.findall(r'\b(?:19|20)\d{2}\b', context))


def metadata_verdict(reference, candidate):
    if not reference or not reference.title or not reference.artist_credit or not candidate.name or not candidate.artists:
        return 'missing_recording_metadata'
    if version_context(reference.title) != version_context(candidate.name):
        return 'version_context_disagrees'
    if normalized(reference.title) != normalized(candidate.name):
        return 'recording_title_disagrees'
    # Only the complete ordered credit is accepted. Do not accept a matching individual contributor.
    names = [normalized(a) for a in candidate.artists]
    # A conjunction is allowed only BETWEEN complete artist names, never stripped from a name.
    credit_pattern = r'(?:and)?'.join(re.escape(n) for n in names)
    if not all(names) or not re.fullmatch(credit_pattern, normalized(reference.artist_credit)):
        return 'recording_artist_disagrees'
    if reference.duration_ms is not None and candidate.duration_ms is not None:
        if abs(reference.duration_ms - candidate.duration_ms) > 2000:
            return 'recording_duration_disagrees'
    return 'metadata_consistent'

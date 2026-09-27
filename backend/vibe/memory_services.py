"""Jev boundary and traceable memory signals; no substitute classifier is used."""
from collections import defaultdict

import requests
from django.conf import settings


def unique_tags(values):
    seen, result = set(), []
    for value in values:
        value = value.strip()
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result


def classify_memory(draft):
    unavailable = {'status': 'unavailable', 'provider': 'jev'}
    endpoint = getattr(settings, 'JEV_CLASSIFICATION_URL', '')
    if not endpoint:
        return [], unavailable
    payload = {key: draft.get(key) for key in ('title', 'body', 'place', 'people', 'songs')}
    # Only deliberately submitted memory content; never private chat history or media bytes.
    headers = {'Accept': 'application/json'}
    api_key = getattr(settings, 'JEV_API_KEY', '')
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    try:
        response = requests.post(endpoint, json={'memory': payload}, headers=headers,
                                 timeout=getattr(settings, 'JEV_TIMEOUT_SECONDS', 8), allow_redirects=False)
        response.raise_for_status()
        data = response.json()
        tags = data.get('tags')
        if not isinstance(tags, list) or len(tags) > 50 or any(not isinstance(tag, str) or not 1 <= len(tag.strip()) <= 60 for tag in tags):
            return [], unavailable
        return unique_tags(tags), {'status': 'complete', 'provider': 'jev'}
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        return [], unavailable


def recommendation_signals(memory):
    """Versioned input boundary for recommendation jobs; explicit user edits win."""
    return {'version': 1, 'memoryID': str(memory.id), 'profileID': str(memory.profile_id),
            'occurredAt': memory.occurred_at.isoformat(), 'tags': memory.tags,
            'songs': [{'provider': song['provider'], 'providerTrackID': song.get('providerTrackID', ''),
                       'title': song['title'], 'artist': song.get('artist', '')} for song in memory.songs]}


def memory_recommendation_context(user):
    from vibe.memory_models import MusicMemory
    return list(MusicMemory.objects.filter(profile__user=user).values_list('recommendation_signals', flat=True)[:200])


def memory_insights(memories):
    groups = defaultdict(list)
    for memory in memories:
        items = [('person', name) for name in memory.people]
        items += [('place', memory.place)] if memory.place else []
        items += [('song', f"{song['title']} — {song.get('artist', '')}".strip(' —')) for song in memory.songs]
        items += [('tag', tag) for tag in memory.tags]
        if memory.media.exists():
            items += [('photo' if item.kind == 'photo' else 'video', item.filename) for item in memory.media.all()]
        for kind, label in set(items):
            groups[(kind, label)].append(str(memory.id))
    connections = [{'kind': kind, 'label': label, 'count': len(ids), 'memoryIDs': ids}
                   for (kind, label), ids in groups.items()]
    connections.sort(key=lambda item: (-item['count'], item['kind'], item['label']))
    repeated = next((item for item in connections if item['count'] > 1 and item['kind'] in {'person', 'place', 'song'}), None)
    if repeated:
        prompt = f"What is another moment that {repeated['label']} brings back—and who was there with you?"
    elif memories and memories[0].place:
        prompt = f"Which song takes you back to {memories[0].place}, and what do you remember seeing around you?"
    else:
        prompt = 'What song brings someone you miss to mind, and which moment would you keep with it?'
    return {'prompt': prompt, 'connections': connections[:100], 'memoryCount': len(memories)}

"""Authenticated, user-scoped memory APIs for the native Vibe clients."""
from io import BytesIO
from pathlib import Path

from django.db import transaction
from django.db.models import Prefetch
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from juke_auth.models import MusicProfile
from vibe.authentication import VIBE_AUTHENTICATION_CLASSES
from vibe.memory_models import MemoryMedia, MemoryTag, MusicMemory
from vibe.memory_serializers import MemoryDraftSerializer
from vibe.memory_services import classify_memory, memory_insights, memory_recommendation_context, recommendation_signals, unique_tags
from vibe.views import VibeUserThrottle


class MemoryAPIView(APIView):
    authentication_classes = VIBE_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]
    throttle_classes = [VibeUserThrottle]


def media_payload(media):
    return {'id': str(media.id), 'kind': media.kind, 'filename': media.filename,
            'contentType': media.content_type, 'size': media.size,
            'url': f'/api/v1/vibe/memory-media/{media.id}/content/'}


def memory_payload(memory):
    return {'id': str(memory.id), 'profileID': str(memory.profile_id), 'title': memory.title,
            'body': memory.body, 'occurredAt': memory.occurred_at.isoformat(), 'createdAt': memory.created_at.isoformat(),
            'updatedAt': memory.updated_at.isoformat(), 'place': memory.place, 'people': memory.people,
            'songs': memory.songs, 'tags': memory.tags, 'generatedTags': memory.generated_tags,
            'excludedTags': memory.excluded_tags, 'classification': memory.classification,
            'media': [media_payload(item) for item in memory.media.all()]}


def user_memories(user):
    return MusicMemory.objects.filter(profile__user=user).prefetch_related(
        Prefetch('media', queryset=MemoryMedia.objects.defer('content').order_by('created_at')))


def save_memory(request, memory=None):
    serializer = MemoryDraftSerializer(data=request.data, partial=memory is not None)
    serializer.is_valid(raise_exception=True)
    values = serializer.validated_data
    if memory is None:
        draft = values
    else:
        draft = {**memory_payload(memory), **values}
        draft.setdefault('mediaIDs', list(memory.media.values_list('id', flat=True)))
    if not any(draft.get(key) for key in ('body', 'songs', 'mediaIDs')):
        raise serializers.ValidationError('Add a song, a photo or video, or a few words to save a memory.')
    ids = list(dict.fromkeys(draft.get('mediaIDs', [])))
    # Classify before any memory/profile/tag is persisted. Tag-only changes retain the original classifier result.
    content_changed = memory is None or any(key in values for key in ('title', 'body', 'place', 'people', 'songs'))
    if content_changed:
        generated, classification = classify_memory(draft)
    else:
        generated, classification = memory.generated_tags, memory.classification
    exclusions = unique_tags(draft.get('excludedTags', []))
    if memory is not None and 'tags' in values:
        selected = {tag.casefold() for tag in values['tags']}
        exclusions = unique_tags(exclusions + [tag for tag in generated if tag.casefold() not in selected])
    blocked = {tag.casefold() for tag in exclusions}
    with transaction.atomic():
        media = list(MemoryMedia.objects.select_for_update().filter(user=request.user, id__in=ids))
        if len(media) != len(ids) or any(item.memory_id and (memory is None or item.memory_id != memory.id) for item in media):
            raise serializers.ValidationError({'mediaIDs': 'One or more attachments are unavailable.'})
        if memory is None:
            profile, _ = MusicProfile.objects.get_or_create(user=request.user)
            memory = MusicMemory(profile=profile)
        for api, attr in (('title', 'title'), ('body', 'body'), ('occurredAt', 'occurred_at'), ('place', 'place'),
                          ('people', 'people'), ('songs', 'songs')):
            if api in values:
                setattr(memory, attr, values[api])
        memory.generated_tags = generated
        memory.excluded_tags = exclusions
        memory.classification = classification
        memory.tags = unique_tags(draft.get('tags', []) + [tag for tag in generated if tag.casefold() not in blocked])
        for tag in values.get('tags', []):
            MemoryTag.objects.get_or_create(user=request.user, normalized=tag.casefold(), defaults={'label': tag})
        memory.recommendation_signals = recommendation_signals(memory)
        memory.save()
        memory.media.exclude(id__in=ids).delete()
        MemoryMedia.objects.filter(id__in=ids).update(memory=memory)
    # Refresh prefetch data after attachment replacement.
    return user_memories(request.user).get(pk=memory.pk)


class MemoryCollectionView(MemoryAPIView):
    def get(self, request):
        try:
            offset = max(0, int(request.query_params.get('offset', 0)))
            limit = min(100, max(1, int(request.query_params.get('limit', 50))))
        except ValueError:
            raise serializers.ValidationError('Invalid pagination parameters.')
        queryset = user_memories(request.user)
        count = queryset.count()
        memories = queryset[offset:offset + limit]
        return Response({'memories': [memory_payload(memory) for memory in memories], 'count': count,
                         'nextOffset': offset + limit if offset + limit < count else None})

    def post(self, request):
        return Response(memory_payload(save_memory(request)), status=status.HTTP_201_CREATED)


class MemoryDetailView(MemoryAPIView):
    def get(self, request, memory_id):
        return Response(memory_payload(get_object_or_404(user_memories(request.user), pk=memory_id)))

    def patch(self, request, memory_id):
        # Merge partial edits against the latest committed memory. This also keeps
        # classifier output and attachment membership consistent across devices.
        with transaction.atomic():
            memory = get_object_or_404(user_memories(request.user).select_for_update(), pk=memory_id)
            return Response(memory_payload(save_memory(request, memory)))

    def delete(self, request, memory_id):
        get_object_or_404(user_memories(request.user), pk=memory_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MemoryClassifyView(MemoryAPIView):
    def post(self, request):
        serializer = MemoryDraftSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tags, classification = classify_memory(serializer.validated_data)
        return Response({'tags': tags, 'classification': classification})


class MemoryTagsView(MemoryAPIView):
    def get(self, request):
        return Response({'tags': list(MemoryTag.objects.filter(user=request.user).values_list('label', flat=True))})


class MemoryInsightsView(MemoryAPIView):
    def get(self, request):
        queryset = user_memories(request.user)
        result = memory_insights(list(queryset[:500]))
        result['memoryCount'] = queryset.count()
        return Response(result)


class MemoryMediaUploadView(MemoryAPIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        uploaded = request.FILES.get('file')
        if not uploaded:
            raise serializers.ValidationError({'file': 'Choose a photo or video.'})
        if uploaded.size > 50 * 1024 * 1024:
            raise serializers.ValidationError({'file': 'Photos and videos must be 50 MB or smaller.'})
        content = uploaded.read()
        content_type = detect_media_type(content)
        if content_type is None:
            raise serializers.ValidationError({'file': 'Use JPEG, PNG, GIF, WebP, HEIC, MP4, or MOV media.'})
        media = MemoryMedia.objects.create(user=request.user, filename=Path(uploaded.name).name[:255],
                                          content_type=content_type, kind='photo' if content_type.startswith('image/') else 'video',
                                          content=content, size=len(content))
        return Response(media_payload(media), status=status.HTTP_201_CREATED)


def detect_media_type(content):
    if content.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if content.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if content.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if content.startswith(b'RIFF') and content[8:12] == b'WEBP':
        return 'image/webp'
    if len(content) >= 12 and content[4:8] == b'ftyp':
        brand = content[8:12]
        if brand in (b'heic', b'heix', b'hevc', b'hevx', b'mif1'):
            return 'image/heic'
        if brand == b'qt  ':
            return 'video/quicktime'
        if brand in (b'isom', b'iso2', b'mp41', b'mp42', b'avc1', b'M4V '):
            return 'video/mp4'
    return None


class MemoryMediaContentView(MemoryAPIView):
    def get(self, request, media_id):
        media = get_object_or_404(MemoryMedia.objects.filter(user=request.user), pk=media_id)
        response = FileResponse(BytesIO(bytes(media.content)), content_type=media.content_type, filename=media.filename)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    def delete(self, request, media_id):
        get_object_or_404(MemoryMedia.objects.filter(user=request.user, memory__isnull=True), pk=media_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MemoryRecommendationContextView(MemoryAPIView):
    def get(self, request):
        signals = memory_recommendation_context(request.user)
        songs = {}
        tags = {}
        for signal in signals:
            for song in signal.get('songs', []):
                key = (song['provider'], song['providerTrackID'])
                if not key[1]:
                    continue
                item = songs.setdefault(key, {**song, 'memoryIDs': [], 'weight': 0})
                if signal['memoryID'] not in item['memoryIDs']:
                    item['memoryIDs'].append(signal['memoryID'])
                    item['weight'] += 1
            for tag in signal.get('tags', []):
                item = tags.setdefault(tag.casefold(), {'tag': tag, 'memoryIDs': [], 'weight': 0})
                if signal['memoryID'] not in item['memoryIDs']:
                    item['memoryIDs'].append(signal['memoryID'])
                    item['weight'] += 1
        return Response({'version': 1, 'source': 'musicMemories', 'memoryCount': len(signals),
                         'songSeeds': sorted(songs.values(), key=lambda item: -item['weight']),
                         'tagSignals': sorted(tags.values(), key=lambda item: -item['weight'])})

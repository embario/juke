import math
from urllib.parse import urlparse

from rest_framework import serializers

from vibe.serializers import StrictSerializer


class MemorySongSerializer(StrictSerializer):
    id = serializers.UUIDField()
    provider = serializers.ChoiceField(choices=('spotify', 'appleMusic'))
    providerTrackID = serializers.CharField(max_length=300, allow_blank=True, required=False, default='')
    title = serializers.CharField(max_length=300)
    artist = serializers.CharField(max_length=300, allow_blank=True, required=False, default='')
    album = serializers.CharField(max_length=300, allow_blank=True, required=False, default='')
    artworkURL = serializers.URLField(max_length=2000, allow_blank=True, required=False, default='')
    deepLink = serializers.CharField(max_length=2000, allow_blank=True, required=False, default='')
    segmentStartSeconds = serializers.FloatField(min_value=0, max_value=604800, required=False, allow_null=True)
    segmentEndSeconds = serializers.FloatField(min_value=0, max_value=604800, required=False, allow_null=True)

    def validate(self, attrs):
        start, end = attrs.get('segmentStartSeconds'), attrs.get('segmentEndSeconds')
        if any(value is not None and not math.isfinite(value) for value in (start, end)):
            raise serializers.ValidationError('Segment times must be finite.')
        if end is not None and end <= (start or 0):
            raise serializers.ValidationError('The segment end must follow its start.')
        link = urlparse(attrs.get('deepLink', ''))
        allowed = {'open.spotify.com', 'music.apple.com', 'geo.music.apple.com'}
        if link.geturl() and not (link.scheme in {'spotify', 'music', 'musics'} or (link.scheme == 'https' and link.hostname in allowed)):
            raise serializers.ValidationError('Use a Spotify or Apple Music song link.')
        attrs['id'] = str(attrs['id'])
        return attrs


class MemoryDraftSerializer(StrictSerializer):
    title = serializers.CharField(max_length=200, allow_blank=True, required=False, default='')
    body = serializers.CharField(max_length=20000, allow_blank=True, required=False, default='')
    occurredAt = serializers.DateTimeField()
    place = serializers.CharField(max_length=200, allow_blank=True, required=False, default='')
    people = serializers.ListField(child=serializers.CharField(max_length=120), max_length=30, required=False, default=list)
    songs = MemorySongSerializer(many=True, max_length=30, required=False, default=list)
    mediaIDs = serializers.ListField(child=serializers.UUIDField(), max_length=20, required=False, default=list)
    tags = serializers.ListField(child=serializers.CharField(max_length=60), max_length=50, required=False, default=list)
    excludedTags = serializers.ListField(child=serializers.CharField(max_length=60), max_length=50, required=False, default=list)

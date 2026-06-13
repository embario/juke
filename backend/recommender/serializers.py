from __future__ import annotations

from urllib.parse import urlparse
from uuid import UUID

from rest_framework import serializers


MAX_IDENTITY_ITEMS = 100
SUPPORTED_IDENTITY_RESOURCES = {
    'spotify': 'track',
    'musicbrainz': 'recording',
    'listenbrainz': 'recording',
}


def normalize_identity_source_id(*, source: str, source_id: str) -> str:
    normalized = str(source_id or '').strip()
    if source == 'spotify':
        if normalized.startswith('spotify:track:'):
            normalized = normalized.removeprefix('spotify:track:')
        elif normalized.startswith(('https://open.spotify.com/', 'http://open.spotify.com/')):
            path_parts = [part for part in urlparse(normalized).path.split('/') if part]
            if len(path_parts) >= 2 and path_parts[0] == 'track':
                normalized = path_parts[1]
        if len(normalized) != 22 or not normalized.isalnum():
            raise serializers.ValidationError('Provide a valid Spotify track ID, URI, or URL.')
        return normalized

    try:
        return str(UUID(normalized))
    except (TypeError, ValueError, AttributeError) as exc:
        provider = 'MusicBrainz recording MBID' if source == 'musicbrainz' else 'ListenBrainz recording MSID'
        raise serializers.ValidationError(f'Provide a valid {provider}.') from exc


class RecommendationRequestSerializer(serializers.Serializer):
    artists = serializers.ListField(child=serializers.CharField(), required=False)
    albums = serializers.ListField(child=serializers.CharField(), required=False)
    tracks = serializers.ListField(child=serializers.CharField(), required=False)
    genres = serializers.ListField(child=serializers.CharField(), required=False)
    limit = serializers.IntegerField(min_value=1, max_value=50, default=10)
    resource_types = serializers.ListField(
        child=serializers.ChoiceField(choices=['artists', 'albums', 'tracks']),
        required=False,
    )

    def validate(self, attrs):
        if not any(attrs.get(key) for key in ['artists', 'albums', 'tracks', 'genres']):
            raise serializers.ValidationError('Provide at least one artist, album, track, or genre.')
        return attrs


class MLCoreIdentityItemSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=['spotify', 'musicbrainz', 'listenbrainz'])
    resource_type = serializers.ChoiceField(choices=['track', 'recording'])
    source_id = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate(self, attrs):
        source = attrs['source']
        resource_type = attrs['resource_type']
        if SUPPORTED_IDENTITY_RESOURCES[source] != resource_type:
            raise serializers.ValidationError(
                f'Unsupported identity pair: {source}:{resource_type}.',
            )
        attrs['source_id'] = normalize_identity_source_id(source=source, source_id=attrs['source_id'])
        return attrs


class MLCoreRecommendationRequestSerializer(serializers.Serializer):
    ranker = serializers.ChoiceField(choices=['cooccurrence', 'metadata'], default='cooccurrence')
    seed_items = MLCoreIdentityItemSerializer(many=True)
    exclude_items = MLCoreIdentityItemSerializer(many=True, required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=10)

    def validate_seed_items(self, value):
        if not value:
            raise serializers.ValidationError('Provide at least one seed item.')
        if len(value) > MAX_IDENTITY_ITEMS:
            raise serializers.ValidationError(f'Provide no more than {MAX_IDENTITY_ITEMS} seed items.')
        return self._deduplicate(value)

    def validate_exclude_items(self, value):
        if len(value) > MAX_IDENTITY_ITEMS:
            raise serializers.ValidationError(f'Provide no more than {MAX_IDENTITY_ITEMS} exclusion items.')
        return self._deduplicate(value)

    @staticmethod
    def _deduplicate(items):
        unique = {}
        for item in items:
            key = (item['source'], item['resource_type'], item['source_id'])
            unique.setdefault(key, item)
        return list(unique.values())


class RecommendationResultSerializer(serializers.Serializer):
    name = serializers.CharField()
    likeness = serializers.FloatField()
    extra = serializers.DictField(child=serializers.CharField(), required=False)


class RecommendationResponseSerializer(serializers.Serializer):
    artists = RecommendationResultSerializer(many=True, required=False)
    albums = RecommendationResultSerializer(many=True, required=False)
    tracks = RecommendationResultSerializer(many=True, required=False)
    model_version = serializers.CharField()
    generated_at = serializers.DateTimeField()


class MLCoreRecommendationResultSerializer(serializers.Serializer):
    canonical_item_id = serializers.UUIDField()
    score = serializers.FloatField()
    components = serializers.DictField(child=serializers.FloatField(), required=False)


class MLCoreUnresolvedItemSerializer(serializers.Serializer):
    source = serializers.CharField()
    resource_type = serializers.CharField()
    source_id = serializers.CharField(allow_blank=True)
    canonical_item_id = serializers.UUIDField(allow_null=True, required=False)
    status = serializers.CharField()
    canonical_key = serializers.CharField(allow_blank=True, required=False)
    item_type = serializers.CharField(allow_blank=True, required=False)


class MLCoreVersionSerializer(serializers.Serializer):
    api_version = serializers.CharField()
    model_version = serializers.CharField()
    training_run_id = serializers.UUIDField(allow_null=True)
    training_version = serializers.CharField(allow_blank=True)
    identity_graph_run_id = serializers.UUIDField(allow_null=True)
    identity_graph_version = serializers.CharField(allow_blank=True)
    identity_graph_algorithm_version = serializers.CharField(allow_blank=True)


class MLCoreRecommendationResponseSerializer(serializers.Serializer):
    items = MLCoreRecommendationResultSerializer(many=True)
    ranker = serializers.CharField()
    seed_count = serializers.IntegerField()
    requested_seed_count = serializers.IntegerField()
    resolved_seed_count = serializers.IntegerField()
    unresolved_seed_items = MLCoreUnresolvedItemSerializer(many=True, required=False)
    unresolved_exclude_items = MLCoreUnresolvedItemSerializer(many=True, required=False)
    request_id = serializers.UUIDField()
    versions = MLCoreVersionSerializer()
    generated_at = serializers.DateTimeField()

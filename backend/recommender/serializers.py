from __future__ import annotations

from rest_framework import serializers


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

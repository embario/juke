from __future__ import annotations

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from recommender.serializers import (
    RecommendationRequestSerializer,
    RecommendationResponseSerializer,
)
from recommender.services import client, taste


class RecommendationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = RecommendationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        profile_payload = taste.mixed_payload(
            artists=validated.get('artists'),
            albums=validated.get('albums'),
            tracks=validated.get('tracks'),
            genres=validated.get('genres'),
        )
        profile_payload['limit'] = validated.get('limit', 10)
        if validated.get('resource_types'):
            profile_payload['resource_types'] = validated['resource_types']

        engine_response = client.fetch_recommendations(profile_payload)

        normalized = self._normalize_response(engine_response)
        response_serializer = RecommendationResponseSerializer(data=normalized)
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def _normalize_response(self, engine_response):
        generated = engine_response.get('generated_at') or timezone.now().isoformat()
        return {
            'artists': engine_response.get('artists', []),
            'albums': engine_response.get('albums', []),
            'tracks': engine_response.get('tracks', []),
            'model_version': engine_response.get('model_version', 'unknown'),
            'generated_at': generated,
        }

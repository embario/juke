from __future__ import annotations

import logging
from uuid import uuid4

import requests
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from recommender.serializers import (
    MLCoreRecommendationRequestSerializer,
    MLCoreRecommendationResponseSerializer,
    RecommendationRequestSerializer,
    RecommendationResponseSerializer,
)
from recommender.services import client, taste


logger = logging.getLogger(__name__)


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


class MLCoreRecommendationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MLCoreRecommendationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        ranker = validated.get('ranker') or 'cooccurrence'
        payload = {
            'seed_items': validated['seed_items'],
            'exclude_items': validated.get('exclude_items', []),
            'limit': validated.get('limit', 10),
            'request_id': str(uuid4()),
        }

        try:
            engine_response = client.fetch_identity_recommendations(ranker, payload)
        except requests.RequestException:
            return Response(
                {'detail': 'recommendations unavailable'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            normalized = self._normalize_response(engine_response, ranker=ranker, request_id=payload['request_id'])
            response_serializer = MLCoreRecommendationResponseSerializer(data=normalized)
            response_serializer.is_valid(raise_exception=True)
        except (AttributeError, TypeError, ValidationError):
            logger.exception(
                'MLCore returned an invalid recommendation response',
                extra={'request_id': payload['request_id'], 'ranker': ranker},
            )
            return Response(
                {'detail': 'recommendations unavailable'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def _normalize_response(self, engine_response, *, ranker, request_id):
        generated = engine_response.get('generated_at') or timezone.now().isoformat()
        items = []
        for item in engine_response.get('items', []):
            normalized_item = dict(item)
            if 'canonical_item_id' not in normalized_item and normalized_item.get('juke_id'):
                normalized_item['canonical_item_id'] = normalized_item['juke_id']
            normalized_item.pop('juke_id', None)
            items.append(normalized_item)
        return {
            'items': items,
            'ranker': engine_response.get('ranker', ranker),
            'seed_count': engine_response.get('seed_count', 0),
            'requested_seed_count': engine_response.get('requested_seed_count', 0),
            'resolved_seed_count': engine_response.get('resolved_seed_count', 0),
            'unresolved_seed_items': engine_response.get('unresolved_seed_items', []),
            'unresolved_exclude_items': engine_response.get('unresolved_exclude_items', []),
            'request_id': engine_response.get('request_id', request_id),
            'versions': engine_response.get('versions', {}),
            'generated_at': generated,
        }

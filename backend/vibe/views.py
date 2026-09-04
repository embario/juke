import base64
import hashlib
import hmac
from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from vibe.authentication import VIBE_AUTHENTICATION_CLASSES
from vibe.models import (
    VibeAccountCapability,
    VibeAuthorizationCode,
    VibeEncryptedChange,
    VibeEncryptedRecord,
)
from vibe.serializers import (
    EncryptedVibeEnvelopeSerializer,
    VibeAuthorizeSerializer,
    VibeChatSerializer,
    VibeExchangeSerializer,
    RemoteMetadataPromptSerializer,
)
from vibe.services import (
    VibeChatUnavailable,
    generate_chat_response,
    issue_authorization_code,
    sha256_hex,
)


APPLE_REFERENCE_DATE = datetime(2001, 1, 1, tzinfo=datetime_timezone.utc)


class VibeExchangeThrottle(AnonRateThrottle):
    scope = 'vibe_auth_exchange'


class VibeUserThrottle(UserRateThrottle):
    scope = 'vibe_user'


def _capability(user):
    capability, _ = VibeAccountCapability.objects.get_or_create(user=user)
    return capability


def _display_name(user):
    profile = getattr(user, 'music_profile', None)
    display_name = ''
    if profile:
        display_name = profile.display_name or profile.name or ''
    return display_name or user.get_full_name() or user.username


def _account_payload(user):
    return {
        'id': str(user.pk),
        'displayName': _display_name(user),
        'email': user.email or None,
        'cloudAIEnabled': _capability(user).cloud_ai_enabled,
    }


class VibeAuthorizeView(APIView):
    authentication_classes = VIBE_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]
    throttle_classes = [VibeUserThrottle]

    def post(self, request):
        serializer = VibeAuthorizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        allowed = settings.VIBE_OAUTH_CLIENTS.get(data['client_id'])
        if not allowed or data['redirect_uri'] not in allowed:
            return Response({'detail': 'Unknown client or redirect URI.'}, status=status.HTTP_400_BAD_REQUEST)
        _, redirect_to = issue_authorization_code(
            user=request.user,
            client_id=data['client_id'],
            redirect_uri=data['redirect_uri'],
            state=data['state'],
            code_challenge=data['code_challenge'],
        )
        return Response({'redirect_to': redirect_to}, status=status.HTTP_200_OK)


class VibeExchangeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [VibeExchangeThrottle]

    def post(self, request):
        serializer = VibeExchangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            auth_code = (
                VibeAuthorizationCode.objects.select_for_update()
                .select_related('user')
                .filter(code_digest=sha256_hex(data['code']))
                .first()
            )
            if (
                auth_code is None
                or auth_code.consumed_at is not None
                or auth_code.expires_at <= timezone.now()
                or not hmac.compare_digest(auth_code.redirect_uri, data['redirect_uri'])
            ):
                return Response({'detail': 'Invalid or expired authorization code.'}, status=status.HTTP_400_BAD_REQUEST)

            verifier_digest = hashlib.sha256(data['code_verifier'].encode('ascii')).digest()
            computed_challenge = base64.urlsafe_b64encode(verifier_digest).rstrip(b'=').decode('ascii')
            if not hmac.compare_digest(auth_code.code_challenge, computed_challenge):
                return Response({'detail': 'Invalid or expired authorization code.'}, status=status.HTTP_400_BAD_REQUEST)

            auth_code.consumed_at = timezone.now()
            auth_code.save(update_fields=('consumed_at',))
            user = auth_code.user
            token, _ = Token.objects.get_or_create(user=user)

        return Response(
            {
                'account': _account_payload(user),
                'accessToken': token.key,
                'authenticatedAt': (timezone.now() - APPLE_REFERENCE_DATE).total_seconds(),
            },
            status=status.HTTP_200_OK,
        )


class VibeOpeningQuestionView(APIView):
    authentication_classes = VIBE_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]
    throttle_classes = [VibeUserThrottle]

    def post(self, request):
        serializer = RemoteMetadataPromptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current = serializer.validated_data.get('currentTrack')
        recent = serializer.validated_data.get('recentlyHeardMusic', [])
        signals = serializer.validated_data.get('conversationSignals', [])
        if current:
            question = f'What did you notice in {current} that you might have missed before?'
        elif signals:
            question = 'What connection in your listening feels most worth following right now?'
        elif recent:
            question = 'What thread connects the music you have been returning to lately?'
        else:
            question = 'What has music made room for in you today?'
        return Response({'question': question})


class VibeEncryptedChatRecordView(APIView):
    authentication_classes = VIBE_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]
    throttle_classes = [VibeUserThrottle]

    def put(self, request, record_id):
        serializer = EncryptedVibeEnvelopeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data['recordID'] != record_id or data['accountID'] != str(request.user.pk):
            return Response({'detail': 'Record identity does not match the authenticated account.'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            record = (
                VibeEncryptedRecord.objects.select_for_update()
                .filter(user=request.user, record_id=record_id)
                .first()
            )
            incoming = {
                'kind': data['kind'],
                'ciphertext': data['ciphertext'],
                'client_modified_at': data['modifiedAt'],
                'encryption_version': data['encryptionVersion'],
            }
            changed = record is None
            if record is None:
                record = VibeEncryptedRecord.objects.create(user=request.user, record_id=record_id, **incoming)
            else:
                if incoming['client_modified_at'] < record.client_modified_at:
                    return Response(
                        {'detail': 'A newer encrypted record already exists.'},
                        status=status.HTTP_409_CONFLICT,
                    )
                changed = any(
                    (
                        record.kind != incoming['kind'],
                        bytes(record.ciphertext) != incoming['ciphertext'],
                        record.client_modified_at != incoming['client_modified_at'],
                        record.encryption_version != incoming['encryption_version'],
                    )
                )
                if changed and incoming['client_modified_at'] == record.client_modified_at:
                    return Response(
                        {'detail': 'Conflicting encrypted records have the same modification time.'},
                        status=status.HTTP_409_CONFLICT,
                    )
                if changed:
                    for field, value in incoming.items():
                        setattr(record, field, value)
                    record.save(update_fields=(*incoming.keys(), 'modified_at'))
            if changed:
                VibeEncryptedChange.objects.create(record=record)
        return Response(status=status.HTTP_201_CREATED if changed else status.HTTP_200_OK)


class VibeEncryptedChatChangesView(APIView):
    authentication_classes = VIBE_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]
    throttle_classes = [VibeUserThrottle]
    page_size = 200

    def get(self, request):
        raw_cursor = request.query_params.get('cursor')
        if raw_cursor in (None, ''):
            cursor = 0
        else:
            try:
                cursor = int(raw_cursor)
            except (TypeError, ValueError):
                return Response({'detail': 'Cursor must be a non-negative integer.'}, status=status.HTTP_400_BAD_REQUEST)
            if cursor < 0:
                return Response({'detail': 'Cursor must be a non-negative integer.'}, status=status.HTTP_400_BAD_REQUEST)

        changes = list(
            VibeEncryptedChange.objects.filter(
                record__user=request.user,
                pk__gt=cursor,
            ).select_related('record').order_by('pk')[: self.page_size]
        )
        by_record = {}
        for change in changes:
            by_record[change.record_id] = change.record
        next_cursor = str(changes[-1].pk) if changes else (str(cursor) if raw_cursor is not None else None)
        return Response(
            {
                'envelopes': [
                    EncryptedVibeEnvelopeSerializer.represent_record(record)
                    for record in by_record.values()
                ],
                'cursor': next_cursor,
            }
        )


class VibeChatView(APIView):
    authentication_classes = VIBE_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]
    throttle_classes = [VibeUserThrottle]

    def post(self, request):
        if not _capability(request.user).cloud_ai_enabled:
            return Response({'detail': 'Cloud AI is not enabled for this account.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = VibeChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reply = generate_chat_response(
                message=serializer.validated_data['message'],
                current_track=serializer.validated_data.get('currentTrack'),
                listener_name=_display_name(request.user),
            )
        except VibeChatUnavailable as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'reply': reply})


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'status': 'ok'})

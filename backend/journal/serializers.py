import base64
import binascii
from datetime import datetime, timedelta, timezone as datetime_timezone

from rest_framework import serializers

from journal.models import JournalEncryptedRecord


APPLE_REFERENCE_DATE = datetime(2001, 1, 1, tzinfo=datetime_timezone.utc)
MAX_CIPHERTEXT_BYTES = 1024 * 1024


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError('Expected a JSON object.')
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError({key: ['Unknown field.'] for key in sorted(unknown)})
        return super().to_internal_value(data)


class JournalAuthorizeSerializer(StrictSerializer):
    client_id = serializers.CharField(max_length=64)
    redirect_uri = serializers.CharField(max_length=255)
    state = serializers.CharField(max_length=512)
    code_challenge = serializers.RegexField(r'^[A-Za-z0-9_-]{43,128}$')
    code_challenge_method = serializers.ChoiceField(choices=('S256',))


class JournalExchangeSerializer(StrictSerializer):
    code = serializers.RegexField(r'^[A-Za-z0-9_-]{32,256}$')
    code_verifier = serializers.RegexField(r'^[A-Za-z0-9._~-]{43,128}$')
    redirect_uri = serializers.CharField(max_length=255)


class RemoteMetadataPromptSerializer(StrictSerializer):
    recentlyHeardMusic = serializers.ListField(
        child=serializers.CharField(max_length=256),
        max_length=20,
        required=False,
        default=list,
    )
    currentTrack = serializers.CharField(max_length=256, required=False, allow_null=True, allow_blank=True)

class EncryptedJournalEnvelopeSerializer(StrictSerializer):
    recordID = serializers.UUIDField()
    accountID = serializers.CharField(max_length=64)
    kind = serializers.ChoiceField(choices=JournalEncryptedRecord.Kind.values)
    ciphertext = serializers.CharField(max_length=((MAX_CIPHERTEXT_BYTES + 2) // 3) * 4)
    modifiedAt = serializers.FloatField(min_value=-978307200, max_value=32503680000)
    encryptionVersion = serializers.IntegerField(min_value=1, max_value=32767)

    def validate_ciphertext(self, value):
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise serializers.ValidationError('Must be canonical base64 ciphertext.') from exc
        if not decoded:
            raise serializers.ValidationError('Ciphertext cannot be empty.')
        if len(decoded) > MAX_CIPHERTEXT_BYTES:
            raise serializers.ValidationError('Ciphertext exceeds the 1 MiB limit.')
        return decoded

    def validate_modifiedAt(self, value):
        try:
            return APPLE_REFERENCE_DATE + timedelta(seconds=value)
        except (OverflowError, ValueError) as exc:
            raise serializers.ValidationError('Invalid timestamp.') from exc

    @staticmethod
    def represent_record(record):
        return {
            'recordID': str(record.record_id),
            'accountID': str(record.user_id),
            'kind': record.kind,
            'ciphertext': base64.b64encode(bytes(record.ciphertext)).decode('ascii'),
            'modifiedAt': (record.client_modified_at - APPLE_REFERENCE_DATE).total_seconds(),
            'encryptionVersion': record.encryption_version,
        }


class JournalChatSerializer(StrictSerializer):
    message = serializers.CharField(max_length=4000, trim_whitespace=True)
    currentTrack = serializers.CharField(max_length=256, required=False, allow_null=True, allow_blank=True)

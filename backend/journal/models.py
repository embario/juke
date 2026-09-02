from django.conf import settings
from django.db import models


class JournalAccountCapability(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='journal_capability',
    )
    cloud_ai_enabled = models.BooleanField(default=False)
    modified_at = models.DateTimeField(auto_now=True)


class JournalAuthorizationCode(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    code_digest = models.CharField(max_length=64, unique=True)
    client_id = models.CharField(max_length=64)
    redirect_uri = models.CharField(max_length=255)
    state = models.CharField(max_length=512)
    code_challenge = models.CharField(max_length=128)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class JournalEncryptedRecord(models.Model):
    class Kind(models.TextChoices):
        AUTHORED_ENTRY = 'authoredEntry'
        LISTENING_REFLECTION = 'listeningReflection'
        CHAT_MESSAGE = 'chatMessage'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='journal_encrypted_records',
    )
    record_id = models.UUIDField()
    kind = models.CharField(max_length=32, choices=Kind.choices)
    ciphertext = models.BinaryField()
    client_modified_at = models.DateTimeField()
    encryption_version = models.PositiveSmallIntegerField()
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('user', 'record_id'),
                name='journal_record_user_record_unique',
            ),
        ]
        indexes = [models.Index(fields=('user', 'modified_at'))]


class JournalEncryptedChange(models.Model):
    record = models.ForeignKey(
        JournalEncryptedRecord,
        on_delete=models.CASCADE,
        related_name='changes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=('record', 'id'))]

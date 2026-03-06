import uuid

from django.db import models

ALLOWED_ENV_CHOICES = (
    ('production', 'Production'),
    ('research', 'Research'),
    ('both', 'Both'),
)


class CorpusManifest(models.Model):
    """
    Auditable manifest of licensed audio corpus rows. Every embedding/training
    job must resolve its input set through this table (arch §5.3).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=64)
    track_path = models.CharField(max_length=1024)
    license = models.CharField(max_length=128)
    license_url = models.URLField(max_length=512, null=True, blank=True)
    allowed_envs = models.CharField(max_length=16, choices=ALLOWED_ENV_CHOICES)
    checksum = models.CharField(max_length=128)
    duration_ms = models.IntegerField(null=True, blank=True)
    track = models.ForeignKey(
        'catalog.Track',
        to_field='juke_id',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='corpus_manifest_entries',
    )
    mbid_candidate = models.UUIDField(null=True, blank=True)
    fingerprint = models.CharField(max_length=256, null=True, blank=True)
    ingested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_corpus_manifest'
        unique_together = ('source', 'track_path', 'checksum')
        indexes = [
            models.Index(fields=['source']),
            models.Index(fields=['allowed_envs']),
        ]

    def __str__(self):
        return f"{self.source}:{self.track_path}"

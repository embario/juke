import uuid

from django.conf import settings
from django.db import models

ALLOWED_ENV_CHOICES = (
    ('production', 'Production'),
    ('research', 'Research'),
    ('both', 'Both'),
)

PROMOTION_STATUS_CHOICES = (
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('blocked', 'Blocked'),
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


class TrainingRun(models.Model):
    """One co-occurrence training invocation and its deterministic signature."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ranker_label = models.CharField(max_length=64)
    training_hash = models.CharField(max_length=64, db_index=True)
    baskets_processed = models.IntegerField()
    baskets_skipped = models.IntegerField()
    items_seen = models.IntegerField()
    pairs_written = models.IntegerField()
    source_row_count = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_training_run'
        indexes = [
            models.Index(fields=['ranker_label']),
            models.Index(fields=['training_hash']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ranker_label}:{self.training_hash[:12]}"


class ItemCoOccurrence(models.Model):
    """
    Symmetric pairwise co-occurrence counts + PMI scores for catalog items
    (arch §5.4). Keys are opaque juke_id UUIDs — track-level by convention
    in Phase 1, but the store is item-agnostic.

    Pairs are stored canonically with item_a_juke_id < item_b_juke_id
    (lexicographic) so each unordered pair has exactly one row. Readers
    must query both (a, ?) and (?, a) orientations.
    """
    item_a_juke_id = models.UUIDField()
    item_b_juke_id = models.UUIDField()
    co_count = models.IntegerField()
    pmi_score = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)
    training_run = models.ForeignKey(
        TrainingRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='cooccurrence_rows',
    )

    class Meta:
        db_table = 'mlcore_item_cooccurrence'
        unique_together = ('item_a_juke_id', 'item_b_juke_id')
        indexes = [
            models.Index(fields=['item_a_juke_id']),
            models.Index(fields=['item_b_juke_id']),
            models.Index(fields=['training_run']),
        ]

    def __str__(self):
        return f"co({self.item_a_juke_id}, {self.item_b_juke_id})={self.co_count}"


class ModelEvaluation(models.Model):
    """
    Offline evaluation metric store (arch §5.4). One row per
    (model, metric, dataset) measurement. Baselines without an
    mlcore_embedding_model row are identified via candidate_label.
    """
    model_id = models.UUIDField(null=True, blank=True, db_index=True)
    candidate_label = models.CharField(max_length=64, db_index=True)
    metric_name = models.CharField(max_length=64)
    metric_value = models.FloatField()
    dataset_hash = models.CharField(max_length=64, db_index=True)
    training_run = models.ForeignKey(
        TrainingRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='evaluations',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_model_evaluation'
        indexes = [
            models.Index(fields=['candidate_label', 'dataset_hash', 'metric_name']),
        ]

    def __str__(self):
        return f"{self.candidate_label}:{self.metric_name}={self.metric_value:.4f}"


class ModelPromotion(models.Model):
    """
    Promotion approval workflow record (arch decisions #7, #18).
    Captures gate check results, approver identity, and timestamp.
    A promotion cannot reach 'approved' unless all gates pass.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_id = models.UUIDField(null=True, blank=True)
    candidate_label = models.CharField(max_length=64)
    baseline_label = models.CharField(max_length=64)
    dataset_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=PROMOTION_STATUS_CHOICES, default='pending')
    gate_results = models.JSONField(default=dict)
    block_reason = models.TextField(blank=True, default='')
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='approved_promotions',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_model_promotion'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.candidate_label} vs {self.baseline_label} [{self.status}]"

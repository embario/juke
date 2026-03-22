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

INGESTION_STATUS_CHOICES = (
    ('pending', 'Pending'),
    ('running', 'Running'),
    ('succeeded', 'Succeeded'),
    ('failed', 'Failed'),
    ('skipped', 'Skipped'),
)

INGESTION_MODE_CHOICES = (
    ('full', 'Full'),
    ('incremental', 'Incremental'),
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


class SourceIngestionRun(models.Model):
    """Versioned execution record for external dataset imports."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=64)
    import_mode = models.CharField(max_length=16, choices=INGESTION_MODE_CHOICES)
    source_version = models.CharField(max_length=255)
    raw_path = models.CharField(max_length=1024)
    checksum = models.CharField(max_length=128)
    status = models.CharField(max_length=16, choices=INGESTION_STATUS_CHOICES, default='pending')
    source_row_count = models.IntegerField(default=0)
    imported_row_count = models.IntegerField(default=0)
    duplicate_row_count = models.IntegerField(default=0)
    canonicalized_row_count = models.IntegerField(default=0)
    unresolved_row_count = models.IntegerField(default=0)
    malformed_row_count = models.IntegerField(default=0)
    policy_classification = models.CharField(max_length=32, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mlcore_source_ingestion_run'
        indexes = [
            models.Index(fields=['source', 'import_mode'], name='mlcore_src_source_6e8952_idx'),
            models.Index(fields=['source', 'source_version'], name='mlcore_src_source_b153c1_idx'),
            models.Index(fields=['status'], name='mlcore_src_status_932106_idx'),
            models.Index(fields=['started_at'], name='mlcore_src_started_7c3252_idx'),
        ]
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.source}:{self.import_mode}:{self.source_version}"


class ListenBrainzRawListen(models.Model):
    """Immutable raw staging row for ListenBrainz listen events."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_run = models.ForeignKey(
        SourceIngestionRun,
        on_delete=models.CASCADE,
        related_name='listenbrainz_raw_rows',
    )
    source_event_signature = models.CharField(max_length=64, unique=True)
    source_user_id = models.CharField(max_length=64, db_index=True)
    played_at = models.DateTimeField(db_index=True)
    recording_mbid = models.UUIDField(null=True, blank=True, db_index=True)
    release_mbid = models.UUIDField(null=True, blank=True)
    recording_msid = models.CharField(max_length=255, blank=True, default='')
    release_msid = models.CharField(max_length=255, blank=True, default='')
    track_name = models.CharField(max_length=1024, blank=True, default='')
    artist_name = models.CharField(max_length=1024, blank=True, default='')
    release_name = models.CharField(max_length=1024, blank=True, default='')
    track_identifier_candidates = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    ingested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_listenbrainz_raw_listen'
        indexes = [
            models.Index(fields=['import_run'], name='mlcore_lis_import__6c1e6e_idx'),
            models.Index(fields=['source_user_id', 'played_at'], name='mlcore_lis_source__5069fc_idx'),
            models.Index(fields=['recording_mbid'], name='mlcore_lis_recordi_534bf5_idx'),
        ]
        ordering = ['played_at', 'id']

    def __str__(self):
        return f"{self.source_user_id}:{self.played_at.isoformat()}"


class NormalizedInteraction(models.Model):
    """Canonicalized interaction row for downstream ML training/evaluation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_run = models.ForeignKey(
        SourceIngestionRun,
        on_delete=models.CASCADE,
        related_name='normalized_interactions',
    )
    raw_listen = models.OneToOneField(
        ListenBrainzRawListen,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='normalized_interaction',
    )
    track = models.ForeignKey(
        'catalog.Track',
        to_field='juke_id',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='normalized_interactions',
    )
    source_id = models.CharField(max_length=64, db_index=True)
    source_version = models.CharField(max_length=255, db_index=True)
    source_event_signature = models.CharField(max_length=64, unique=True)
    source_user_id = models.CharField(max_length=64, db_index=True)
    played_at = models.DateTimeField(db_index=True)
    session_hint = models.CharField(max_length=128, db_index=True)
    track_identifier_candidates = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_normalized_interaction'
        indexes = [
            models.Index(fields=['source_id', 'source_version'], name='mlcore_nor_source__54a8d9_idx'),
            models.Index(fields=['source_user_id', 'played_at'], name='mlcore_nor_source__09767c_idx'),
            models.Index(fields=['track'], name='mlcore_nor_track_i_2555db_idx'),
            models.Index(fields=['import_run'], name='mlcore_nor_import__0fa0e0_idx'),
        ]
        ordering = ['played_at', 'id']

    def __str__(self):
        return f"{self.source_id}:{self.source_user_id}:{self.played_at.isoformat()}"


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

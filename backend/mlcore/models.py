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

TRAINING_BUCKET_STATUS_CHOICES = (
    ('pending', 'Pending'),
    ('running', 'Running'),
    ('succeeded', 'Succeeded'),
    ('failed', 'Failed'),
    ('assumed_succeeded', 'Assumed succeeded'),
)

LISTENBRAINZ_RESOLUTION_STATE_CHOICES = (
    (0, 'Unresolved'),
    (1, 'Resolved'),
)

CANONICAL_ITEM_TYPE_CHOICES = (
    ('recording_mbid', 'Recording MBID'),
    ('spotify_track', 'Spotify Track'),
    ('recording_msid', 'Recording MSID'),
    ('catalog_track', 'Catalog Track'),
)

CANONICAL_ITEM_ALIAS_STATUS_CHOICES = (
    ('active', 'Active'),
    ('retired', 'Retired'),
    ('conflict', 'Conflict'),
)


def _binary_to_hex(value):
    if isinstance(value, memoryview):
        value = value.tobytes()
    if value in (None, b''):
        return ''
    return bytes(value).hex()


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
    fingerprint = models.CharField(max_length=128, blank=True, default='')
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


class DatasetOrchestrationRun(models.Model):
    """Top-level execution record for one orchestrated dataset shard run."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=64)
    import_mode = models.CharField(max_length=16, choices=INGESTION_MODE_CHOICES, default='full')
    source_version = models.CharField(max_length=255)
    manifest_path = models.CharField(max_length=1024)
    orchestration_path = models.CharField(max_length=1024)
    output_root = models.CharField(max_length=1024)
    status = models.CharField(max_length=16, choices=INGESTION_STATUS_CHOICES, default='pending')
    shard_parallelism = models.IntegerField(default=1)
    max_shards_per_run = models.IntegerField(null=True, blank=True)
    shard_count = models.IntegerField(default=0)
    scheduled_shard_count = models.IntegerField(default=0)
    completed_shard_count = models.IntegerField(default=0)
    failed_shard_count = models.IntegerField(default=0)
    source_row_count = models.IntegerField(default=0)
    imported_row_count = models.IntegerField(default=0)
    duplicate_row_count = models.IntegerField(default=0)
    canonicalized_row_count = models.IntegerField(default=0)
    unresolved_row_count = models.IntegerField(default=0)
    malformed_row_count = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mlcore_dataset_orchestration_run'
        unique_together = ('provider', 'source_version', 'orchestration_path')
        indexes = [
            models.Index(fields=['provider', 'source_version'], name='mlcore_dor_provider_821c5f_idx'),
            models.Index(fields=['status'], name='mlcore_dor_status_6798d7_idx'),
            models.Index(fields=['started_at'], name='mlcore_dor_started_9dfd6a_idx'),
        ]
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.provider}:{self.source_version}:{self.status}"


class DatasetShardIngestionRun(models.Model):
    """Persistent shard-level execution record for orchestrated dataset imports."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    orchestration_run = models.ForeignKey(
        DatasetOrchestrationRun,
        on_delete=models.CASCADE,
        related_name='shard_runs',
    )
    provider = models.CharField(max_length=64)
    import_mode = models.CharField(max_length=16, choices=INGESTION_MODE_CHOICES, default='full')
    source_version = models.CharField(max_length=255)
    shard_key = models.CharField(max_length=255)
    shard_path = models.CharField(max_length=1024)
    status = models.CharField(max_length=16, choices=INGESTION_STATUS_CHOICES, default='pending')
    task_id = models.CharField(max_length=255, blank=True, default='')
    source_ingestion_run = models.ForeignKey(
        SourceIngestionRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='dataset_shard_runs',
    )
    source_row_count = models.IntegerField(default=0)
    imported_row_count = models.IntegerField(default=0)
    duplicate_row_count = models.IntegerField(default=0)
    canonicalized_row_count = models.IntegerField(default=0)
    unresolved_row_count = models.IntegerField(default=0)
    malformed_row_count = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mlcore_dataset_shard_ingestion_run'
        unique_together = ('orchestration_run', 'shard_key')
        indexes = [
            models.Index(fields=['orchestration_run', 'status'], name='mlcore_dsi_orchest_0f7624_idx'),
            models.Index(fields=['provider', 'source_version'], name='mlcore_dsi_provider_6dc0a4_idx'),
            models.Index(fields=['status'], name='mlcore_dsi_status_d073af_idx'),
        ]
        ordering = ['shard_key', 'started_at']

    def __str__(self):
        return f"{self.provider}:{self.source_version}:{self.shard_key}:{self.status}"


class FullIngestionLease(models.Model):
    """Exclusive provider-level lease for long-running full dataset ingestions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.CharField(max_length=64, unique=True)
    holder_type = models.CharField(max_length=32, default='full_ingestion')
    holder_run_id = models.CharField(max_length=64, blank=True, default='')
    source_version = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=16, choices=INGESTION_STATUS_CHOICES, default='pending')
    metadata = models.JSONField(default=dict, blank=True)
    acquired_at = models.DateTimeField(auto_now_add=True)
    heartbeat_at = models.DateTimeField(auto_now=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mlcore_full_ingestion_lease'
        indexes = [
            models.Index(fields=['status'], name='mlcore_fil_status_c3a27d_idx'),
            models.Index(fields=['heartbeat_at'], name='mlcore_fil_heartbe_207655_idx'),
        ]
        ordering = ['provider']

    def __str__(self):
        return f"{self.provider}:{self.status}:{self.holder_run_id or '-'}"


class CanonicalItem(models.Model):
    """MLCore-native item identity independent of local catalog hydration."""

    id = models.UUIDField(primary_key=True, editable=False)
    item_type = models.CharField(max_length=32, choices=CANONICAL_ITEM_TYPE_CHOICES)
    canonical_key = models.CharField(max_length=512, unique=True)
    track = models.ForeignKey(
        'catalog.Track',
        to_field='juke_id',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='canonical_items',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mlcore_canonical_item'
        db_tablespace = 'juke_mlcore_hot'
        indexes = [
            models.Index(fields=['item_type'], name='mlcore_ci_item_ty_ef87b5_idx'),
            models.Index(fields=['track'], name='mlcore_ci_track_i_79f9ca_idx'),
        ]
        ordering = ['item_type', 'canonical_key']

    def __str__(self):
        return self.canonical_key


class CanonicalItemAlias(models.Model):
    """External provider identity that resolves to one MLCore canonical item."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    canonical_item = models.ForeignKey(
        CanonicalItem,
        on_delete=models.CASCADE,
        related_name='aliases',
    )
    source = models.CharField(max_length=64)
    resource_type = models.CharField(max_length=64)
    source_id = models.CharField(max_length=512)
    confidence = models.FloatField(default=1.0)
    source_version = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=16, choices=CANONICAL_ITEM_ALIAS_STATUS_CHOICES, default='active')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mlcore_canonical_item_alias'
        db_tablespace = 'juke_mlcore_hot'
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'resource_type', 'source_id'],
                name='mlcore_cia_source_resource_source_id_uniq',
            ),
        ]
        indexes = [
            models.Index(fields=['canonical_item'], name='mlcore_cia_canonic_7d4fe3_idx'),
            models.Index(fields=['source', 'resource_type', 'source_id'], name='mlcore_cia_lookup_117b92_idx'),
            models.Index(fields=['status'], name='mlcore_cia_status_6e75d3_idx'),
        ]
        ordering = ['source', 'resource_type', 'source_id']

    def __str__(self):
        return f'{self.source}:{self.resource_type}:{self.source_id}'


class CanonicalAliasMaterializationRun(models.Model):
    """Persistent checkpoint and provenance for canonical alias materialization."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_version = models.CharField(max_length=255, blank=True, default='')
    algorithm_version = models.CharField(max_length=64, default='canonical-alias-v2')
    status = models.CharField(max_length=16, choices=INGESTION_STATUS_CHOICES, default='pending')
    current_phase = models.CharField(max_length=64, blank=True, default='')
    include_catalog_tracks = models.BooleanField(default=False)
    batch_size = models.IntegerField(default=100_000)
    total_items = models.BigIntegerField(default=0)
    processed_items = models.BigIntegerField(default=0)
    created_count = models.BigIntegerField(default=0)
    existing_count = models.BigIntegerField(default=0)
    conflict_count = models.BigIntegerField(default=0)
    batches_processed = models.BigIntegerField(default=0)
    checkpoints = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mlcore_canonical_alias_materialization_run'
        db_tablespace = 'juke_mlcore_hot'
        indexes = [
            models.Index(fields=['status'], name='mlcore_camr_status_idx'),
            models.Index(fields=['source_version'], name='mlcore_camr_source_idx'),
            models.Index(fields=['started_at'], name='mlcore_camr_started_idx'),
        ]
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.source_version or self.id}:{self.status}'


class ListenBrainzEventLedger(models.Model):
    """Compact event-level ledger for ListenBrainz replay, dedupe, and audit."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_run = models.ForeignKey(
        SourceIngestionRun,
        on_delete=models.CASCADE,
        related_name='listenbrainz_event_ledgers',
    )
    event_signature = models.BinaryField(max_length=32, unique=True)
    played_at = models.DateTimeField(db_index=True)
    session_key = models.BinaryField(max_length=32, db_index=True)
    canonical_item = models.ForeignKey(
        CanonicalItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='listenbrainz_event_ledgers',
    )
    track = models.ForeignKey(
        'catalog.Track',
        to_field='juke_id',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='listenbrainz_event_ledgers',
    )
    resolution_state = models.PositiveSmallIntegerField(
        choices=LISTENBRAINZ_RESOLUTION_STATE_CHOICES,
        default=0,
    )
    cold_ref = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_listenbrainz_event_ledger'
        indexes = [
            models.Index(fields=['import_run'], name='mlcore_lbe_import__e9179a_idx'),
            models.Index(fields=['canonical_item'], name='mlcore_lbe_canonic_9067f9_idx'),
            models.Index(fields=['track'], name='mlcore_lbe_track_i_4c8647_idx'),
            models.Index(fields=['resolution_state'], name='mlcore_lbe_resolut_8e2ae0_idx'),
        ]
        ordering = ['played_at', 'id']

    @property
    def event_signature_hex(self):
        return _binary_to_hex(self.event_signature)

    @property
    def session_key_hex(self):
        return _binary_to_hex(self.session_key)

    def __str__(self):
        return f"{self.played_at.isoformat()}:{self.event_signature_hex[:12]}"


class ListenBrainzSessionTrack(models.Model):
    """Compact hot-path training facts keyed by ListenBrainz session and canonical item."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    import_run = models.ForeignKey(
        SourceIngestionRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='listenbrainz_session_tracks',
    )
    session_key = models.BinaryField(max_length=32, db_index=True)
    canonical_item = models.ForeignKey(
        CanonicalItem,
        on_delete=models.CASCADE,
        related_name='listenbrainz_session_tracks',
    )
    track = models.ForeignKey(
        'catalog.Track',
        to_field='juke_id',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='listenbrainz_session_tracks',
    )
    first_played_at = models.DateTimeField()
    last_played_at = models.DateTimeField()
    play_count = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_listenbrainz_session_track'
        db_tablespace = 'juke_mlcore_cold'
        unique_together = ('session_key', 'canonical_item')
        indexes = [
            models.Index(fields=['canonical_item'], name='mlcore_lst_canonic_78087f_idx'),
            models.Index(fields=['track'], name='mlcore_lst_track_i_5d5e20_idx'),
            models.Index(fields=['import_run'], name='mlcore_lst_import__6d7bf6_idx'),
            models.Index(fields=['last_played_at'], name='mlcore_lst_last_pl_4a4ec9_idx'),
        ]
        ordering = ['first_played_at', 'id']

    @property
    def session_key_hex(self):
        return _binary_to_hex(self.session_key)

    def __str__(self):
        return f"{self.session_key_hex[:12]}:{self.canonical_item_id}"


class ListenBrainzRawListen(models.Model):
    """Deprecated wide raw staging row retained only for legacy transition work."""

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
    recording_msid = models.TextField(blank=True, default='')
    release_msid = models.TextField(blank=True, default='')
    track_name = models.TextField(blank=True, default='')
    artist_name = models.TextField(blank=True, default='')
    release_name = models.TextField(blank=True, default='')
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
    """Deprecated wide training row retained only for legacy transition work."""

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
    baskets_processed = models.BigIntegerField()
    baskets_skipped = models.IntegerField()
    items_seen = models.BigIntegerField()
    pairs_written = models.BigIntegerField()
    source_row_count = models.BigIntegerField()
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
    Symmetric pairwise co-occurrence counts + PMI scores for MLCore canonical
    items (arch §5.4). Keys are opaque UUIDs and need not correspond 1:1 with
    a local catalog.Track row.

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
        db_index=False,
        on_delete=models.SET_NULL,
        related_name='cooccurrence_rows',
    )

    class Meta:
        db_table = 'mlcore_item_cooccurrence'
        db_tablespace = 'juke_mlcore_hot'
        unique_together = ('item_a_juke_id', 'item_b_juke_id')

    def __str__(self):
        return f"co({self.item_a_juke_id}, {self.item_b_juke_id})={self.co_count}"


class CoOccurrenceTrainingBucket(models.Model):
    """Progress row for one bucket of a bucketed co-occurrence training run."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    training_run = models.ForeignKey(
        TrainingRun,
        on_delete=models.CASCADE,
        related_name='cooccurrence_buckets',
    )
    source = models.CharField(max_length=64)
    algorithm_version = models.CharField(max_length=64)
    bucket_count = models.IntegerField()
    bucket_index = models.IntegerField()
    status = models.CharField(
        max_length=24,
        choices=TRAINING_BUCKET_STATUS_CHOICES,
        default='pending',
    )
    rows_written = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'mlcore_cooccurrence_training_bucket'
        unique_together = ('training_run', 'bucket_count', 'bucket_index')
        indexes = [
            models.Index(fields=['training_run', 'status'], name='mlcore_ctb_run_stat_idx'),
            models.Index(fields=['source', 'algorithm_version'], name='mlcore_ctb_src_alg_idx'),
            models.Index(fields=['bucket_count', 'bucket_index'], name='mlcore_ctb_bucket_idx'),
        ]
        ordering = ['training_run', 'bucket_index']

    def __str__(self):
        return f"{self.training_run_id}:{self.bucket_index}/{self.bucket_count}:{self.status}"


class CoOccurrenceTrainingBasket(models.Model):
    """Durable eligible ListenBrainz basket staging for a co-occurrence run."""

    training_run = models.ForeignKey(
        TrainingRun,
        db_index=False,
        on_delete=models.CASCADE,
        related_name='cooccurrence_training_baskets',
    )
    source = models.CharField(max_length=64)
    algorithm_version = models.CharField(max_length=64)
    bucket_count = models.IntegerField()
    bucket_index = models.IntegerField()
    session_key = models.BinaryField(max_length=32)
    item_count = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_cooccurrence_training_basket'
        db_tablespace = 'juke_mlcore_cold'
        indexes = [
            models.Index(fields=['training_run', 'session_key'], name='mlcore_ctbs_run_session_idx'),
        ]


class CoOccurrenceTrainingSessionItem(models.Model):
    """Durable basket item staging used for bucket-local pair generation."""

    training_run = models.ForeignKey(
        TrainingRun,
        db_index=False,
        on_delete=models.CASCADE,
        related_name='cooccurrence_training_session_items',
    )
    bucket_count = models.IntegerField()
    bucket_index = models.IntegerField()
    session_key = models.BinaryField(max_length=32)
    item_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_cooccurrence_training_session_item'
        db_tablespace = 'juke_mlcore_cold'
        indexes = [
            models.Index(fields=['training_run', 'bucket_index', 'session_key'], name='mlcore_ctsi_run_bkt_sess_idx'),
        ]


class CoOccurrenceTrainingPair(models.Model):
    """Append-only staged pair counts; merged into ItemCoOccurrence once."""

    training_run = models.ForeignKey(
        TrainingRun,
        db_index=False,
        on_delete=models.CASCADE,
        related_name='cooccurrence_training_pairs',
    )
    bucket_count = models.IntegerField()
    bucket_index = models.IntegerField()
    item_a_juke_id = models.UUIDField()
    item_b_juke_id = models.UUIDField()
    co_count = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mlcore_cooccurrence_training_pair'
        db_tablespace = 'juke_mlcore_cold'
        indexes = [
            models.Index(fields=['training_run', 'bucket_index'], name='mlcore_ctp_run_bucket_idx'),
        ]


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
    n_baskets = models.BigIntegerField(default=0)
    n_trials = models.BigIntegerField(default=0)
    n_cold_trials = models.BigIntegerField(default=0)
    evaluation_started_at = models.DateTimeField(null=True, blank=True)
    evaluation_elapsed_seconds = models.FloatField(null=True, blank=True)
    evaluation_trials_per_second = models.FloatField(null=True, blank=True)
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

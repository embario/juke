import uuid
from pathlib import Path
from unittest import mock

from django.test import TestCase

from mlcore.models import SourceIngestionRun
from mlcore.services.incremental_identity import run_incremental_identity_ingestion
from mlcore.services.listenbrainz_identity_bridge import (
    ConflictResolutionResult,
    IdentityGraphExpansionResult,
    ISRCAliasMaterializationResult,
    ListenBrainzIdentityBridgeResult,
)
from mlcore.services.listenbrainz_shards import ListenBrainzShardMaterializationResult
from mlcore.services.listenbrainz_source import RemoteSyncResult


class IncrementalIdentityIngestionTests(TestCase):

    def setUp(self):
        self.archive_path = Path('/tmp/listenbrainz-incremental.tar')
        self.archive_path.write_text('archive')
        self.source_version = 'listenbrainz-dump-2449-20260304-000003-incremental'
        SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='incremental',
            source_version=self.source_version,
            raw_path=str(self.archive_path),
            checksum='checksum',
            status='succeeded',
        )

    @mock.patch('mlcore.services.incremental_identity.materialize_listenbrainz_isrc_aliases')
    @mock.patch('mlcore.services.incremental_identity.resolve_listenbrainz_identity_conflicts')
    @mock.patch('mlcore.services.incremental_identity.expand_listenbrainz_identity_graph')
    @mock.patch('mlcore.services.incremental_identity.import_listenbrainz_identity_bridge')
    @mock.patch('mlcore.services.incremental_identity.materialize_listenbrainz_shards')
    @mock.patch('mlcore.services.incremental_identity.sync_listenbrainz_remote_dumps')
    def test_syncs_materializes_and_updates_identity_for_incremental_versions(
        self,
        mock_sync,
        mock_materialize,
        mock_bridge,
        mock_expand,
        mock_conflict,
        mock_isrc_aliases,
    ):
        mock_sync.return_value = RemoteSyncResult(
            status='succeeded',
            policy_classification='production_approved',
            full_source_version=None,
            incremental_source_versions=[self.source_version],
            downloaded_paths=[str(self.archive_path)],
            skipped_source_versions=[],
        )
        mock_materialize.return_value = ListenBrainzShardMaterializationResult(
            source_version=self.source_version,
            archive_path=str(self.archive_path),
            output_root='/tmp/shards',
            manifest_path='/tmp/shards/manifest.json',
            shard_count=1,
            total_uncompressed_bytes=123,
        )
        mock_bridge.return_value = ListenBrainzIdentityBridgeResult(
            run_id=str(uuid.uuid4()),
            source_version=self.source_version,
            shard_count=1,
            source_row_count=10,
            mapped_row_count=8,
            unique_pair_count=6,
            isrc_observation_count=4,
            unique_isrc_pair_count=3,
            malformed_row_count=0,
            active_mapping_count=5,
            conflict_msid_count=1,
            redirect_count=4,
            redirect_conflict_count=0,
            elapsed_seconds=1.0,
        )
        mock_expand.return_value = IdentityGraphExpansionResult(
            source_version=self.source_version,
            missing_msid_count=1,
            created_msid_count=1,
            active_mapping_count=5,
            conflict_msid_count=1,
            redirect_count=5,
            redirect_conflict_count=0,
            elapsed_seconds=1.0,
        )
        mock_conflict.return_value = ConflictResolutionResult(
            source_version=self.source_version,
            policy_version='shard-dominance-v1',
            eligible_conflict_msid_count=1,
            resolved_msid_count=1,
            created_msid_count=0,
            redirect_count=1,
            redirect_conflict_count=0,
            elapsed_seconds=1.0,
            min_winner_share=0.95,
            min_winner_shards=2,
        )
        mock_isrc_aliases.return_value = ISRCAliasMaterializationResult(
            source_version=self.source_version,
            isrc_observation_count=4,
            unique_msid_isrc_pair_count=3,
            distinct_isrc_count=2,
            materialized_alias_count=2,
            ambiguous_isrc_count=0,
            existing_alias_conflict_count=0,
            unresolved_pair_count=0,
        )

        result = run_incremental_identity_ingestion(max_incrementals=3)

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(len(result.processed_versions), 1)
        self.assertEqual(result.processed_versions[0].source_version, self.source_version)
        mock_materialize.assert_called_once_with(str(self.archive_path), source_version=self.source_version)
        mock_bridge.assert_called_once_with('/tmp/shards/manifest.json')
        mock_expand.assert_called_once_with(self.source_version)
        mock_conflict.assert_called_once_with(self.source_version)
        mock_isrc_aliases.assert_called_once_with(self.source_version)
        self.assertEqual(result.processed_versions[0].materialized_isrc_alias_count, 2)
        run = SourceIngestionRun.objects.get(source='mlcore-incremental-identity')
        self.assertEqual(run.status, 'succeeded')
        self.assertEqual(run.imported_row_count, 5)
        self.assertEqual(run.canonicalized_row_count, 6)

    @mock.patch('mlcore.services.incremental_identity.sync_listenbrainz_remote_dumps')
    def test_dry_run_discovers_candidates_without_network_sync_or_processing(self, mock_sync):

        result = run_incremental_identity_ingestion(max_incrementals=3, dry_run=True)

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.processed_versions, [])
        self.assertEqual(result.synced_incremental_source_versions, [])
        mock_sync.assert_not_called()

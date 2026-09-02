from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from mlcore.tasks import ingest_incremental_identity_task


class IncrementalIdentityTaskTests(SimpleTestCase):
    @mock.patch('mlcore.tasks.run_incremental_identity_ingestion')
    def test_runs_end_to_end_identity_pipeline(self, mock_run):
        processed = SimpleNamespace(source_version='listenbrainz-test', materialized_isrc_alias_count=2)
        mock_run.return_value = SimpleNamespace(
            run_id='run-id',
            status='succeeded',
            synced_full_source_version=None,
            synced_incremental_source_versions=['listenbrainz-test'],
            skipped_source_versions=[],
            processed_versions=[processed],
            elapsed_seconds=1.0,
        )

        result = ingest_incremental_identity_task.run(max_incrementals=3)

        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['processed_versions'][0]['materialized_isrc_alias_count'], 2)
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args.kwargs['max_incrementals'], 3)
        self.assertTrue(callable(mock_run.call_args.kwargs['progress_callback']))

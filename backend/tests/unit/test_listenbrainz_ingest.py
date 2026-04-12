import datetime
import io
import json
import tarfile
import tempfile
import uuid
from unittest import mock
from pathlib import Path

from django.test import TestCase, override_settings
from django.utils import timezone

from mlcore.ingestion.listenbrainz import (
    _maybe_release_memory,
    configured_source_version,
    import_listenbrainz_dump,
)
from mlcore.models import (
    ListenBrainzEventLedger,
    ListenBrainzRawListen,
    ListenBrainzSessionTrack,
    NormalizedInteraction,
    SourceIngestionRun,
)
from tests.utils import create_album, create_track


def _write_tar(contents: dict[str, str], *, suffix: str = '.tar.gz', mode: str = 'w:gz') -> Path:
    archive_path = Path(tempfile.mkdtemp()) / f'listenbrainz-slice{suffix}'
    with tarfile.open(archive_path, mode) as archive:
        for name, payload in contents.items():
            data = payload.encode('utf-8')
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return archive_path


def _listen_payload(
    *,
    user_name: str,
    listened_at: int,
    timestamp: int | None = None,
    recording_mbid: uuid.UUID | None = None,
    recording_msid: str = '',
    track_name: str = 'Track Name',
    artist_name: str = 'Artist Name',
    release_name: str = 'Album Name',
    use_additional_info_mbid_fallback: bool = False,
    additional_info: dict | None = None,
) -> dict:
    info = dict(additional_info or {})
    mbid_mapping = {
        'recording_mbid': '',
        'release_mbid': '',
        'artist_mbids': [],
    }
    if recording_mbid:
        if use_additional_info_mbid_fallback:
            info['recording_mbid'] = str(recording_mbid)
        else:
            mbid_mapping['recording_mbid'] = str(recording_mbid)

    return {
        'user_name': user_name,
        'listened_at': listened_at if timestamp is None else None,
        'timestamp': timestamp if timestamp is not None else None,
        'track_metadata': {
            'track_name': track_name,
            'artist_name': artist_name,
            'release_name': release_name,
            'recording_msid': recording_msid,
            'additional_info': info,
            'mbid_mapping': mbid_mapping,
        },
    }


@override_settings(
    MLCORE_LISTENBRAINZ_USER_HASH_SALT='test-salt',
    MLCORE_LISTENBRAINZ_MAX_MALFORMED_ROWS=0,
    MLCORE_LISTENBRAINZ_SESSION_WINDOW_SECONDS=1800,
)
class ListenBrainzImportTests(TestCase):

    def setUp(self):
        album = create_album(
            name='Testing Album',
            total_tracks=1,
            release_date=datetime.date(2025, 1, 1),
        )
        self.track = create_track(
            name='Testing Track',
            album=album,
            track_number=1,
            duration_ms=123000,
        )
        self.track.mbid = uuid.uuid4()
        self.track.save(update_fields=['mbid'])

    def test_imports_compressed_dump_slice_into_raw_and_normalized_rows(self):
        payloads = [
            _listen_payload(
                user_name='alice',
                listened_at=1710000000,
                recording_mbid=self.track.mbid,
                recording_msid='msid-1',
                track_name='Testing Track',
            ),
            _listen_payload(
                user_name='bob',
                listened_at=1710000900,
                recording_msid='msid-2',
                track_name='Unknown Track',
            ),
        ]
        archive_path = _write_tar({
            'listenbrainz/listens/2026/03/chunk-0001.listens': '\n'.join(json.dumps(payload) for payload in payloads),
        })

        result = import_listenbrainz_dump(archive_path, source_version='2026-03-22-full', import_mode='full')

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.source_row_count, 2)
        self.assertEqual(result.imported_row_count, 2)
        self.assertEqual(result.canonicalized_row_count, 2)
        self.assertEqual(ListenBrainzEventLedger.objects.count(), 2)
        self.assertEqual(ListenBrainzSessionTrack.objects.count(), 1)
        self.assertEqual(ListenBrainzRawListen.objects.count(), 0)
        self.assertEqual(NormalizedInteraction.objects.count(), 0)

        run = SourceIngestionRun.objects.get(pk=result.run_id)
        self.assertEqual(run.import_mode, 'full')
        self.assertEqual(run.policy_classification, 'production_approved')
        self.assertTrue(run.checksum)

        matched = ListenBrainzSessionTrack.objects.get(track_id=self.track.juke_id)
        self.assertEqual(matched.play_count, 1)
        self.assertEqual(len(matched.session_key_hex), 64)
        self.assertEqual(
            ListenBrainzEventLedger.objects.filter(track_id=self.track.juke_id).count(),
            1,
        )
        self.assertEqual(ListenBrainzEventLedger.objects.filter(track_id__isnull=True).count(), 1)

    def test_reimport_is_idempotent_and_counts_duplicates(self):
        payload = _listen_payload(
            user_name='alice',
            listened_at=1710000000,
            recording_mbid=self.track.mbid,
            recording_msid='repeat-msid',
            track_name='Testing Track',
        )
        archive_path = _write_tar({
            'listenbrainz/listens/2026/03/chunk-0001.listens': '\n'.join([
                json.dumps(payload),
                json.dumps(payload),
            ]),
        })

        first = import_listenbrainz_dump(archive_path, source_version='2026-03-22-full', import_mode='full')
        second = import_listenbrainz_dump(archive_path, source_version='2026-03-22-full', import_mode='full')

        self.assertEqual(first.imported_row_count, 1)
        self.assertEqual(first.duplicate_row_count, 1)
        self.assertEqual(second.imported_row_count, 0)
        self.assertEqual(second.duplicate_row_count, 2)
        self.assertEqual(ListenBrainzEventLedger.objects.count(), 1)
        self.assertEqual(ListenBrainzSessionTrack.objects.count(), 1)
        self.assertEqual(ListenBrainzRawListen.objects.count(), 0)
        self.assertEqual(NormalizedInteraction.objects.count(), 0)
        self.assertEqual(SourceIngestionRun.objects.count(), 2)

    def test_malformed_dump_fails_fast_and_rolls_back_rows(self):
        archive_path = _write_tar({
            'listenbrainz/listens/2026/03/chunk-0001.listens': '\n'.join([
                json.dumps(_listen_payload(user_name='alice', listened_at=1710000000, recording_msid='ok-msid')),
                '{"user_name": ',
            ]),
        })

        with self.assertRaisesMessage(ValueError, 'invalid JSON'):
            import_listenbrainz_dump(archive_path, source_version='2026-03-22-inc', import_mode='incremental')

        run = SourceIngestionRun.objects.get()
        self.assertEqual(run.status, 'failed')
        self.assertIn('invalid JSON', run.last_error)
        self.assertEqual(ListenBrainzEventLedger.objects.count(), 0)
        self.assertEqual(ListenBrainzSessionTrack.objects.count(), 0)
        self.assertEqual(ListenBrainzRawListen.objects.count(), 0)
        self.assertEqual(NormalizedInteraction.objects.count(), 0)

    def test_imports_zstd_tar_dump(self):
        archive_path = _write_tar(
            {
                'listenbrainz/listens/2026/03/chunk-0001.listens': json.dumps(
                    _listen_payload(
                        user_name='alice',
                        listened_at=1710000000,
                        recording_mbid=self.track.mbid,
                        recording_msid='zstd-msid',
                        track_name='Testing Track',
                    )
                ),
            },
            suffix='.tar.zst',
            mode='w:zst',
        )

        result = import_listenbrainz_dump(archive_path, source_version='2026-03-22-full-zst', import_mode='full')

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.source_row_count, 1)
        self.assertEqual(result.imported_row_count, 1)
        self.assertEqual(result.canonicalized_row_count, 1)
        self.assertEqual(ListenBrainzEventLedger.objects.count(), 1)
        self.assertEqual(ListenBrainzSessionTrack.objects.count(), 1)
        self.assertEqual(ListenBrainzRawListen.objects.count(), 0)
        self.assertEqual(NormalizedInteraction.objects.count(), 0)

    def test_reports_progress_snapshots(self):
        payloads = [
            _listen_payload(
                user_name='alice',
                listened_at=1710000000,
                recording_mbid=self.track.mbid,
                recording_msid='progress-msid-1',
                track_name='Testing Track',
            ),
            _listen_payload(
                user_name='alice',
                listened_at=1710000900,
                recording_msid='progress-msid-2',
                track_name='Unknown Track',
            ),
        ]
        archive_path = _write_tar({
            'listenbrainz/listens/2026/03/chunk-0001.listens': '\n'.join(json.dumps(payload) for payload in payloads),
        })
        snapshots = []

        result = import_listenbrainz_dump(
            archive_path,
            source_version='2026-03-22-progress',
            import_mode='full',
            progress_callback=snapshots.append,
        )

        self.assertEqual(result.status, 'succeeded')
        self.assertTrue(snapshots)
        self.assertEqual(snapshots[-1]['source_row_count'], 2)
        self.assertEqual(snapshots[-1]['imported_row_count'], 2)
        self.assertEqual(snapshots[-1]['last_origin'], 'listenbrainz/listens/2026/03/chunk-0001.listens')
        self.assertEqual(snapshots[-1]['last_entry_index'], 1)

    def test_import_accepts_track_metadata_longer_than_legacy_char_limits(self):
        long_track_name = 'X' * 2086
        long_artist_name = 'Y' * 1400
        archive_path = _write_tar({
            'listenbrainz/listens/2026/03/chunk-0001.listens': json.dumps(
                _listen_payload(
                    user_name='alice',
                    listened_at=1710000000,
                    recording_msid='long-field-msid',
                    track_name=long_track_name,
                    artist_name=long_artist_name,
                )
            ),
        })

        result = import_listenbrainz_dump(archive_path, source_version='2026-03-22-long-fields', import_mode='full')

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(ListenBrainzEventLedger.objects.filter(import_run_id=result.run_id).count(), 1)
        self.assertEqual(ListenBrainzSessionTrack.objects.filter(import_run_id=result.run_id).count(), 0)
        self.assertEqual(ListenBrainzRawListen.objects.count(), 0)
        self.assertEqual(NormalizedInteraction.objects.count(), 0)

    def test_resume_restarts_inside_multi_listen_line_after_committed_batch(self):
        archive_path = _write_tar({
            'listenbrainz/listens/2026/03/chunk-0001.listens': json.dumps(
                {
                    'user_name': 'alice',
                    'payload': {
                        'listens': [
                            _listen_payload(
                                user_name='alice',
                                listened_at=1710000000,
                                recording_msid='resume-msid-1',
                                track_name='Unknown Track 1',
                            ),
                            _listen_payload(
                                user_name='alice',
                                listened_at=1710000001,
                                recording_msid='resume-msid-2',
                                track_name='Unknown Track 2',
                            ),
                            _listen_payload(
                                user_name='alice',
                                listened_at=1710000002,
                                recording_msid='resume-msid-3',
                                track_name='Unknown Track 3',
                            ),
                        ],
                    },
                }
            ),
        })
        original_flush_batch = import_listenbrainz_dump.__globals__['_flush_batch']
        flush_calls = {'count': 0}

        def flaky_flush_batch(*args, **kwargs):
            flush_calls['count'] += 1
            result = original_flush_batch(*args, **kwargs)
            if flush_calls['count'] == 1:
                raise RuntimeError('simulated worker crash after first committed batch')
            return result

        with mock.patch('mlcore.ingestion.listenbrainz._flush_batch', side_effect=flaky_flush_batch):
            with self.assertRaisesMessage(RuntimeError, 'simulated worker crash'):
                import_listenbrainz_dump(
                    archive_path,
                    source_version='2026-03-22-resume',
                    import_mode='full',
                    batch_size=1,
                )

        failed_run = SourceIngestionRun.objects.get(status='failed')
        self.assertEqual(failed_run.imported_row_count, 1)
        self.assertEqual(
            failed_run.metadata['last_committed_checkpoint'],
            {
                'origin': 'listenbrainz/listens/2026/03/chunk-0001.listens',
                'line_number': 1,
                'entry_index': 1,
                'source_row_count': 1,
                'imported_row_count': 1,
                'duplicate_row_count': 0,
                'canonicalized_row_count': 1,
                'unresolved_row_count': 1,
                'malformed_row_count': 0,
            },
        )

        resumed = import_listenbrainz_dump(
            archive_path,
            source_version='2026-03-22-resume',
            import_mode='full',
            batch_size=1,
        )

        self.assertEqual(resumed.status, 'succeeded')
        self.assertEqual(resumed.source_row_count, 3)
        self.assertEqual(resumed.imported_row_count, 3)
        self.assertEqual(ListenBrainzEventLedger.objects.count(), 3)
        self.assertEqual(ListenBrainzSessionTrack.objects.count(), 0)
        self.assertEqual(ListenBrainzRawListen.objects.count(), 0)
        self.assertEqual(NormalizedInteraction.objects.count(), 0)
        resumed_run = SourceIngestionRun.objects.get(pk=resumed.run_id)
        self.assertEqual(
            resumed_run.metadata['resume_start_checkpoint'],
            failed_run.metadata['last_committed_checkpoint'],
        )
        self.assertEqual(str(resumed_run.metadata['resumed_from_run_id']), str(failed_run.pk))

    def test_resume_skips_newer_failed_run_without_checkpoint(self):
        archive_path = _write_tar({
            'listenbrainz/listens/2026/03/chunk-0001.listens': '\n'.join([
                json.dumps(_listen_payload(user_name='alice', listened_at=1710000000, recording_msid='resume-msid-1')),
                json.dumps(_listen_payload(user_name='alice', listened_at=1710000001, recording_msid='resume-msid-2')),
            ]),
        })
        original_flush_batch = import_listenbrainz_dump.__globals__['_flush_batch']
        flush_calls = {'count': 0}

        def flaky_flush_batch(*args, **kwargs):
            flush_calls['count'] += 1
            result = original_flush_batch(*args, **kwargs)
            if flush_calls['count'] == 1:
                raise RuntimeError('simulated worker crash after first committed batch')
            return result

        with mock.patch('mlcore.ingestion.listenbrainz._flush_batch', side_effect=flaky_flush_batch):
            with self.assertRaisesMessage(RuntimeError, 'simulated worker crash'):
                import_listenbrainz_dump(
                    archive_path,
                    source_version='2026-03-22-checkpoint-skip',
                    import_mode='full',
                    batch_size=1,
                )

        checkpointed_run = SourceIngestionRun.objects.get(status='failed')
        self.assertTrue(checkpointed_run.metadata.get('last_committed_checkpoint'))
        SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version='2026-03-22-checkpoint-skip',
            raw_path=str(archive_path),
            checksum=checkpointed_run.checksum,
            status='failed',
            policy_classification='production_approved',
            completed_at=timezone.now(),
            metadata={},
        )

        resumed = import_listenbrainz_dump(
            archive_path,
            source_version='2026-03-22-checkpoint-skip',
            import_mode='full',
            batch_size=1,
        )

        resumed_run = SourceIngestionRun.objects.get(pk=resumed.run_id)
        self.assertEqual(str(resumed_run.metadata['resumed_from_run_id']), str(checkpointed_run.pk))
        self.assertEqual(resumed.imported_row_count, 2)

    @override_settings(MLCORE_LISTENBRAINZ_MEMORY_TRIM_EVERY_ROWS=1000)
    @mock.patch('mlcore.ingestion.listenbrainz._malloc_trim', return_value=True)
    @mock.patch('mlcore.ingestion.listenbrainz.gc.collect')
    def test_maybe_release_memory_trims_on_configured_threshold(self, mock_gc_collect, mock_malloc_trim):
        counts = {'source_row_count': 1500}

        updated = _maybe_release_memory(
            counts=counts,
            last_trimmed_source_rows=0,
        )

        self.assertEqual(updated, 1500)
        mock_gc_collect.assert_called_once_with()
        mock_malloc_trim.assert_called_once_with()

    @override_settings(MLCORE_LISTENBRAINZ_MEMORY_TRIM_EVERY_ROWS=1000)
    @mock.patch('mlcore.ingestion.listenbrainz._malloc_trim', return_value=True)
    @mock.patch('mlcore.ingestion.listenbrainz.gc.collect')
    def test_maybe_release_memory_skips_below_threshold(self, mock_gc_collect, mock_malloc_trim):
        counts = {'source_row_count': 900}

        updated = _maybe_release_memory(
            counts=counts,
            last_trimmed_source_rows=0,
        )

        self.assertEqual(updated, 0)
        mock_gc_collect.assert_not_called()
        mock_malloc_trim.assert_not_called()

    def test_imports_real_dump_schema_variants(self):
        payload = _listen_payload(
            user_name='alice',
            listened_at=1710000000,
            timestamp=1710000000,
            recording_mbid=self.track.mbid,
            recording_msid='real-schema-msid',
            track_name='Testing Track',
            use_additional_info_mbid_fallback=True,
        )
        archive_path = _write_tar({
            'listenbrainz/listens/2026/03/chunk-0001.listens': json.dumps(payload),
        })

        result = import_listenbrainz_dump(archive_path, source_version='2026-03-22-real-schema', import_mode='full')

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.source_row_count, 1)
        self.assertEqual(result.imported_row_count, 1)
        matched = ListenBrainzSessionTrack.objects.get()
        self.assertEqual(matched.track_id, self.track.juke_id)
        self.assertEqual(ListenBrainzEventLedger.objects.get().track_id, self.track.juke_id)

    def test_configured_source_version_strips_dump_archive_suffix(self):
        version = configured_source_version(
            'full',
            '/srv/data/listenbrainz/listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst',
        )

        self.assertEqual(
            version,
            'listenbrainz-dump-2446-20260301-000003-full',
        )

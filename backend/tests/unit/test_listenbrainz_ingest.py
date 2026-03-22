import datetime
import io
import json
import tarfile
import tempfile
import uuid
from pathlib import Path

from django.test import TestCase, override_settings

from mlcore.ingestion.listenbrainz import import_listenbrainz_dump
from mlcore.models import ListenBrainzRawListen, NormalizedInteraction, SourceIngestionRun
from tests.utils import create_album, create_track


def _write_tar_gz(contents: dict[str, str]) -> Path:
    archive_path = Path(tempfile.mkdtemp()) / 'listenbrainz-slice.tar.gz'
    with tarfile.open(archive_path, 'w:gz') as archive:
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
    recording_mbid: uuid.UUID | None = None,
    recording_msid: str = '',
    track_name: str = 'Track Name',
    artist_name: str = 'Artist Name',
    release_name: str = 'Album Name',
    additional_info: dict | None = None,
) -> dict:
    return {
        'user_name': user_name,
        'listened_at': listened_at,
        'track_metadata': {
            'track_name': track_name,
            'artist_name': artist_name,
            'release_name': release_name,
            'recording_msid': recording_msid,
            'additional_info': additional_info or {},
            'mbid_mapping': {
                'recording_mbid': str(recording_mbid) if recording_mbid else '',
                'release_mbid': '',
                'artist_mbids': [],
            },
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
        archive_path = _write_tar_gz({
            'listenbrainz/chunk-0001.jsonl': '\n'.join(json.dumps(payload) for payload in payloads),
        })

        result = import_listenbrainz_dump(archive_path, source_version='2026-03-22-full', import_mode='full')

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.source_row_count, 2)
        self.assertEqual(result.imported_row_count, 2)
        self.assertEqual(result.canonicalized_row_count, 2)
        self.assertEqual(ListenBrainzRawListen.objects.count(), 2)
        self.assertEqual(NormalizedInteraction.objects.count(), 2)

        run = SourceIngestionRun.objects.get(pk=result.run_id)
        self.assertEqual(run.import_mode, 'full')
        self.assertEqual(run.policy_classification, 'research_only')
        self.assertTrue(run.checksum)

        matched = NormalizedInteraction.objects.get(track_id=self.track.juke_id)
        self.assertEqual(matched.source_id, 'listenbrainz')
        self.assertEqual(matched.source_version, '2026-03-22-full')
        self.assertNotEqual(matched.source_user_id, 'alice')
        self.assertTrue(matched.session_hint.startswith(matched.source_user_id))
        self.assertEqual(matched.track_identifier_candidates['recording_mbid'], str(self.track.mbid))

    def test_reimport_is_idempotent_and_counts_duplicates(self):
        payload = _listen_payload(
            user_name='alice',
            listened_at=1710000000,
            recording_mbid=self.track.mbid,
            recording_msid='repeat-msid',
            track_name='Testing Track',
        )
        archive_path = _write_tar_gz({
            'listenbrainz/chunk-0001.jsonl': '\n'.join([
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
        self.assertEqual(ListenBrainzRawListen.objects.count(), 1)
        self.assertEqual(NormalizedInteraction.objects.count(), 1)
        self.assertEqual(SourceIngestionRun.objects.count(), 2)

    def test_malformed_dump_fails_fast_and_rolls_back_rows(self):
        archive_path = _write_tar_gz({
            'listenbrainz/chunk-0001.jsonl': '\n'.join([
                json.dumps(_listen_payload(user_name='alice', listened_at=1710000000, recording_msid='ok-msid')),
                '{"user_name": ',
            ]),
        })

        with self.assertRaisesMessage(ValueError, 'invalid JSON'):
            import_listenbrainz_dump(archive_path, source_version='2026-03-22-inc', import_mode='incremental')

        run = SourceIngestionRun.objects.get()
        self.assertEqual(run.status, 'failed')
        self.assertIn('invalid JSON', run.last_error)
        self.assertEqual(ListenBrainzRawListen.objects.count(), 0)
        self.assertEqual(NormalizedInteraction.objects.count(), 0)

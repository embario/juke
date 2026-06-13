import uuid
import threading
from unittest import mock
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from catalog.models import TrackExternalIdentifier
from mlcore.models import CanonicalAliasMaterializationRun, CanonicalItem, CanonicalItemAlias
from mlcore.services.canonical_items import (
    ALIAS_RESOURCE_RECORDING,
    ALIAS_RESOURCE_TRACK,
    ALIAS_SOURCE_MUSICBRAINZ,
    ALIAS_SOURCE_LISTENBRAINZ,
    ALIAS_SOURCE_SPOTIFY,
    AliasMaterializationProgress,
    ITEM_TYPE_RECORDING_MBID,
    ITEM_TYPE_RECORDING_MSID,
    ITEM_TYPE_SPOTIFY_TRACK,
    bulk_ensure_canonical_items_for_tracks,
    identity_from_listenbrainz_candidates,
    identity_from_parts,
    canonical_item_alias_uuid,
    materialize_canonical_item_self_aliases,
    materialize_track_aliases,
    write_alias_materialization_metrics,
)
from tests.utils import create_album, create_track


class CanonicalItemIdentityTests(SimpleTestCase):

    def test_prefers_recording_mbid_over_other_ids(self):
        recording_mbid = uuid.uuid4()

        identity = identity_from_listenbrainz_candidates(
            recording_mbid=str(recording_mbid),
            recording_msid='recording-msid',
            spotify_id='spotify-track-id',
        )

        self.assertIsNotNone(identity)
        self.assertEqual(identity.item_type, ITEM_TYPE_RECORDING_MBID)
        self.assertEqual(identity.canonical_key, f'{ITEM_TYPE_RECORDING_MBID}:{recording_mbid}')

    def test_prefers_recording_msid_over_spotify(self):
        identity = identity_from_listenbrainz_candidates(
            recording_msid='recording-msid',
            spotify_id='spotify-track-id',
        )

        self.assertIsNotNone(identity)
        self.assertEqual(identity.item_type, ITEM_TYPE_RECORDING_MSID)
        self.assertEqual(identity.canonical_key, f'{ITEM_TYPE_RECORDING_MSID}:recording-msid')

    def test_falls_back_to_spotify(self):
        identity = identity_from_listenbrainz_candidates(
            spotify_id='spotify-track-id',
        )

        self.assertIsNotNone(identity)
        self.assertEqual(identity.item_type, ITEM_TYPE_SPOTIFY_TRACK)
        self.assertEqual(identity.canonical_key, f'{ITEM_TYPE_SPOTIFY_TRACK}:spotify-track-id')


class CanonicalItemAliasModelTests(TestCase):

    def setUp(self):
        self.album = create_album(name='Album', total_tracks=10, release_date='2026-01-01')
        self.track = create_track(name='Track', album=self.album, track_number=1, duration_ms=1000)
        self.canonical_item = bulk_ensure_canonical_items_for_tracks([self.track])[self.track.juke_id]

    def test_alias_unique_by_source_resource_and_source_id(self):
        CanonicalItemAlias.objects.create(
            canonical_item=self.canonical_item,
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='sp-track',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CanonicalItemAlias.objects.create(
                    canonical_item=self.canonical_item,
                    source=ALIAS_SOURCE_SPOTIFY,
                    resource_type=ALIAS_RESOURCE_TRACK,
                    source_id='sp-track',
                )

    def test_alias_cascades_when_canonical_item_is_deleted(self):
        CanonicalItemAlias.objects.create(
            canonical_item=self.canonical_item,
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='sp-track',
        )

        self.canonical_item.delete()

        self.assertEqual(CanonicalItemAlias.objects.count(), 0)

    def test_canonical_identity_tables_are_hot_path_tables(self):
        self.assertEqual(CanonicalItem._meta.db_tablespace, 'juke_mlcore_hot')
        self.assertEqual(CanonicalItemAlias._meta.db_tablespace, 'juke_mlcore_hot')
        self.assertEqual(CanonicalAliasMaterializationRun._meta.db_tablespace, 'juke_mlcore_hot')


class CanonicalItemAliasMaterializationTests(TestCase):

    def setUp(self):
        self.album = create_album(name='Album', total_tracks=10, release_date='2026-01-01')

    def test_creates_spotify_and_musicbrainz_aliases_for_track(self):
        mbid = uuid.uuid4()
        track = create_track(
            name='Track',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-a',
            mbid=mbid,
        )

        result = materialize_track_aliases([track], source_version='test-corpus')

        self.assertEqual(result.created_count, 2)
        canonical_item = bulk_ensure_canonical_items_for_tracks([track])[track.juke_id]
        spotify_alias = CanonicalItemAlias.objects.get(
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='spotify-a',
        )
        mbid_alias = CanonicalItemAlias.objects.get(
            source=ALIAS_SOURCE_MUSICBRAINZ,
            resource_type=ALIAS_RESOURCE_RECORDING,
            source_id=str(mbid),
        )
        self.assertEqual(spotify_alias.canonical_item, canonical_item)
        self.assertEqual(mbid_alias.canonical_item, canonical_item)
        self.assertEqual(canonical_item.item_type, ITEM_TYPE_RECORDING_MBID)
        self.assertEqual(spotify_alias.source_version, 'test-corpus')

    def test_creates_track_external_identifier_aliases(self):
        track = create_track(
            name='Track',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-b',
        )
        TrackExternalIdentifier.objects.create(
            track=track,
            source='musicbrainz',
            external_id='external-recording',
        )

        materialize_track_aliases([track])

        alias = CanonicalItemAlias.objects.get(
            source='musicbrainz',
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='external-recording',
        )
        self.assertEqual(alias.canonical_item, bulk_ensure_canonical_items_for_tracks([track])[track.juke_id])

    def test_materialization_is_idempotent(self):
        track = create_track(
            name='Track',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-c',
        )

        first = materialize_track_aliases([track])
        second = materialize_track_aliases([track])

        self.assertEqual(first.created_count, 1)
        self.assertEqual(second.created_count, 0)
        self.assertEqual(second.existing_count, 1)
        self.assertEqual(CanonicalItemAlias.objects.count(), 1)

    def test_materialization_batches_tracks_from_database(self):
        create_track(
            name='First',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-batch-a',
        )
        create_track(
            name='Second',
            album=self.album,
            track_number=2,
            duration_ms=1000,
            spotify_id='spotify-batch-b',
        )
        create_track(
            name='Third',
            album=self.album,
            track_number=3,
            duration_ms=1000,
            spotify_id='spotify-batch-c',
        )

        result = materialize_track_aliases(source_version='batched-corpus', batch_size=2)

        self.assertEqual(result.created_count, 3)
        self.assertEqual(result.conflict_count, 0)
        self.assertEqual(CanonicalItemAlias.objects.filter(source_version='batched-corpus').count(), 3)

    def test_materialization_reports_progress_per_batch(self):
        create_track(
            name='First',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-progress-a',
        )
        create_track(
            name='Second',
            album=self.album,
            track_number=2,
            duration_ms=1000,
            spotify_id='spotify-progress-b',
        )
        snapshots = []

        materialize_track_aliases(
            source_version='progress-corpus',
            batch_size=1,
            progress_callback=lambda progress: snapshots.append((
                progress.status,
                progress.total_items,
                progress.processed_items,
                progress.created_count,
            )),
        )

        self.assertGreaterEqual(len(snapshots), 3)
        self.assertEqual(snapshots[0], ('running', 2, 0, 0))
        self.assertEqual(snapshots[-1], ('succeeded', 2, 2, 2))

    def test_materialization_reports_conflicts_across_batches(self):
        first = create_track(
            name='First',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-cross-batch',
        )
        second = create_track(
            name='Second',
            album=self.album,
            track_number=2,
            duration_ms=1000,
        )
        TrackExternalIdentifier.objects.create(
            track=second,
            source=ALIAS_SOURCE_SPOTIFY,
            external_id='spotify-cross-batch',
        )

        result = materialize_track_aliases([first, second], batch_size=1)

        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.conflict_count, 1)
        self.assertEqual(result.conflicts[0].reason, 'existing_mapping')
        self.assertEqual(CanonicalItemAlias.objects.count(), 2)

    def test_materialization_rejects_invalid_batch_size(self):
        with self.assertRaisesMessage(ValueError, 'batch_size must be greater than 0'):
            materialize_track_aliases(batch_size=0)

    def test_conflict_is_reported_without_reassigning_existing_alias(self):
        first = create_track(
            name='First',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-first',
        )
        second = create_track(
            name='Second',
            album=self.album,
            track_number=2,
            duration_ms=1000,
            spotify_id='spotify-second',
        )
        first_canonical = bulk_ensure_canonical_items_for_tracks([first])[first.juke_id]
        second_canonical = bulk_ensure_canonical_items_for_tracks([second])[second.juke_id]
        CanonicalItemAlias.objects.create(
            canonical_item=first_canonical,
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='spotify-second',
        )

        result = materialize_track_aliases([second])

        self.assertEqual(result.conflict_count, 1)
        alias = CanonicalItemAlias.objects.get(
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='spotify-second',
        )
        self.assertEqual(alias.canonical_item, first_canonical)
        self.assertNotEqual(alias.canonical_item, second_canonical)


class CanonicalItemSelfAliasMaterializationTests(TestCase):

    def test_materializes_aliases_from_canonical_keys(self):
        mbid_identity = identity_from_parts(item_type=ITEM_TYPE_RECORDING_MBID, key_value=str(uuid.uuid4()))
        msid_identity = identity_from_parts(item_type=ITEM_TYPE_RECORDING_MSID, key_value='msid-self-alias')
        spotify_identity = identity_from_parts(item_type=ITEM_TYPE_SPOTIFY_TRACK, key_value='spotify-self-alias')
        CanonicalItem.objects.bulk_create([
            CanonicalItem(
                id=mbid_identity.item_id,
                item_type=mbid_identity.item_type,
                canonical_key=mbid_identity.canonical_key,
            ),
            CanonicalItem(
                id=msid_identity.item_id,
                item_type=msid_identity.item_type,
                canonical_key=msid_identity.canonical_key,
            ),
            CanonicalItem(
                id=spotify_identity.item_id,
                item_type=spotify_identity.item_type,
                canonical_key=spotify_identity.canonical_key,
            ),
        ])

        result = materialize_canonical_item_self_aliases(source_version='self-alias-test', batch_size=2)

        self.assertEqual(result.created_count, 3)
        self.assertEqual(result.conflict_count, 0)
        self.assertEqual(CanonicalItemAlias.objects.get(
            source=ALIAS_SOURCE_MUSICBRAINZ,
            resource_type=ALIAS_RESOURCE_RECORDING,
            source_id=mbid_identity.canonical_key.removeprefix(f'{ITEM_TYPE_RECORDING_MBID}:'),
        ).canonical_item_id, mbid_identity.item_id)
        self.assertEqual(CanonicalItemAlias.objects.get(
            source=ALIAS_SOURCE_LISTENBRAINZ,
            resource_type=ALIAS_RESOURCE_RECORDING,
            source_id='msid-self-alias',
        ).canonical_item_id, msid_identity.item_id)
        self.assertEqual(CanonicalItemAlias.objects.get(
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='spotify-self-alias',
        ).canonical_item_id, spotify_identity.item_id)
        spotify_alias = CanonicalItemAlias.objects.get(source=ALIAS_SOURCE_SPOTIFY, source_id='spotify-self-alias')
        self.assertEqual(
            spotify_alias.id,
            canonical_item_alias_uuid(source='spotify', resource_type='track', source_id='spotify-self-alias'),
        )

    def test_self_alias_materialization_is_idempotent(self):
        identity = identity_from_parts(item_type=ITEM_TYPE_RECORDING_MSID, key_value='msid-idempotent')
        CanonicalItem.objects.create(
            id=identity.item_id,
            item_type=identity.item_type,
            canonical_key=identity.canonical_key,
        )

        first = materialize_canonical_item_self_aliases(batch_size=1)
        second = materialize_canonical_item_self_aliases(batch_size=1)

        self.assertEqual(first.created_count, 1)
        self.assertEqual(second.created_count, 0)
        self.assertEqual(second.existing_count, 1)
        self.assertEqual(CanonicalItemAlias.objects.count(), 1)

    def test_self_alias_materialization_reports_progress(self):
        for index in range(3):
            identity = identity_from_parts(item_type=ITEM_TYPE_RECORDING_MSID, key_value=f'msid-progress-{index}')
            CanonicalItem.objects.create(
                id=identity.item_id,
                item_type=identity.item_type,
                canonical_key=identity.canonical_key,
            )
        snapshots = []

        materialize_canonical_item_self_aliases(
            batch_size=2,
            progress_callback=lambda progress: snapshots.append((
                progress.status,
                progress.total_items,
                progress.processed_items,
                progress.created_count,
            )),
        )

        self.assertEqual(snapshots[0], ('running', 3, 0, 0))
        self.assertEqual(snapshots[-1], ('succeeded', 3, 3, 3))


class CanonicalItemAliasMetricsTests(SimpleTestCase):

    def test_writes_materialization_progress_metrics(self):
        progress = AliasMaterializationProgress(
            status='running',
            total_items=100,
            processed_items=25,
            created_count=20,
            existing_count=4,
            conflict_count=1,
            batch_size=10,
            batches_processed=3,
            source_version='test-version',
        )

        with TemporaryDirectory() as temp_dir:
            metrics_path = Path(temp_dir) / 'mlcore_canonical_alias_materialization.prom'
            write_alias_materialization_metrics(progress, metrics_path=metrics_path)

            content = metrics_path.read_text(encoding='utf-8')

        self.assertIn('status="running",source_version="test-version",phase=""', content)
        self.assertIn('algorithm_version="canonical-alias-v2",run_id=""', content)
        self.assertIn('mlcore_canonical_alias_materialization_items_total', content)
        self.assertIn('mlcore_canonical_alias_materialization_items_processed', content)
        self.assertIn('mlcore_canonical_alias_materialization_progress_fraction', content)
        self.assertIn('mlcore_canonical_alias_materialization_eta_seconds', content)
        self.assertIn('mlcore_canonical_alias_materialization_alias_conflicts', content)


class CanonicalAliasConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_materialization_creates_one_alias_and_counts_actual_insert(self):
        album = create_album(name='Concurrent Album', total_tracks=1, release_date='2026-01-01')
        track = create_track(
            name='Concurrent Track', album=album, track_number=1, duration_ms=1000,
            spotify_id='0VjIjW4GlUZAMYd2vXMi3b',
        )
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def materialize():
            try:
                close_old_connections()
                local_track = type(track).objects.get(pk=track.pk)
                barrier.wait()
                results.append(materialize_track_aliases([local_track], batch_size=1))
            except Exception as exc:  # pragma: no cover - assertion reports thread failures
                errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=materialize) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(errors, [])
        self.assertEqual(sorted(result.created_count for result in results), [0, 1])
        self.assertEqual(CanonicalItemAlias.objects.filter(source='spotify', source_id=track.spotify_id).count(), 1)


class CanonicalAliasMaterializationRunTests(TransactionTestCase):
    def test_failed_command_persists_checkpoint_and_resumes(self):
        for index in range(2):
            identity = identity_from_parts(item_type=ITEM_TYPE_RECORDING_MSID, key_value=str(uuid.uuid4()))
            CanonicalItem.objects.create(
                id=identity.item_id,
                item_type=identity.item_type,
                canonical_key=identity.canonical_key,
            )

        from mlcore.services import canonical_items

        original = canonical_items._materialize_canonical_item_alias_batch
        processed_calls = 0

        def fail_after_first_batch(*args, **kwargs):
            nonlocal processed_calls
            result = original(*args, **kwargs)
            if result[2] > 0:
                processed_calls += 1
            if processed_calls == 2:
                raise RuntimeError('simulated interruption')
            return result

        with TemporaryDirectory() as temp_dir:
            metrics_path = Path(temp_dir) / 'aliases.prom'
            with self.assertRaisesMessage(RuntimeError, 'simulated interruption'):
                with mock.patch.object(
                    canonical_items,
                    '_materialize_canonical_item_alias_batch',
                    side_effect=fail_after_first_batch,
                ):
                    call_command(
                        'materialize_canonical_aliases',
                        source_version='resume-test',
                        batch_size=1,
                        metrics_path=str(metrics_path),
                    )

            run = CanonicalAliasMaterializationRun.objects.get(source_version='resume-test')
            self.assertEqual(run.status, 'failed')
            self.assertEqual(run.processed_items, 1)
            self.assertTrue(run.checkpoints['canonical'][ITEM_TYPE_RECORDING_MSID])

            call_command(
                'materialize_canonical_aliases',
                resume_run_id=run.id,
                metrics_path=str(metrics_path),
            )

        run.refresh_from_db()
        self.assertEqual(run.status, 'succeeded')
        self.assertEqual(run.processed_items, 2)
        self.assertEqual(run.created_count, 2)
        self.assertEqual(run.batches_processed, 2)
        self.assertEqual(run.checkpoints['canonical_complete'], True)
        self.assertEqual(CanonicalItemAlias.objects.filter(source='listenbrainz').count(), 2)

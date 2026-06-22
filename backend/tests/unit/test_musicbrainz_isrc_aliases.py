import io
import json
import uuid

from django.core.management import call_command
from django.test import TestCase

from mlcore.models import (
    CanonicalAliasMaterializationRun,
    CanonicalItem,
    CanonicalItemAlias,
    MusicBrainzRecordingISRC,
    SourceIngestionRun,
)
from mlcore.services.canonical_items import identity_from_parts
from mlcore.services.musicbrainz_isrc_aliases import (
    ALGORITHM_VERSION,
    materialize_musicbrainz_isrc_alias_batch,
)


class MusicBrainzISRCAliasTests(TestCase):
    source_version = 'musicbrainz-test-v1'

    def setUp(self):
        self.mbid_one = uuid.uuid4()
        self.mbid_two = uuid.uuid4()
        self.mbid_missing = uuid.uuid4()
        self.item_one = self._create_mbid_item(self.mbid_one)
        self.item_two = self._create_mbid_item(self.mbid_two)
        MusicBrainzRecordingISRC.objects.bulk_create([
            self._evidence(self.mbid_one, 'USAAA2400001'),
            self._evidence(self.mbid_one, 'USAAA2400002'),
            self._evidence(self.mbid_one, 'USAAA2400003'),
            self._evidence(self.mbid_two, 'USAAA2400003'),
            self._evidence(self.mbid_missing, 'USAAA2400004'),
        ])

    def _create_mbid_item(self, mbid):
        identity = identity_from_parts(item_type='recording_mbid', key_value=mbid)
        return CanonicalItem.objects.create(
            id=identity.item_id,
            item_type=identity.item_type,
            canonical_key=identity.canonical_key,
        )

    def _evidence(self, mbid, isrc):
        return MusicBrainzRecordingISRC(
            recording_mbid=mbid,
            isrc=isrc,
            source_version=self.source_version,
        )

    def test_materializes_unique_isrcs_and_excludes_ambiguous_or_unresolved(self):
        first = materialize_musicbrainz_isrc_alias_batch(
            source_version=self.source_version,
            last_isrc=None,
            batch_size=10,
        )
        second = materialize_musicbrainz_isrc_alias_batch(
            source_version=self.source_version,
            last_isrc=None,
            batch_size=10,
        )

        self.assertEqual(first.processed_count, 4)
        self.assertEqual(first.created_count, 2)
        self.assertEqual(first.ambiguous_count, 1)
        self.assertEqual(first.unresolved_count, 1)
        self.assertEqual(first.existing_alias_conflict_count, 0)
        self.assertEqual(second.created_count, 0)
        self.assertEqual(second.existing_count, 2)
        self.assertEqual(CanonicalItemAlias.objects.filter(source='isrc').count(), 2)
        alias = CanonicalItemAlias.objects.get(source='isrc', source_id='USAAA2400001')
        self.assertEqual(alias.canonical_item, self.item_one)
        self.assertEqual(alias.metadata['match_source'], 'musicbrainz')

    def test_existing_alias_is_not_reassigned_on_conflict(self):
        CanonicalItemAlias.objects.create(
            canonical_item=self.item_two,
            source='isrc',
            resource_type='recording',
            source_id='USAAA2400001',
        )

        result = materialize_musicbrainz_isrc_alias_batch(
            source_version=self.source_version,
            last_isrc=None,
            batch_size=10,
        )

        self.assertEqual(result.existing_alias_conflict_count, 1)
        alias = CanonicalItemAlias.objects.get(source='isrc', source_id='USAAA2400001')
        self.assertEqual(alias.canonical_item, self.item_two)

    def test_batches_resume_after_last_isrc(self):
        first = materialize_musicbrainz_isrc_alias_batch(
            source_version=self.source_version,
            last_isrc=None,
            batch_size=2,
        )
        second = materialize_musicbrainz_isrc_alias_batch(
            source_version=self.source_version,
            last_isrc=first.last_isrc,
            batch_size=2,
        )
        complete = materialize_musicbrainz_isrc_alias_batch(
            source_version=self.source_version,
            last_isrc=second.last_isrc,
            batch_size=2,
        )

        self.assertEqual(first.processed_count, 2)
        self.assertEqual(second.processed_count, 2)
        self.assertEqual(complete.processed_count, 0)

    def test_command_persists_checkpoint_and_resumes(self):
        SourceIngestionRun.objects.create(
            source='musicbrainz-identity-bridge',
            import_mode='full',
            source_version=self.source_version,
            raw_path='/tmp/musicbrainz.tar.bz2',
            checksum='checksum',
            status='succeeded',
        )
        first_output = io.StringIO()
        call_command(
            'materialize_musicbrainz_isrc_aliases',
            '--batch-size',
            '2',
            '--max-batches',
            '1',
            '--json',
            '--metrics-path',
            '',
            stdout=first_output,
        )
        first_payload = json.loads(first_output.getvalue())
        run = CanonicalAliasMaterializationRun.objects.get(pk=first_payload['run_id'])

        self.assertEqual(run.algorithm_version, ALGORITHM_VERSION)
        self.assertEqual(run.status, 'pending')
        self.assertEqual(run.processed_items, 2)

        second_output = io.StringIO()
        call_command(
            'materialize_musicbrainz_isrc_aliases',
            '--resume-run-id',
            str(run.id),
            '--json',
            '--metrics-path',
            '',
            stdout=second_output,
        )
        run.refresh_from_db()
        self.assertEqual(run.status, 'succeeded')
        self.assertEqual(run.processed_items, 4)

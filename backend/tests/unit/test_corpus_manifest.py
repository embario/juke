import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from mlcore.models import CorpusManifest
from tests.utils import create_album, create_track


def _mk_row(**overrides):
    defaults = dict(
        source='musicbrainz',
        track_path='/corpus/mb/001.flac',
        license='CC-BY-4.0',
        allowed_envs='production',
        checksum='sha256:abc123',
    )
    defaults.update(overrides)
    return CorpusManifest.objects.create(**defaults)


class CorpusManifestTests(TestCase):

    def test_minimal_create(self):
        row = _mk_row()
        self.assertIsNotNone(row.id)
        self.assertIsNotNone(row.ingested_at)
        self.assertEqual(row.source, 'musicbrainz')

    def test_unique_together_source_path_checksum(self):
        _mk_row()
        with self.assertRaises(IntegrityError):
            _mk_row()

    def test_same_path_different_checksum_allowed(self):
        _mk_row(checksum='sha256:aaa')
        _mk_row(checksum='sha256:bbb')
        self.assertEqual(CorpusManifest.objects.count(), 2)

    def test_allowed_envs_choices_validation(self):
        row = CorpusManifest(
            source='musicbrainz',
            track_path='/x.flac',
            license='CC-BY-4.0',
            allowed_envs='invalid-env',
            checksum='sha256:xyz',
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_track_fk_is_nullable(self):
        row = _mk_row()
        self.assertIsNone(row.track)

    def test_track_fk_uses_juke_id(self):
        album = create_album(name='A', total_tracks=1, release_date=datetime.date(2020, 1, 1))
        track = create_track(name='T', album=album, track_number=1, duration_ms=180000)
        row = _mk_row(track=track)
        # FK column stores juke_id (UUID), not the auto-PK int
        self.assertEqual(row.track_id, track.juke_id)

    def test_track_delete_sets_null(self):
        album = create_album(name='A', total_tracks=1, release_date=datetime.date(2020, 1, 1))
        track = create_track(name='T', album=album, track_number=1, duration_ms=180000)
        row = _mk_row(track=track)
        track.delete()
        row.refresh_from_db()
        self.assertIsNone(row.track)
        # Manifest row survives
        self.assertTrue(CorpusManifest.objects.filter(pk=row.pk).exists())

    def test_reverse_relation_from_track(self):
        album = create_album(name='A', total_tracks=1, release_date=datetime.date(2020, 1, 1))
        track = create_track(name='T', album=album, track_number=1, duration_ms=180000)
        _mk_row(track=track)
        _mk_row(track=track, checksum='sha256:other')
        self.assertEqual(track.corpus_manifest_entries.count(), 2)

"""Metadata-only backfill from an existing verified dump; never reloads identity facts or listens."""

import tarfile
from pathlib import Path

from django.db import connection, transaction
from mlcore.models import MusicBrainzRecordingMetadata

from mlcore.services.musicbrainz_bridge import (
    _load_manifest,
    _core_artifact,
    _validate_archive,
    _member_rows,
    _copy_rows,
)


def import_recording_metadata(manifest_path, *, progress=None):
    manifest_path = Path(manifest_path)
    manifest = _load_manifest(manifest_path)
    artifact = _core_artifact(manifest, manifest_path)
    archive_path = Path(artifact['path'])
    _validate_archive(archive_path, artifact['sha256'])
    version = manifest['source_version']
    if MusicBrainzRecordingMetadata.objects.filter(source_version=version).exclude(source_checksum=artifact['sha256']).exists():
        raise ValueError('Source version already has metadata from a different checksum')
    # Session-local tables keep this separate from the bridge's shared staging and checkpoints.
    with connection.cursor() as c:
        c.execute('DROP TABLE IF EXISTS tmp_mb_metadata_recording, tmp_mb_metadata_credit')
        c.execute("""CREATE TEMP TABLE tmp_mb_metadata_recording
            (recording_mbid uuid, title text, artist_credit_id bigint, duration_ms integer)""")
        c.execute('CREATE TEMP TABLE tmp_mb_metadata_credit (id bigint, name text)')
    loaded = set()
    try:
        with tarfile.open(archive_path, mode='r|bz2') as ar:
            for member in ar:
                name = member.name.removeprefix('./')
                if name not in {'mbdump/recording', 'mbdump/artist_credit'} or not member.isfile():
                    continue
                if name in loaded:
                    raise ValueError('Duplicate metadata archive member: ' + name)
                rows = _member_rows(ar.extractfile(member))
                if name == 'mbdump/recording':
                    _copy_rows(
                        'tmp_mb_metadata_recording',
                        ('recording_mbid', 'title', 'artist_credit_id', 'duration_ms'),
                        ((r[1], r[2], r[3], r[4]) for r in rows if len(r) >= 5),
                    )
                else:
                    _copy_rows('tmp_mb_metadata_credit', ('id', 'name'), ((r[0], r[1]) for r in rows if len(r) >= 2))
                loaded.add(name)
                if progress:
                    progress({'event': 'metadata_member_complete', 'member': name})
                if len(loaded) == 2:
                    break
        if len(loaded) != 2:
            raise ValueError('Recording metadata requires recording and artist_credit archive members')
        with transaction.atomic(), connection.cursor() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ['mlcore-recording-metadata:' + version])
            if MusicBrainzRecordingMetadata.objects.filter(source_version=version).exclude(source_checksum=artifact['sha256']).exists():
                raise ValueError('Source version already has metadata from a different checksum')
            c.execute('ANALYZE tmp_mb_metadata_recording')
            c.execute('ANALYZE tmp_mb_metadata_credit')
            c.execute(
                """INSERT INTO mlcore_musicbrainz_recording_metadata
                (recording_mbid, source_version, source_checksum, title, artist_credit, duration_ms, created_at)
                SELECT r.recording_mbid, %s, %s, r.title, a.name, r.duration_ms, NOW()
                FROM tmp_mb_metadata_recording r JOIN tmp_mb_metadata_credit a ON a.id = r.artist_credit_id
                JOIN (SELECT recording_mbid FROM mlcore_musicbrainz_recording_isrc WHERE source_version = %s
                      UNION SELECT recording_mbid FROM mlcore_musicbrainz_recording_url WHERE source_version = %s) targets
                  ON targets.recording_mbid = r.recording_mbid
                ON CONFLICT (recording_mbid, source_version) DO NOTHING""",
                [version, artifact['sha256'], version, version],
            )
            inserted = c.rowcount
        return {'source_version': version, 'inserted_metadata': inserted, 'identity_facts_changed': 0}
    finally:
        with connection.cursor() as c:
            c.execute('DROP TABLE IF EXISTS tmp_mb_metadata_recording, tmp_mb_metadata_credit')

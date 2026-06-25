from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from django.db import connection
from django.utils import timezone

from mlcore.models import SourceIngestionRun
from mlcore.services.musicbrainz_source import CORE_ARTIFACT_NAME, MUSICBRAINZ_SOURCE_ID

BRIDGE_SOURCE_ID = 'musicbrainz-identity-bridge'
ISRC_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$')
COPY_BATCH_SIZE = 100_000

STAGING_TABLES = (
    'mlcore_mb_recording_stage',
    'mlcore_mb_isrc_stage',
    'mlcore_mb_url_stage',
    'mlcore_mb_recording_url_stage',
    'mlcore_mb_link_stage',
    'mlcore_mb_link_type_stage',
)


@dataclass(frozen=True)
class MusicBrainzBridgeResult:
    run_id: str
    source_version: str
    recording_rows: int
    isrc_rows: int
    valid_isrc_rows: int
    malformed_isrc_rows: int
    duplicate_isrc_rows: int
    unique_recordings_with_isrc: int
    inserted_isrc_rows: int
    url_relationship_rows: int
    extracted_url_rows: int
    inserted_url_rows: int


def import_musicbrainz_bridge(
    manifest_path: str | Path,
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> MusicBrainzBridgeResult:
    manifest_path = Path(manifest_path)
    manifest = _load_manifest(manifest_path)
    source_version = str(manifest['source_version'])
    artifact = _core_artifact(manifest, manifest_path)
    checksum = str(artifact['sha256'])
    archive_path = Path(artifact['path'])
    _validate_archive(archive_path, checksum)

    run = SourceIngestionRun.objects.create(
        source=BRIDGE_SOURCE_ID,
        import_mode='full',
        source_version=source_version,
        raw_path=str(archive_path),
        checksum=checksum,
        fingerprint=_manifest_fingerprint(manifest),
        status='running',
        policy_classification='production_approved',
        metadata={
            'phase': 'identity_bridge',
            'manifest_path': str(manifest_path),
            'staging_tables': list(STAGING_TABLES),
            'tablespace': 'juke_mlcore_cold',
        },
    )

    counters: dict[str, int] = {
        'recording_rows': 0,
        'isrc_rows': 0,
        'valid_isrc_rows': 0,
        'malformed_isrc_rows': 0,
        'url_rows': 0,
        'url_relationship_rows': 0,
        'link_rows': 0,
        'link_type_rows': 0,
    }
    try:
        _truncate_staging_tables()
        _load_archive(archive_path, counters, progress_callback)

        summary = _materialize_bridge(source_version)
        metadata = {
            **run.metadata,
            **counters,
            **summary,
        }
        run.status = 'succeeded'
        run.source_row_count = counters['recording_rows'] + counters['isrc_rows']
        run.imported_row_count = summary['inserted_isrc_rows'] + summary['inserted_url_rows']
        run.duplicate_row_count = summary['duplicate_isrc_rows']
        run.canonicalized_row_count = summary['unique_recordings_with_isrc']
        run.malformed_row_count = counters['malformed_isrc_rows']
        run.metadata = metadata
        run.completed_at = timezone.now()
        run.save(update_fields=[
            'status',
            'source_row_count',
            'imported_row_count',
            'duplicate_row_count',
            'canonicalized_row_count',
            'malformed_row_count',
            'metadata',
            'completed_at',
        ])
        return MusicBrainzBridgeResult(
            run_id=str(run.id),
            source_version=source_version,
            recording_rows=counters['recording_rows'],
            isrc_rows=counters['isrc_rows'],
            valid_isrc_rows=counters['valid_isrc_rows'],
            malformed_isrc_rows=counters['malformed_isrc_rows'],
            duplicate_isrc_rows=summary['duplicate_isrc_rows'],
            unique_recordings_with_isrc=summary['unique_recordings_with_isrc'],
            inserted_isrc_rows=summary['inserted_isrc_rows'],
            url_relationship_rows=counters['url_relationship_rows'],
            extracted_url_rows=summary['extracted_url_rows'],
            inserted_url_rows=summary['inserted_url_rows'],
        )
    except Exception as exc:
        run.status = 'failed'
        run.last_error = str(exc)
        run.metadata = {**run.metadata, **counters}
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'last_error', 'metadata', 'completed_at'])
        raise


def classify_provider(url: str) -> str:
    host = url.lower()
    providers = (
        ('spotify', ('open.spotify.com/', 'spotify.com/track/')),
        ('apple_music', ('music.apple.com/', 'itunes.apple.com/')),
        ('youtube', ('youtube.com/', 'youtu.be/')),
        ('soundcloud', ('soundcloud.com/',)),
        ('bandcamp', ('bandcamp.com/',)),
        ('deezer', ('deezer.com/',)),
        ('tidal', ('tidal.com/',)),
    )
    for provider, needles in providers:
        if any(needle in host for needle in needles):
            return provider
    return 'other'


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f'MusicBrainz manifest does not exist: {path}')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('source') != MUSICBRAINZ_SOURCE_ID:
        raise ValueError(f'Unexpected MusicBrainz manifest source: {manifest.get("source")!r}')
    if not manifest.get('source_version'):
        raise ValueError('MusicBrainz manifest is missing source_version')
    return manifest


def _core_artifact(manifest: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    for artifact in manifest.get('artifacts', []):
        if artifact.get('name') == CORE_ARTIFACT_NAME:
            artifact = dict(artifact)
            path = Path(str(artifact.get('path', '')))
            if not path.is_absolute():
                path = manifest_path.parent / path
            artifact['path'] = str(path)
            return artifact
    raise ValueError(f'MusicBrainz manifest does not contain {CORE_ARTIFACT_NAME}')


def _validate_archive(path: Path, expected_checksum: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f'MusicBrainz archive does not exist: {path}')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected_checksum:
        raise ValueError(f'MusicBrainz archive checksum mismatch: {path}')


def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
    stable = {
        'source': manifest['source'],
        'source_version': manifest['source_version'],
        'artifacts': [
            {'name': artifact.get('name'), 'sha256': artifact.get('sha256')}
            for artifact in manifest.get('artifacts', [])
        ],
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def _truncate_staging_tables() -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'TRUNCATE TABLE {", ".join(STAGING_TABLES)}')


def _member_rows(extracted: Any) -> Iterator[list[str | None]]:
    lines = (line.decode('utf-8', errors='replace') for line in extracted)
    for row in csv.reader(lines, delimiter='\t', quoting=csv.QUOTE_NONE):
        yield [_decode_copy_value(value) for value in row]


def _decode_copy_value(value: str) -> str | None:
    if value == r'\N':
        return None
    replacements = {
        r'\t': '\t',
        r'\n': '\n',
        r'\r': '\r',
        r'\b': '\b',
        r'\f': '\f',
        r'\v': '\v',
        r'\\': '\\',
    }
    return re.sub(r'\\(?:[tnrbfv\\])', lambda match: replacements[match.group(0)], value)


def _load_archive(
    archive_path: Path,
    counters: dict[str, int],
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> None:
    loaders = {
        'mbdump/recording': _load_recordings,
        'mbdump/isrc': _load_isrcs,
        'mbdump/url': _load_urls,
        'mbdump/l_recording_url': _load_recording_urls,
        'mbdump/link': _load_links,
        'mbdump/link_type': _load_link_types,
    }
    loaded: set[str] = set()
    with tarfile.open(archive_path, mode='r|bz2') as archive:
        for member in archive:
            name = member.name.removeprefix('./')
            loader = loaders.get(name)
            if loader is None or not member.isfile():
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f'Unable to read MusicBrainz member: {name}')
            loader(extracted, counters)
            loaded.add(name)
            _report(progress_callback, name.removeprefix('mbdump/'), counters)
    missing = sorted(set(loaders) - loaded)
    if missing:
        raise ValueError(f'MusicBrainz archive is missing bridge members: {", ".join(missing)}')


def _load_recordings(extracted: Any, counters: dict[str, int]) -> None:
    def rows() -> Iterator[tuple[Any, ...]]:
        for row in _member_rows(extracted):
            counters['recording_rows'] += 1
            if len(row) >= 2 and row[0] and row[1]:
                yield row[0], row[1]

    _copy_rows('mlcore_mb_recording_stage', ('recording_id', 'recording_mbid'), rows())


def _load_isrcs(extracted: Any, counters: dict[str, int]) -> None:
    def rows() -> Iterator[tuple[Any, ...]]:
        for row in _member_rows(extracted):
            counters['isrc_rows'] += 1
            isrc = str(row[2]).upper() if len(row) >= 3 and row[2] else ''
            if len(row) < 3 or not row[1] or not ISRC_RE.fullmatch(isrc):
                counters['malformed_isrc_rows'] += 1
                continue
            counters['valid_isrc_rows'] += 1
            yield row[1], isrc

    _copy_rows('mlcore_mb_isrc_stage', ('recording_id', 'isrc'), rows())


def _load_urls(extracted: Any, counters: dict[str, int]) -> None:
    def rows() -> Iterator[tuple[Any, ...]]:
        for row in _member_rows(extracted):
            counters['url_rows'] += 1
            if len(row) >= 3 and row[0] and row[2]:
                yield row[0], row[2]

    _copy_rows('mlcore_mb_url_stage', ('url_id', 'url'), rows())


def _load_recording_urls(extracted: Any, counters: dict[str, int]) -> None:
    def rows() -> Iterator[tuple[Any, ...]]:
        for row in _member_rows(extracted):
            counters['url_relationship_rows'] += 1
            if len(row) >= 4 and row[1] and row[2] and row[3]:
                yield row[1], row[2], row[3]

    _copy_rows(
        'mlcore_mb_recording_url_stage',
        ('link_id', 'recording_id', 'url_id'),
        rows(),
    )


def _load_links(extracted: Any, counters: dict[str, int]) -> None:
    def rows() -> Iterator[tuple[Any, ...]]:
        for row in _member_rows(extracted):
            counters['link_rows'] += 1
            if len(row) >= 2 and row[0] and row[1]:
                yield row[0], row[1]

    _copy_rows('mlcore_mb_link_stage', ('link_id', 'link_type_id'), rows())


def _load_link_types(extracted: Any, counters: dict[str, int]) -> None:
    def rows() -> Iterator[tuple[Any, ...]]:
        for row in _member_rows(extracted):
            counters['link_type_rows'] += 1
            if len(row) >= 7 and row[0] and row[4] and row[5] and row[6]:
                yield row[0], row[4], row[5], row[6]

    _copy_rows(
        'mlcore_mb_link_type_stage',
        ('link_type_id', 'entity_type0', 'entity_type1', 'name'),
        rows(),
    )


def _copy_rows(table: str, columns: tuple[str, ...], rows: Iterable[tuple[Any, ...]]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    buffered = 0
    for row in rows:
        writer.writerow(row)
        buffered += 1
        if buffered >= COPY_BATCH_SIZE:
            _copy_buffer(table, columns, buffer)
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator='\n')
            buffered = 0
    if buffered:
        _copy_buffer(table, columns, buffer)


def _copy_buffer(table: str, columns: tuple[str, ...], buffer: io.StringIO) -> None:
    buffer.seek(0)
    sql = f'COPY {table} ({", ".join(columns)}) FROM STDIN WITH (FORMAT csv)'
    connection.ensure_connection()
    with connection.cursor() as cursor:
        raw_cursor = getattr(cursor, 'cursor', cursor)
        if hasattr(raw_cursor, 'copy_expert'):
            raw_cursor.copy_expert(sql, buffer)
            return
    raise RuntimeError('MusicBrainz bridge import requires PostgreSQL COPY support')


def _materialize_bridge(source_version: str) -> dict[str, int]:
    with connection.cursor() as cursor:
        cursor.execute('''
            SELECT COUNT(*) - COUNT(DISTINCT (recording_id, isrc))
            FROM mlcore_mb_isrc_stage
        ''')
        duplicate_isrc_rows = cursor.fetchone()[0]

        cursor.execute('''
            SELECT COUNT(DISTINCT r.recording_mbid)
            FROM mlcore_mb_isrc_stage i
            JOIN mlcore_mb_recording_stage r ON r.recording_id = i.recording_id
        ''')
        unique_recordings_with_isrc = cursor.fetchone()[0]

        cursor.execute('''
            INSERT INTO mlcore_musicbrainz_recording_isrc
                (recording_mbid, isrc, source_version, created_at)
            SELECT DISTINCT r.recording_mbid, i.isrc, %s, NOW()
            FROM mlcore_mb_isrc_stage i
            JOIN mlcore_mb_recording_stage r ON r.recording_id = i.recording_id
            ON CONFLICT (recording_mbid, isrc, source_version) DO NOTHING
        ''', [source_version])
        inserted_isrc_rows = max(cursor.rowcount, 0)

        cursor.execute('''
            SELECT COUNT(DISTINCT (r.recording_mbid, u.url))
            FROM mlcore_mb_recording_url_stage ru
            JOIN mlcore_mb_recording_stage r ON r.recording_id = ru.recording_id
            JOIN mlcore_mb_url_stage u ON u.url_id = ru.url_id
            JOIN mlcore_mb_link_stage l ON l.link_id = ru.link_id
            JOIN mlcore_mb_link_type_stage lt ON lt.link_type_id = l.link_type_id
        ''')
        extracted_url_rows = cursor.fetchone()[0]

        cursor.execute('''
            INSERT INTO mlcore_musicbrainz_recording_url
                (recording_mbid, url, url_fingerprint, provider, link_type_id,
                 link_type_name, source_version, created_at)
            SELECT DISTINCT ON (r.recording_mbid, md5(u.url))
                r.recording_mbid,
                u.url,
                md5(u.url),
                CASE
                    WHEN lower(u.url) LIKE '%%open.spotify.com/%%'
                      OR lower(u.url) LIKE '%%spotify.com/track/%%' THEN 'spotify'
                    WHEN lower(u.url) LIKE '%%music.apple.com/%%'
                      OR lower(u.url) LIKE '%%itunes.apple.com/%%' THEN 'apple_music'
                    WHEN lower(u.url) LIKE '%%youtube.com/%%'
                      OR lower(u.url) LIKE '%%youtu.be/%%' THEN 'youtube'
                    WHEN lower(u.url) LIKE '%%soundcloud.com/%%' THEN 'soundcloud'
                    WHEN lower(u.url) LIKE '%%bandcamp.com/%%' THEN 'bandcamp'
                    WHEN lower(u.url) LIKE '%%deezer.com/%%' THEN 'deezer'
                    WHEN lower(u.url) LIKE '%%tidal.com/%%' THEN 'tidal'
                    ELSE 'other'
                END,
                lt.link_type_id,
                lt.name,
                %s,
                NOW()
            FROM mlcore_mb_recording_url_stage ru
            JOIN mlcore_mb_recording_stage r ON r.recording_id = ru.recording_id
            JOIN mlcore_mb_url_stage u ON u.url_id = ru.url_id
            JOIN mlcore_mb_link_stage l ON l.link_id = ru.link_id
            JOIN mlcore_mb_link_type_stage lt ON lt.link_type_id = l.link_type_id
            ORDER BY r.recording_mbid, md5(u.url), lt.link_type_id
            ON CONFLICT (recording_mbid, url_fingerprint, source_version) DO NOTHING
        ''', [source_version])
        inserted_url_rows = max(cursor.rowcount, 0)

    return {
        'duplicate_isrc_rows': duplicate_isrc_rows,
        'unique_recordings_with_isrc': unique_recordings_with_isrc,
        'inserted_isrc_rows': inserted_isrc_rows,
        'extracted_url_rows': extracted_url_rows,
        'inserted_url_rows': inserted_url_rows,
    }


def _report(
    callback: Callable[[dict[str, Any]], None] | None,
    member: str,
    counters: dict[str, int],
) -> None:
    if callback:
        callback({'member': member, **counters})

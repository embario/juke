from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import Track
from catalog.services.identity import IdentityResolver
from mlcore.models import ListenBrainzRawListen, NormalizedInteraction, SourceIngestionRun
from mlcore.services.corpus import LicensePolicy

logger = logging.getLogger(__name__)

LISTENBRAINZ_SOURCE_ID = 'listenbrainz'
DEFAULT_BATCH_SIZE = 500
DEFAULT_SESSION_WINDOW_SECONDS = 30 * 60
SUPPORTED_JSON_LINE_SUFFIXES = ('.jsonl', '.ndjson', '.json')
SPOTIFY_ID_KEYS = (
    'spotify_id',
    'spotify_track_id',
    'submission_client_track_id',
    'media_player_track_id',
)


@dataclass(frozen=True)
class ParsedListen:
    source_user_id: str
    played_at: datetime
    session_hint: str
    source_event_signature: str
    track_identifier_candidates: dict[str, Any]
    payload: dict[str, Any]
    metadata: dict[str, Any]
    recording_mbid: UUID | None
    release_mbid: UUID | None
    recording_msid: str
    release_msid: str
    track_name: str
    artist_name: str
    release_name: str


@dataclass(frozen=True)
class ImportResult:
    run_id: UUID
    status: str
    source_row_count: int
    imported_row_count: int
    duplicate_row_count: int
    canonicalized_row_count: int
    unresolved_row_count: int
    malformed_row_count: int
    checksum: str


def import_listenbrainz_dump(
    dump_path: str | Path,
    *,
    source_version: str,
    import_mode: str = 'full',
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ImportResult:
    path = Path(dump_path)
    if not path.exists():
        raise FileNotFoundError(f'ListenBrainz dump not found: {path}')

    checksum = _sha256_file(path)
    policy = LicensePolicy()
    classification = policy.classify_source(LISTENBRAINZ_SOURCE_ID)
    if classification == 'blocked':
        raise ValueError('ListenBrainz source is blocked by current MLCore policy configuration')

    run = SourceIngestionRun.objects.create(
        source=LISTENBRAINZ_SOURCE_ID,
        import_mode=import_mode,
        source_version=source_version,
        raw_path=str(path),
        checksum=checksum,
        status='running',
        policy_classification=classification,
    )

    try:
        with transaction.atomic():
            counts = _ingest_dump(path, run, source_version=source_version, batch_size=batch_size)
        run.status = 'succeeded'
        run.source_row_count = counts['source_row_count']
        run.imported_row_count = counts['imported_row_count']
        run.duplicate_row_count = counts['duplicate_row_count']
        run.canonicalized_row_count = counts['canonicalized_row_count']
        run.unresolved_row_count = counts['unresolved_row_count']
        run.malformed_row_count = counts['malformed_row_count']
        run.completed_at = timezone.now()
        run.metadata = {
            **run.metadata,
            'batch_size': batch_size,
            'session_window_seconds': getattr(
                settings,
                'MLCORE_LISTENBRAINZ_SESSION_WINDOW_SECONDS',
                DEFAULT_SESSION_WINDOW_SECONDS,
            ),
        }
        run.save(
            update_fields=[
                'status', 'source_row_count', 'imported_row_count', 'duplicate_row_count',
                'canonicalized_row_count', 'unresolved_row_count', 'malformed_row_count',
                'completed_at', 'metadata',
            ]
        )
    except Exception as exc:
        run.status = 'failed'
        run.completed_at = timezone.now()
        run.last_error = str(exc)
        run.save(update_fields=['status', 'completed_at', 'last_error'])
        raise

    logger.info(
        'listenbrainz import finished run=%s mode=%s source_rows=%d imported=%d duplicates=%d malformed=%d',
        run.pk,
        import_mode,
        run.source_row_count,
        run.imported_row_count,
        run.duplicate_row_count,
        run.malformed_row_count,
    )
    return ImportResult(
        run_id=run.pk,
        status=run.status,
        source_row_count=run.source_row_count,
        imported_row_count=run.imported_row_count,
        duplicate_row_count=run.duplicate_row_count,
        canonicalized_row_count=run.canonicalized_row_count,
        unresolved_row_count=run.unresolved_row_count,
        malformed_row_count=run.malformed_row_count,
        checksum=run.checksum,
    )


def configured_dump_path(import_mode: str) -> str | None:
    if import_mode == 'full':
        return getattr(settings, 'MLCORE_LISTENBRAINZ_FULL_IMPORT_PATH', '') or None
    if import_mode == 'incremental':
        return getattr(settings, 'MLCORE_LISTENBRAINZ_INCREMENTAL_IMPORT_PATH', '') or None
    raise ValueError(f"Unknown import_mode '{import_mode}'")


def configured_source_version(import_mode: str, dump_path: str | Path) -> str:
    if import_mode == 'full':
        configured = getattr(settings, 'MLCORE_LISTENBRAINZ_FULL_SOURCE_VERSION', '')
    elif import_mode == 'incremental':
        configured = getattr(settings, 'MLCORE_LISTENBRAINZ_INCREMENTAL_SOURCE_VERSION', '')
    else:
        raise ValueError(f"Unknown import_mode '{import_mode}'")

    if configured:
        return configured

    return Path(dump_path).name


def _ingest_dump(
    dump_path: Path,
    run: SourceIngestionRun,
    *,
    source_version: str,
    batch_size: int,
) -> dict[str, int]:
    resolution_cache: dict[tuple[str, str], UUID | None] = {}
    counts = {
        'source_row_count': 0,
        'imported_row_count': 0,
        'duplicate_row_count': 0,
        'canonicalized_row_count': 0,
        'unresolved_row_count': 0,
        'malformed_row_count': 0,
    }
    max_malformed = getattr(settings, 'MLCORE_LISTENBRAINZ_MAX_MALFORMED_ROWS', 0)
    parsed_batch: list[ParsedListen] = []
    seen_in_batch: set[str] = set()

    for payload, error in _iter_listen_payloads(dump_path):
        if error:
            counts['malformed_row_count'] += 1
            if counts['malformed_row_count'] > max_malformed:
                raise ValueError(error)
            continue

        counts['source_row_count'] += 1
        try:
            parsed = _parse_listen(payload)
        except ValueError as exc:
            counts['malformed_row_count'] += 1
            if counts['malformed_row_count'] > max_malformed:
                raise ValueError(str(exc)) from exc
            continue

        if parsed.source_event_signature in seen_in_batch:
            counts['duplicate_row_count'] += 1
            continue

        seen_in_batch.add(parsed.source_event_signature)
        parsed_batch.append(parsed)
        if len(parsed_batch) >= batch_size:
            _flush_batch(
                run,
                source_version=source_version,
                parsed_batch=parsed_batch,
                counts=counts,
                resolution_cache=resolution_cache,
            )
            parsed_batch.clear()
            seen_in_batch.clear()

    if parsed_batch:
        _flush_batch(
            run,
            source_version=source_version,
            parsed_batch=parsed_batch,
            counts=counts,
            resolution_cache=resolution_cache,
        )

    if counts['source_row_count'] == 0:
        raise ValueError(f'No listen events found in {dump_path}')

    return counts


def _flush_batch(
    run: SourceIngestionRun,
    *,
    source_version: str,
    parsed_batch: list[ParsedListen],
    counts: dict[str, int],
    resolution_cache: dict[tuple[str, str], UUID | None],
) -> None:
    signatures = [parsed.source_event_signature for parsed in parsed_batch]
    existing_signatures = set(
        ListenBrainzRawListen.objects.filter(source_event_signature__in=signatures).values_list(
            'source_event_signature',
            flat=True,
        )
    )

    new_listens = [parsed for parsed in parsed_batch if parsed.source_event_signature not in existing_signatures]
    counts['duplicate_row_count'] += len(parsed_batch) - len(new_listens)
    if not new_listens:
        return

    raw_rows = [
        ListenBrainzRawListen(
            import_run=run,
            source_event_signature=parsed.source_event_signature,
            source_user_id=parsed.source_user_id,
            played_at=parsed.played_at,
            recording_mbid=parsed.recording_mbid,
            release_mbid=parsed.release_mbid,
            recording_msid=parsed.recording_msid,
            release_msid=parsed.release_msid,
            track_name=parsed.track_name,
            artist_name=parsed.artist_name,
            release_name=parsed.release_name,
            track_identifier_candidates=parsed.track_identifier_candidates,
            payload=parsed.payload,
        )
        for parsed in new_listens
    ]
    created_rows = ListenBrainzRawListen.objects.bulk_create(raw_rows)
    raw_by_signature = {row.source_event_signature: row for row in created_rows}

    normalized_rows: list[NormalizedInteraction] = []
    unresolved = 0
    for parsed in new_listens:
        track_juke_id = _resolve_track_juke_id(parsed.track_identifier_candidates, resolution_cache)
        if track_juke_id is None:
            unresolved += 1
        normalized_rows.append(
            NormalizedInteraction(
                import_run=run,
                raw_listen=raw_by_signature[parsed.source_event_signature],
                track_id=track_juke_id,
                source_id=LISTENBRAINZ_SOURCE_ID,
                source_version=source_version,
                source_event_signature=parsed.source_event_signature,
                source_user_id=parsed.source_user_id,
                played_at=parsed.played_at,
                session_hint=parsed.session_hint,
                track_identifier_candidates=parsed.track_identifier_candidates,
                metadata=parsed.metadata,
            )
        )

    NormalizedInteraction.objects.bulk_create(normalized_rows)

    counts['imported_row_count'] += len(created_rows)
    counts['canonicalized_row_count'] += len(normalized_rows)
    counts['unresolved_row_count'] += unresolved


def _resolve_track_juke_id(
    candidates: dict[str, Any],
    resolution_cache: dict[tuple[str, str], UUID | None],
) -> UUID | None:
    recording_mbid = str(candidates.get('recording_mbid') or '').strip()
    if recording_mbid:
        cache_key = ('mbid', recording_mbid)
        if cache_key not in resolution_cache:
            track = IdentityResolver.resolve_track(mbid=_maybe_uuid(recording_mbid))
            resolution_cache[cache_key] = track.juke_id if track else None
        return resolution_cache[cache_key]

    spotify_id = str(candidates.get('spotify_id') or '').strip()
    if spotify_id:
        cache_key = ('spotify', spotify_id)
        if cache_key not in resolution_cache:
            track = IdentityResolver.resolve_track(source='spotify', external_id=spotify_id)
            if track is None:
                track = Track.objects.filter(spotify_id=spotify_id).first()
            resolution_cache[cache_key] = track.juke_id if track else None
        return resolution_cache[cache_key]

    return None


def _parse_listen(payload: dict[str, Any]) -> ParsedListen:
    user_name = str(payload.get('user_name') or payload.get('user_id') or '').strip()
    if not user_name:
        raise ValueError('ListenBrainz row missing user_name/user_id')

    listened_at = payload.get('listened_at')
    if listened_at in (None, ''):
        raise ValueError('ListenBrainz row missing listened_at')

    try:
        played_at = datetime.fromtimestamp(int(listened_at), tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise ValueError(f'Invalid listened_at value: {listened_at!r}') from exc

    track_metadata = payload.get('track_metadata')
    if not isinstance(track_metadata, dict):
        raise ValueError('ListenBrainz row missing track_metadata')

    mbid_mapping = track_metadata.get('mbid_mapping') or {}
    additional_info = track_metadata.get('additional_info') or {}

    recording_mbid = _maybe_uuid(mbid_mapping.get('recording_mbid'))
    release_mbid = _maybe_uuid(mbid_mapping.get('release_mbid'))
    artist_mbids = [str(value) for value in (mbid_mapping.get('artist_mbids') or []) if _maybe_uuid(value)]
    spotify_id = _extract_spotify_id(additional_info)
    recording_msid = str(track_metadata.get('recording_msid') or additional_info.get('recording_msid') or '').strip()
    release_msid = str(track_metadata.get('release_msid') or additional_info.get('release_msid') or '').strip()
    track_name = str(track_metadata.get('track_name') or '').strip()
    artist_name = str(track_metadata.get('artist_name') or '').strip()
    release_name = str(track_metadata.get('release_name') or '').strip()

    if not any([recording_mbid, recording_msid, track_name]):
        raise ValueError('ListenBrainz row missing track identifiers')

    source_user_id = _hash_user_id(user_name)
    session_hint = _session_hint(source_user_id, played_at)
    track_identifier_candidates = {
        'recording_mbid': str(recording_mbid) if recording_mbid else '',
        'release_mbid': str(release_mbid) if release_mbid else '',
        'artist_mbids': artist_mbids,
        'recording_msid': recording_msid,
        'release_msid': release_msid,
        'spotify_id': spotify_id,
    }
    source_event_signature = _event_signature(
        source_user_id=source_user_id,
        played_at=played_at,
        candidates=track_identifier_candidates,
        track_name=track_name,
        artist_name=artist_name,
    )
    metadata = {
        'user_name': user_name,
        'track_name': track_name,
        'artist_name': artist_name,
        'release_name': release_name,
        'additional_info': additional_info,
    }
    return ParsedListen(
        source_user_id=source_user_id,
        played_at=played_at,
        session_hint=session_hint,
        source_event_signature=source_event_signature,
        track_identifier_candidates=track_identifier_candidates,
        payload=payload,
        metadata=metadata,
        recording_mbid=recording_mbid,
        release_mbid=release_mbid,
        recording_msid=recording_msid,
        release_msid=release_msid,
        track_name=track_name,
        artist_name=artist_name,
        release_name=release_name,
    )


def _iter_listen_payloads(path: Path) -> Iterator[tuple[dict[str, Any] | None, str | None]]:
    if _is_tar_archive(path):
        yield from _iter_tar_payloads(path)
        return

    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            yield from _iter_json_line_payloads(handle, origin=path.name)
        return

    with path.open('rt', encoding='utf-8') as handle:
        yield from _iter_json_line_payloads(handle, origin=path.name)


def _iter_tar_payloads(path: Path) -> Iterator[tuple[dict[str, Any] | None, str | None]]:
    with tarfile.open(path, 'r:*') as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if not member.name.endswith(SUPPORTED_JSON_LINE_SUFFIXES):
                continue

            extracted = archive.extractfile(member)
            if extracted is None:
                continue

            with io.TextIOWrapper(extracted, encoding='utf-8') as handle:
                yield from _iter_json_line_payloads(handle, origin=member.name)


def _iter_json_line_payloads(
    handle: io.TextIOBase,
    *,
    origin: str,
) -> Iterator[tuple[dict[str, Any] | None, str | None]]:
    for line_number, raw_line in enumerate(handle, start=1):
        line = raw_line.strip()
        if not line:
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            yield None, f'{origin}:{line_number}: invalid JSON ({exc.msg})'
            continue

        if isinstance(record, dict) and isinstance(record.get('payload'), dict):
            payload = record['payload']
            listens = payload.get('listens')
            if isinstance(listens, list):
                inherited_user = record.get('user_name') or payload.get('user_name')
                for index, entry in enumerate(listens, start=1):
                    if not isinstance(entry, dict):
                        yield None, f'{origin}:{line_number}:{index}: listen entry is not an object'
                        continue
                    event = dict(entry)
                    if inherited_user and 'user_name' not in event:
                        event['user_name'] = inherited_user
                    yield event, None
                continue

        if not isinstance(record, dict):
            yield None, f'{origin}:{line_number}: expected JSON object row'
            continue

        yield record, None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _is_tar_archive(path: Path) -> bool:
    lower_name = path.name.lower()
    return lower_name.endswith('.tar') or lower_name.endswith('.tar.gz') or lower_name.endswith('.tgz')


def _hash_user_id(value: str) -> str:
    salt = getattr(settings, 'MLCORE_LISTENBRAINZ_USER_HASH_SALT', 'listenbrainz')
    return hashlib.sha256(f'{salt}:{value}'.encode('utf-8')).hexdigest()


def _session_hint(source_user_id: str, played_at: datetime) -> str:
    window_seconds = getattr(settings, 'MLCORE_LISTENBRAINZ_SESSION_WINDOW_SECONDS', DEFAULT_SESSION_WINDOW_SECONDS)
    bucket = int(played_at.timestamp()) // window_seconds
    return f'{source_user_id}:{bucket}'


def _event_signature(
    *,
    source_user_id: str,
    played_at: datetime,
    candidates: dict[str, Any],
    track_name: str,
    artist_name: str,
) -> str:
    parts = [
        LISTENBRAINZ_SOURCE_ID,
        source_user_id,
        str(int(played_at.timestamp())),
        str(candidates.get('recording_mbid') or ''),
        str(candidates.get('recording_msid') or ''),
        str(candidates.get('spotify_id') or ''),
        track_name.casefold().strip(),
        artist_name.casefold().strip(),
    ]
    return hashlib.sha256('\x1f'.join(parts).encode('utf-8')).hexdigest()


def _maybe_uuid(value: Any) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _extract_spotify_id(additional_info: dict[str, Any]) -> str:
    for key in SPOTIFY_ID_KEYS:
        value = additional_info.get(key)
        if value:
            return str(value).strip()
    return ''

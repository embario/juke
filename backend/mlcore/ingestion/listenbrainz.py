from __future__ import annotations

import ctypes
import gc
import functools
import gzip
import hashlib
import io
import json
import logging
import tarfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from catalog.models import Track
from catalog.services.identity import IdentityResolver
from mlcore.models import (
    ListenBrainzEventLedger,
    ListenBrainzSessionTrack,
    SourceIngestionRun,
)
from mlcore.services.corpus import LicensePolicy

logger = logging.getLogger(__name__)

LISTENBRAINZ_SOURCE_ID = 'listenbrainz'
DEFAULT_BATCH_SIZE = 500
DEFAULT_SESSION_WINDOW_SECONDS = 30 * 60
DEFAULT_RESOLUTION_CACHE_MAX_SIZE = 50_000
DEFAULT_MEMORY_TRIM_EVERY_ROWS = 100_000
PROGRESS_REPORT_EVERY_ROWS = 100_000
PROGRESS_REPORT_EVERY_SECONDS = 30
SUPPORTED_JSON_LINE_SUFFIXES = ('.jsonl', '.ndjson', '.json', '.listens')
SOURCE_VERSION_SUFFIXES = ('.tar.zst', '.tar.gz', '.tgz', '.tar', '.gz')
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
    session_key: bytes
    source_event_signature: bytes
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
    fingerprint: str = ''


@dataclass(frozen=True)
class ResumeCheckpoint:
    origin: str
    line_number: int
    entry_index: int
    source_row_count: int
    imported_row_count: int
    duplicate_row_count: int
    canonicalized_row_count: int
    unresolved_row_count: int
    malformed_row_count: int


@dataclass(frozen=True)
class ResumeCandidate:
    run: SourceIngestionRun
    checkpoint: ResumeCheckpoint


@dataclass
class SessionTrackAggregate:
    session_key: bytes
    track_juke_id: UUID
    first_played_at: datetime
    last_played_at: datetime
    play_count: int = 1


def import_listenbrainz_dump(
    dump_path: str | Path,
    *,
    source_version: str,
    import_mode: str = 'full',
    batch_size: int = DEFAULT_BATCH_SIZE,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    resume: bool = True,
) -> ImportResult:
    path = Path(dump_path)
    if not path.exists():
        raise FileNotFoundError(f'ListenBrainz dump not found: {path}')

    policy = LicensePolicy()
    classification = policy.classify_source(LISTENBRAINZ_SOURCE_ID)
    if classification == 'blocked':
        raise ValueError('ListenBrainz source is blocked by current MLCore policy configuration')

    run = SourceIngestionRun.objects.create(
        source=LISTENBRAINZ_SOURCE_ID,
        import_mode=import_mode,
        source_version=source_version,
        raw_path=str(path),
        checksum='',
        fingerprint='',
        status='running',
        policy_classification=classification,
        metadata={
            'stage': 'fingerprint',
            'batch_size': batch_size,
            'session_window_seconds': getattr(
                settings,
                'MLCORE_LISTENBRAINZ_SESSION_WINDOW_SECONDS',
                DEFAULT_SESSION_WINDOW_SECONDS,
            ),
            'resume_enabled': resume,
        },
    )

    try:
        if progress_callback is not None:
            progress_callback(
                {
                    'run_id': str(run.pk),
                    'status': 'running',
                    'source': LISTENBRAINZ_SOURCE_ID,
                    'import_mode': import_mode,
                    'source_version': source_version,
                    'raw_path': str(path),
                    'phase': 'fingerprint',
                    'source_row_count': 0,
                    'imported_row_count': 0,
                    'duplicate_row_count': 0,
                    'canonicalized_row_count': 0,
                    'unresolved_row_count': 0,
                    'malformed_row_count': 0,
                }
            )

        fingerprint = _dump_fingerprint(path, source_version=source_version)
        resume_candidate = _find_resume_candidate(
            path,
            fingerprint=fingerprint,
            import_mode=import_mode,
            exclude_run_id=run.pk,
        ) if resume else None

        run.fingerprint = fingerprint
        run.metadata = {
            **run.metadata,
            'stage': 'importing',
            'fingerprint_mode': 'sampled_content_sha256',
            'resumed_from_run_id': (
                str(resume_candidate.run.pk)
                if resume_candidate is not None
                else ''
            ),
            'resume_start_checkpoint': (
                _checkpoint_to_metadata(resume_candidate.checkpoint)
                if resume_candidate is not None
                else {}
            ),
        }
        run.save(update_fields=['fingerprint', 'metadata'])

        counts = _ingest_dump(
            path,
            run,
            source_version=source_version,
            batch_size=batch_size,
            progress_callback=progress_callback,
            resume_checkpoint=resume_candidate.checkpoint if resume_candidate is not None else None,
        )
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
            'stage': 'completed',
        }
        run.save(
            update_fields=[
                'status',
                'source_row_count',
                'imported_row_count',
                'duplicate_row_count',
                'canonicalized_row_count',
                'unresolved_row_count',
                'malformed_row_count',
                'completed_at',
                'metadata',
            ]
        )
    except Exception as exc:
        run.status = 'failed'
        run.completed_at = timezone.now()
        run.last_error = str(exc)
        run.metadata = {
            **run.metadata,
            'stage': 'failed',
        }
        run.save(update_fields=['status', 'completed_at', 'last_error', 'metadata'])
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
        fingerprint=run.fingerprint,
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

    return infer_source_version_from_path(dump_path)


def infer_source_version_from_path(dump_path: str | Path) -> str:
    name = Path(dump_path).name
    lower_name = name.lower()
    for suffix in SOURCE_VERSION_SUFFIXES:
        if lower_name.endswith(suffix):
            candidate = name[: -len(suffix)]
            if candidate:
                if candidate.startswith('listenbrainz-listens-dump-'):
                    return candidate.replace('listenbrainz-listens-dump-', 'listenbrainz-dump-', 1)
                return candidate
    return name


def _ingest_dump(
    dump_path: Path,
    run: SourceIngestionRun,
    *,
    source_version: str,
    batch_size: int,
    progress_callback: Callable[[dict[str, Any]], None] | None,
    resume_checkpoint: ResumeCheckpoint | None,
) -> dict[str, int]:
    resolve_track_juke_id = _build_track_resolver(
        maxsize=getattr(
            settings,
            'MLCORE_LISTENBRAINZ_RESOLUTION_CACHE_MAX_SIZE',
            DEFAULT_RESOLUTION_CACHE_MAX_SIZE,
        )
    )
    counts = _counts_from_resume_checkpoint(resume_checkpoint)
    max_malformed = getattr(settings, 'MLCORE_LISTENBRAINZ_MAX_MALFORMED_ROWS', 0)
    parsed_batch: list[ParsedListen] = []
    seen_in_batch: set[bytes] = set()
    last_origin = dump_path.name
    last_line_number = 0
    last_entry_index = 0
    last_reported_source_rows = counts['source_row_count']
    last_reported_at = time.monotonic()
    last_trimmed_source_rows = counts['source_row_count']

    if resume_checkpoint is not None:
        logger.info(
            'listenbrainz import resuming run=%s from %s:%d:%d source_rows=%d imported=%d duplicates=%d unresolved=%d malformed=%d',
            run.pk,
            resume_checkpoint.origin,
            resume_checkpoint.line_number,
            resume_checkpoint.entry_index,
            resume_checkpoint.source_row_count,
            resume_checkpoint.imported_row_count,
            resume_checkpoint.duplicate_row_count,
            resume_checkpoint.unresolved_row_count,
            resume_checkpoint.malformed_row_count,
        )
        last_origin = resume_checkpoint.origin
        last_line_number = resume_checkpoint.line_number
        last_entry_index = resume_checkpoint.entry_index

    for payload, error, origin, line_number, entry_index in _iter_listen_payloads(
        dump_path,
        resume_after=resume_checkpoint,
    ):
        last_origin = origin
        last_line_number = line_number
        last_entry_index = entry_index
        if error:
            counts['malformed_row_count'] += 1
            if counts['malformed_row_count'] > max_malformed:
                raise ValueError(error)
            last_reported_source_rows, last_reported_at = _maybe_report_progress(
                run,
                counts=counts,
                batch_size=batch_size,
                last_origin=last_origin,
                last_line_number=last_line_number,
                last_entry_index=last_entry_index,
                progress_callback=progress_callback,
                last_reported_source_rows=last_reported_source_rows,
                last_reported_at=last_reported_at,
            )
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
            last_reported_source_rows, last_reported_at = _maybe_report_progress(
                run,
                counts=counts,
                batch_size=batch_size,
                last_origin=last_origin,
                last_line_number=last_line_number,
                last_entry_index=last_entry_index,
                progress_callback=progress_callback,
                last_reported_source_rows=last_reported_source_rows,
                last_reported_at=last_reported_at,
            )
            continue

        seen_in_batch.add(parsed.source_event_signature)
        parsed_batch.append(parsed)
        if len(parsed_batch) >= batch_size:
            _flush_batch(
                run,
                source_version=source_version,
                parsed_batch=parsed_batch,
                counts=counts,
                resolve_track_juke_id=resolve_track_juke_id,
                batch_end_origin=last_origin,
                batch_end_line_number=last_line_number,
                batch_end_entry_index=last_entry_index,
            )
            parsed_batch.clear()
            seen_in_batch.clear()
            last_trimmed_source_rows = _maybe_release_memory(
                counts=counts,
                last_trimmed_source_rows=last_trimmed_source_rows,
            )
            last_reported_source_rows, last_reported_at = _maybe_report_progress(
                run,
                counts=counts,
                batch_size=batch_size,
                last_origin=last_origin,
                last_line_number=last_line_number,
                last_entry_index=last_entry_index,
                progress_callback=progress_callback,
                last_reported_source_rows=last_reported_source_rows,
                last_reported_at=last_reported_at,
            )

    if parsed_batch:
        _flush_batch(
            run,
            source_version=source_version,
            parsed_batch=parsed_batch,
            counts=counts,
            resolve_track_juke_id=resolve_track_juke_id,
            batch_end_origin=last_origin,
            batch_end_line_number=last_line_number,
            batch_end_entry_index=last_entry_index,
        )
        last_trimmed_source_rows = _maybe_release_memory(
            counts=counts,
            last_trimmed_source_rows=last_trimmed_source_rows,
            force=True,
        )
        last_reported_source_rows, last_reported_at = _maybe_report_progress(
            run,
            counts=counts,
            batch_size=batch_size,
            last_origin=last_origin,
            last_line_number=last_line_number,
            last_entry_index=last_entry_index,
            progress_callback=progress_callback,
            last_reported_source_rows=last_reported_source_rows,
            last_reported_at=last_reported_at,
            force=True,
        )

    if counts['source_row_count'] == 0 and resume_checkpoint is None:
        raise ValueError(f'No listen events found in {dump_path}')

    return counts


def _flush_batch(
    run: SourceIngestionRun,
    *,
    source_version: str,
    parsed_batch: list[ParsedListen],
    counts: dict[str, int],
    resolve_track_juke_id: Callable[[dict[str, Any]], UUID | None],
    batch_end_origin: str,
    batch_end_line_number: int,
    batch_end_entry_index: int,
) -> None:
    with transaction.atomic():
        signatures = [parsed.source_event_signature for parsed in parsed_batch]
        existing_signatures = set(
            _as_binary(value)
            for value in ListenBrainzEventLedger.objects.filter(event_signature__in=signatures).values_list(
                'event_signature',
                flat=True,
            )
        )

        new_listens = [parsed for parsed in parsed_batch if parsed.source_event_signature not in existing_signatures]
        counts['duplicate_row_count'] += len(parsed_batch) - len(new_listens)
        if new_listens:
            ledger_rows: list[ListenBrainzEventLedger] = []
            session_track_aggregates: dict[tuple[bytes, UUID], SessionTrackAggregate] = {}
            unresolved = 0
            for parsed in new_listens:
                track_juke_id = resolve_track_juke_id(parsed.track_identifier_candidates)
                if track_juke_id is None:
                    unresolved += 1
                ledger_rows.append(
                    ListenBrainzEventLedger(
                        import_run=run,
                        event_signature=parsed.source_event_signature,
                        played_at=parsed.played_at,
                        session_key=parsed.session_key,
                        track_id=track_juke_id,
                        resolution_state=1 if track_juke_id is not None else 0,
                    )
                )
                if track_juke_id is None:
                    continue

                aggregate_key = (parsed.session_key, track_juke_id)
                aggregate = session_track_aggregates.get(aggregate_key)
                if aggregate is None:
                    session_track_aggregates[aggregate_key] = SessionTrackAggregate(
                        session_key=parsed.session_key,
                        track_juke_id=track_juke_id,
                        first_played_at=parsed.played_at,
                        last_played_at=parsed.played_at,
                    )
                    continue
                if parsed.played_at < aggregate.first_played_at:
                    aggregate.first_played_at = parsed.played_at
                if parsed.played_at > aggregate.last_played_at:
                    aggregate.last_played_at = parsed.played_at
                aggregate.play_count += 1

            ListenBrainzEventLedger.objects.bulk_create(ledger_rows)
            _upsert_session_tracks(run, session_track_aggregates)

            counts['imported_row_count'] += len(ledger_rows)
            counts['canonicalized_row_count'] += len(ledger_rows)
            counts['unresolved_row_count'] += unresolved
            del session_track_aggregates
            del ledger_rows
        del new_listens
        del existing_signatures
        del signatures

        _persist_run_progress(
            run,
            counts=counts,
            last_origin=batch_end_origin,
            last_line_number=batch_end_line_number,
            last_entry_index=batch_end_entry_index,
        )


def _upsert_session_tracks(
    run: SourceIngestionRun,
    aggregates: dict[tuple[bytes, UUID], SessionTrackAggregate],
) -> None:
    if not aggregates:
        return

    session_keys = list({aggregate.session_key for aggregate in aggregates.values()})
    track_ids = list({aggregate.track_juke_id for aggregate in aggregates.values()})
    existing_rows = ListenBrainzSessionTrack.objects.filter(
        session_key__in=session_keys,
        track_id__in=track_ids,
    )
    existing_by_key = {
        (_as_binary(row.session_key), row.track_id): row
        for row in existing_rows
    }

    rows_to_create: list[ListenBrainzSessionTrack] = []
    rows_to_update: list[ListenBrainzSessionTrack] = []
    for aggregate_key, aggregate in aggregates.items():
        existing = existing_by_key.get(aggregate_key)
        if existing is None:
            rows_to_create.append(
                ListenBrainzSessionTrack(
                    import_run=run,
                    session_key=aggregate.session_key,
                    track_id=aggregate.track_juke_id,
                    first_played_at=aggregate.first_played_at,
                    last_played_at=aggregate.last_played_at,
                    play_count=aggregate.play_count,
                )
            )
            continue

        if aggregate.first_played_at < existing.first_played_at:
            existing.first_played_at = aggregate.first_played_at
        if aggregate.last_played_at > existing.last_played_at:
            existing.last_played_at = aggregate.last_played_at
        existing.play_count += aggregate.play_count
        rows_to_update.append(existing)

    if rows_to_create:
        ListenBrainzSessionTrack.objects.bulk_create(rows_to_create)
    if rows_to_update:
        ListenBrainzSessionTrack.objects.bulk_update(
            rows_to_update,
            ['first_played_at', 'last_played_at', 'play_count'],
        )


def _as_binary(value: bytes | memoryview) -> bytes:
    if isinstance(value, memoryview):
        return value.tobytes()
    return bytes(value)


def _build_track_resolver(maxsize: int) -> Callable[[dict[str, Any]], UUID | None]:
    if maxsize > 0:
        resolve_track_by_mbid = functools.lru_cache(maxsize=maxsize)(_resolve_track_by_mbid_uncached)
        resolve_track_by_spotify = functools.lru_cache(maxsize=maxsize)(_resolve_track_by_spotify_uncached)
    else:
        resolve_track_by_mbid = _resolve_track_by_mbid_uncached
        resolve_track_by_spotify = _resolve_track_by_spotify_uncached

    def _resolve(candidates: dict[str, Any]) -> UUID | None:
        recording_mbid = str(candidates.get('recording_mbid') or '').strip()
        if recording_mbid:
            return resolve_track_by_mbid(recording_mbid)

        spotify_id = str(candidates.get('spotify_id') or '').strip()
        if spotify_id:
            return resolve_track_by_spotify(spotify_id)

        return None

    return _resolve


def _resolve_track_by_mbid_uncached(recording_mbid: str) -> UUID | None:
    track = IdentityResolver.resolve_track(mbid=_maybe_uuid(recording_mbid))
    return track.juke_id if track else None


def _resolve_track_by_spotify_uncached(spotify_id: str) -> UUID | None:
    track = IdentityResolver.resolve_track(source='spotify', external_id=spotify_id)
    if track is None:
        track = Track.objects.filter(spotify_id=spotify_id).first()
    return track.juke_id if track else None


def _maybe_release_memory(
    *,
    counts: dict[str, int],
    last_trimmed_source_rows: int,
    force: bool = False,
) -> int:
    trim_every_rows = int(
        getattr(
            settings,
            'MLCORE_LISTENBRAINZ_MEMORY_TRIM_EVERY_ROWS',
            DEFAULT_MEMORY_TRIM_EVERY_ROWS,
        )
    )
    if trim_every_rows <= 0:
        return last_trimmed_source_rows
    if not force and counts['source_row_count'] - last_trimmed_source_rows < trim_every_rows:
        return last_trimmed_source_rows

    gc.collect()
    trimmed = _malloc_trim()
    logger.info(
        'listenbrainz import memory trim rows=%d trimmed=%s',
        counts['source_row_count'],
        trimmed,
    )
    return counts['source_row_count']


@functools.lru_cache(maxsize=1)
def _malloc_trim_function():
    for candidate in (None, 'libc.so.6'):
        try:
            libc = ctypes.CDLL(candidate) if candidate is not None else ctypes.CDLL(None)
        except OSError:
            continue
        malloc_trim = getattr(libc, 'malloc_trim', None)
        if malloc_trim is None:
            continue
        malloc_trim.argtypes = [ctypes.c_size_t]
        malloc_trim.restype = ctypes.c_int
        return malloc_trim
    return None


def _malloc_trim() -> bool:
    malloc_trim = _malloc_trim_function()
    if malloc_trim is None:
        return False
    try:
        return bool(malloc_trim(0))
    except OSError:
        return False


def _persist_run_progress(
    run: SourceIngestionRun,
    *,
    counts: dict[str, int],
    last_origin: str,
    last_line_number: int,
    last_entry_index: int,
) -> None:
    run.source_row_count = counts['source_row_count']
    run.imported_row_count = counts['imported_row_count']
    run.duplicate_row_count = counts['duplicate_row_count']
    run.canonicalized_row_count = counts['canonicalized_row_count']
    run.unresolved_row_count = counts['unresolved_row_count']
    run.malformed_row_count = counts['malformed_row_count']
    run.metadata = {
        **run.metadata,
        'last_progress_at': timezone.now().isoformat(),
        'last_committed_checkpoint': _checkpoint_to_metadata(
            ResumeCheckpoint(
                origin=last_origin,
                line_number=last_line_number,
                entry_index=last_entry_index,
                source_row_count=counts['source_row_count'],
                imported_row_count=counts['imported_row_count'],
                duplicate_row_count=counts['duplicate_row_count'],
                canonicalized_row_count=counts['canonicalized_row_count'],
                unresolved_row_count=counts['unresolved_row_count'],
                malformed_row_count=counts['malformed_row_count'],
            )
        ),
    }
    run.save(
        update_fields=[
            'source_row_count',
            'imported_row_count',
            'duplicate_row_count',
            'canonicalized_row_count',
            'unresolved_row_count',
            'malformed_row_count',
            'metadata',
        ]
    )


def _counts_from_resume_checkpoint(resume_checkpoint: ResumeCheckpoint | None) -> dict[str, int]:
    if resume_checkpoint is None:
        return {
            'source_row_count': 0,
            'imported_row_count': 0,
            'duplicate_row_count': 0,
            'canonicalized_row_count': 0,
            'unresolved_row_count': 0,
            'malformed_row_count': 0,
        }
    return {
        'source_row_count': resume_checkpoint.source_row_count,
        'imported_row_count': resume_checkpoint.imported_row_count,
        'duplicate_row_count': resume_checkpoint.duplicate_row_count,
        'canonicalized_row_count': resume_checkpoint.canonicalized_row_count,
        'unresolved_row_count': resume_checkpoint.unresolved_row_count,
        'malformed_row_count': resume_checkpoint.malformed_row_count,
    }


def _checkpoint_to_metadata(checkpoint: ResumeCheckpoint) -> dict[str, Any]:
    return {
        'origin': checkpoint.origin,
        'line_number': checkpoint.line_number,
        'entry_index': checkpoint.entry_index,
        'source_row_count': checkpoint.source_row_count,
        'imported_row_count': checkpoint.imported_row_count,
        'duplicate_row_count': checkpoint.duplicate_row_count,
        'canonicalized_row_count': checkpoint.canonicalized_row_count,
        'unresolved_row_count': checkpoint.unresolved_row_count,
        'malformed_row_count': checkpoint.malformed_row_count,
    }


def _find_resume_candidate(
    path: Path,
    *,
    fingerprint: str,
    import_mode: str,
    exclude_run_id: UUID,
) -> ResumeCandidate | None:
    previous_runs = (
        SourceIngestionRun.objects.filter(
            source=LISTENBRAINZ_SOURCE_ID,
            import_mode=import_mode,
            raw_path=str(path),
            status='failed',
        )
        .filter(
            Q(fingerprint=fingerprint)
            | Q(fingerprint='', checksum=fingerprint)
        )
        .exclude(pk=exclude_run_id)
        .order_by('-started_at')
    )
    for previous_run in previous_runs:
        checkpoint_data = previous_run.metadata.get('last_committed_checkpoint') or {}
        origin = str(checkpoint_data.get('origin') or '').strip()
        line_number = int(checkpoint_data.get('line_number') or 0)
        entry_index = int(checkpoint_data.get('entry_index') or 1)
        if not origin or line_number <= 0:
            continue

        return ResumeCandidate(
            run=previous_run,
            checkpoint=ResumeCheckpoint(
                origin=origin,
                line_number=line_number,
                entry_index=entry_index,
                source_row_count=int(checkpoint_data.get('source_row_count') or 0),
                imported_row_count=int(checkpoint_data.get('imported_row_count') or 0),
                duplicate_row_count=int(checkpoint_data.get('duplicate_row_count') or 0),
                canonicalized_row_count=int(checkpoint_data.get('canonicalized_row_count') or 0),
                unresolved_row_count=int(checkpoint_data.get('unresolved_row_count') or 0),
                malformed_row_count=int(checkpoint_data.get('malformed_row_count') or 0),
            ),
        )

    return None


def _parse_listen(payload: dict[str, Any]) -> ParsedListen:
    user_name = str(payload.get('user_name') or payload.get('user_id') or '').strip()
    if not user_name:
        raise ValueError('ListenBrainz row missing user_name/user_id')

    listened_at = payload.get('listened_at')
    if listened_at in (None, ''):
        listened_at = payload.get('timestamp')
    if listened_at in (None, ''):
        raise ValueError('ListenBrainz row missing listened_at/timestamp')

    try:
        played_at = datetime.fromtimestamp(int(listened_at), tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise ValueError(f'Invalid listened_at value: {listened_at!r}') from exc

    track_metadata = payload.get('track_metadata')
    if not isinstance(track_metadata, dict):
        raise ValueError('ListenBrainz row missing track_metadata')

    mbid_mapping = track_metadata.get('mbid_mapping') or {}
    additional_info = track_metadata.get('additional_info') or {}

    recording_mbid = _maybe_uuid(mbid_mapping.get('recording_mbid') or additional_info.get('recording_mbid'))
    release_mbid = _maybe_uuid(mbid_mapping.get('release_mbid') or additional_info.get('release_mbid'))
    artist_mbid_values = mbid_mapping.get('artist_mbids') or additional_info.get('artist_mbids') or []
    artist_mbids = [str(value) for value in artist_mbid_values if _maybe_uuid(value)]
    spotify_id = _extract_spotify_id(additional_info)
    recording_msid = str(track_metadata.get('recording_msid') or additional_info.get('recording_msid') or '').strip()
    release_msid = str(track_metadata.get('release_msid') or additional_info.get('release_msid') or '').strip()
    track_name = str(track_metadata.get('track_name') or '').strip()
    artist_name = str(track_metadata.get('artist_name') or '').strip()
    release_name = str(track_metadata.get('release_name') or '').strip()

    if not any([recording_mbid, recording_msid, track_name]):
        raise ValueError('ListenBrainz row missing track identifiers')

    source_user_id = _hash_user_id(user_name)
    session_key = _session_key(source_user_id, played_at)
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
        session_key=session_key,
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


def _iter_listen_payloads(
    path: Path,
    *,
    resume_after: ResumeCheckpoint | None = None,
) -> Iterator[tuple[dict[str, Any] | None, str | None, str, int, int]]:
    if _is_tar_archive(path):
        yield from _iter_tar_payloads(path, resume_after=resume_after)
        return

    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            if resume_after is not None and resume_after.origin != path.name:
                raise ValueError(f'Resume checkpoint origin not found in gzip dump: {resume_after.origin}')
            yield from _iter_json_line_payloads(
                handle,
                origin=path.name,
                skip_through_line=resume_after.line_number if resume_after is not None else 0,
                skip_through_entry_index=resume_after.entry_index if resume_after is not None else 0,
            )
        return

    with path.open('rt', encoding='utf-8') as handle:
        if resume_after is not None and resume_after.origin != path.name:
            raise ValueError(f'Resume checkpoint origin not found in dump: {resume_after.origin}')
        yield from _iter_json_line_payloads(
            handle,
            origin=path.name,
            skip_through_line=resume_after.line_number if resume_after is not None else 0,
            skip_through_entry_index=resume_after.entry_index if resume_after is not None else 0,
        )


def _iter_tar_payloads(
    path: Path,
    *,
    resume_after: ResumeCheckpoint | None = None,
) -> Iterator[tuple[dict[str, Any] | None, str | None, str, int, int]]:
    awaiting_resume_origin = resume_after is not None
    resume_origin_found = False
    with tarfile.open(path, 'r:*') as archive:
        for member in archive:
            if not member.isfile():
                continue
            if not member.name.endswith(SUPPORTED_JSON_LINE_SUFFIXES):
                continue
            if awaiting_resume_origin:
                if member.name != resume_after.origin:
                    continue
                awaiting_resume_origin = False
                resume_origin_found = True

            extracted = archive.extractfile(member)
            if extracted is None:
                continue

            with io.TextIOWrapper(extracted, encoding='utf-8') as handle:
                yield from _iter_json_line_payloads(
                    handle,
                    origin=member.name,
                    skip_through_line=resume_after.line_number if resume_after and member.name == resume_after.origin else 0,
                    skip_through_entry_index=(
                        resume_after.entry_index
                        if resume_after and member.name == resume_after.origin
                        else 0
                    ),
                )
    if resume_after is not None and not resume_origin_found:
        raise ValueError(f'Resume checkpoint origin not found in tar dump: {resume_after.origin}')


def _iter_json_line_payloads(
    handle: io.TextIOBase,
    *,
    origin: str,
    skip_through_line: int = 0,
    skip_through_entry_index: int = 0,
) -> Iterator[tuple[dict[str, Any] | None, str | None, str, int, int]]:
    for line_number, raw_line in enumerate(handle, start=1):
        if line_number < skip_through_line:
            continue
        line = raw_line.strip()
        if not line:
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            if line_number == skip_through_line and skip_through_entry_index > 0:
                continue
            yield None, f'{origin}:{line_number}: invalid JSON ({exc.msg})', origin, line_number, 1
            continue

        if isinstance(record, dict) and isinstance(record.get('payload'), dict):
            payload = record['payload']
            listens = payload.get('listens')
            if isinstance(listens, list):
                inherited_user = record.get('user_name') or payload.get('user_name')
                for index, entry in enumerate(listens, start=1):
                    if line_number == skip_through_line and index <= skip_through_entry_index:
                        continue
                    if not isinstance(entry, dict):
                        yield None, f'{origin}:{line_number}:{index}: listen entry is not an object', origin, line_number, index
                        continue
                    event = dict(entry)
                    if inherited_user and 'user_name' not in event:
                        event['user_name'] = inherited_user
                    yield event, None, origin, line_number, index
                continue

        if not isinstance(record, dict):
            if line_number == skip_through_line and skip_through_entry_index > 0:
                continue
            yield None, f'{origin}:{line_number}: expected JSON object row', origin, line_number, 1
            continue

        if line_number == skip_through_line and skip_through_entry_index > 0:
            continue
        yield record, None, origin, line_number, 1


def _maybe_report_progress(
    run: SourceIngestionRun,
    *,
    counts: dict[str, int],
    batch_size: int,
    last_origin: str,
    last_line_number: int,
    last_entry_index: int,
    progress_callback: Callable[[dict[str, Any]], None] | None,
    last_reported_source_rows: int,
    last_reported_at: float,
    force: bool = False,
) -> tuple[int, float]:
    now = time.monotonic()
    should_report = force
    if not should_report and counts['source_row_count'] - last_reported_source_rows >= PROGRESS_REPORT_EVERY_ROWS:
        should_report = True
    if not should_report and now - last_reported_at >= PROGRESS_REPORT_EVERY_SECONDS:
        should_report = True
    if not should_report:
        return last_reported_source_rows, last_reported_at

    snapshot = {
        'run_id': str(run.pk),
        'status': run.status,
        'source': run.source,
        'import_mode': run.import_mode,
        'source_version': run.source_version,
        'raw_path': run.raw_path,
        'phase': 'importing',
        'source_row_count': counts['source_row_count'],
        'imported_row_count': counts['imported_row_count'],
        'duplicate_row_count': counts['duplicate_row_count'],
        'canonicalized_row_count': counts['canonicalized_row_count'],
        'unresolved_row_count': counts['unresolved_row_count'],
        'malformed_row_count': counts['malformed_row_count'],
        'batch_size': batch_size,
        'last_origin': last_origin,
        'last_line_number': last_line_number,
        'last_entry_index': last_entry_index,
    }
    logger.info(
        'listenbrainz import progress run=%s rows=%d imported=%d duplicates=%d unresolved=%d malformed=%d at=%s:%d:%d',
        run.pk,
        counts['source_row_count'],
        counts['imported_row_count'],
        counts['duplicate_row_count'],
        counts['unresolved_row_count'],
        counts['malformed_row_count'],
        last_origin,
        last_line_number,
        last_entry_index,
    )
    if progress_callback is not None:
        progress_callback(snapshot)
    return counts['source_row_count'], now


def _dump_fingerprint(path: Path, *, source_version: str) -> str:
    stat = path.stat()
    sample_size = 1024 * 1024
    digest = hashlib.sha256()
    digest.update(b'listenbrainz')
    digest.update(source_version.encode('utf-8'))
    digest.update(str(stat.st_size).encode('ascii'))
    with path.open('rb') as handle:
        head = handle.read(sample_size)
        digest.update(head)
        if stat.st_size > sample_size:
            tail_offset = max(0, stat.st_size - sample_size)
            handle.seek(tail_offset)
            digest.update(handle.read(sample_size))
    return digest.hexdigest()


def _is_tar_archive(path: Path) -> bool:
    lower_name = path.name.lower()
    return (
        lower_name.endswith('.tar')
        or lower_name.endswith('.tar.gz')
        or lower_name.endswith('.tar.zst')
        or lower_name.endswith('.tgz')
    )


def _hash_user_id(value: str) -> str:
    salt = getattr(settings, 'MLCORE_LISTENBRAINZ_USER_HASH_SALT', 'listenbrainz')
    return hashlib.sha256(f'{salt}:{value}'.encode('utf-8')).hexdigest()


def _session_key(source_user_id: str, played_at: datetime) -> bytes:
    window_seconds = getattr(settings, 'MLCORE_LISTENBRAINZ_SESSION_WINDOW_SECONDS', DEFAULT_SESSION_WINDOW_SECONDS)
    bucket = int(played_at.timestamp()) // window_seconds
    return hashlib.sha256(f'{source_user_id}:{bucket}'.encode('utf-8')).digest()


def _event_signature(
    *,
    source_user_id: str,
    played_at: datetime,
    candidates: dict[str, Any],
    track_name: str,
    artist_name: str,
) -> bytes:
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
    return hashlib.sha256('\x1f'.join(parts).encode('utf-8')).digest()


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

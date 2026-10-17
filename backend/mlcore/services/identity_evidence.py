"""Load ListenBrainz schema-v3 shard evidence into ``mlcore_identity_evidence`` (cold, many-to-many).

Everything here is set-based. A group of shard files of one scheme is COPYed into an unlogged staging
table (configurable tablespace, e.g. NVMe), aggregated once with ``GROUP BY ... ORDER BY value, subject``
into a second staging table whose identity ``row_id`` follows that order, then applied in ``row_id``
slices. Because each slice is a contiguous slice of the unique index's key order, an applying batch
touches a localised range of the index and consecutive batches move rightwards: a merge-like pass
rather than random probes. The MSID subject id is derived (uuid5, as ``canonical_item_uuid``) while
streaming the file, so no join against the 100M-row canonical item table is needed.

Resumable: a group row records its shard keys and ``applied_through``; every batch advances that
cursor in the same transaction as its writes, so a batch is applied exactly once.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from compression import zstd
from django.db import connection, transaction
from django.utils import timezone

from mlcore.models import IdentityEvidence, IdentityEvidenceLoadGroup, ListenBrainzIdentityShard
from mlcore.services.canonical_items import ITEM_TYPE_RECORDING_MSID, canonical_item_uuid
from mlcore.services.listenbrainz_identity_bridge import (
    EXTRACTION_SCHEMA_VERSION,
    ISRC_SUFFIX,
    MBID_SUFFIX,
    SPOTIFY_SUFFIX,
)

EVIDENCE_SOURCE = 'listenbrainz'
RAW_STAGE_TABLE = 'mlcore_identity_evidence_stage_raw'
STAGE_TABLE = 'mlcore_identity_evidence_stage'
DEFAULT_GROUP_SIZE = 12
DEFAULT_BATCH_SIZE = 50_000
WORK_MEM_RE = re.compile(r'^[0-9]{1,6}(kB|MB|GB)$')
TABLESPACE_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')
SHARD_PERIOD_RE = re.compile(r'(\d{4})/(\d{1,2})')


@dataclass(frozen=True)
class SchemeFile:
    scheme: str
    suffix: str
    counted: bool  # msid<TAB>value<TAB>count vs msid<TAB>value (one observation per shard)


SCHEME_FILES = {
    'spotify_track': SchemeFile('spotify_track', SPOTIFY_SUFFIX, True),
    'isrc': SchemeFile('isrc', ISRC_SUFFIX, True),
    'mbid': SchemeFile('mbid', MBID_SUFFIX, False),
}


@dataclass(frozen=True)
class IdentityEvidenceLoadResult:
    source_version: str
    groups_loaded: int
    groups_skipped: int
    raw_row_count: int
    evidence_row_count: int
    elapsed_seconds: float


def shard_period(shard_key: str, fallback: datetime) -> datetime:
    """First day of the shard's month (``2007/05.jsonl`` -> 2007-05-01 UTC), or ``fallback``."""
    match = SHARD_PERIOD_RE.search(shard_key)
    if not match:
        return fallback
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return fallback
    return datetime(year, month, 1, tzinfo=UTC)


def scheme_file_path(
    mbid_output_path: str | Path,
    scheme: str,
    *,
    output_root: str | Path | None = None,
    source_version: str = '',
    shard_key: str = '',
) -> Path:
    """Path of the scheme's file for a shard, from the checkpoint path or an operator-relocated root."""
    suffix = SCHEME_FILES[scheme].suffix
    if output_root is not None:
        return Path(output_root) / source_version / f'{shard_key}{suffix}'
    mbid_path = Path(mbid_output_path)
    if not mbid_path.name.endswith(MBID_SUFFIX):
        raise ValueError(f'Unexpected ListenBrainz identity output path: {mbid_path}')
    return mbid_path.with_name(mbid_path.name[:-len(MBID_SUFFIX)] + suffix)


class _EvidenceStageReader:
    """File-like for COPY: ``msid<TAB>value[<TAB>count]`` -> ``subject<TAB>value<TAB>count<TAB>period``."""

    def __init__(self, path: Path, *, counted: bool, period: datetime) -> None:
        self._file = zstd.open(path, 'rb')
        self._counted = counted
        self._period = period.isoformat().encode()
        self._buffer = b''
        self.row_count = 0

    def read(self, size: int = -1) -> bytes:
        size = (1 << 20) if size is None or size < 0 else size
        while len(self._buffer) < size:
            lines = self._file.readlines(size)
            if not lines:
                break
            out = []
            for line in lines:
                parts = line.rstrip(b'\n').split(b'\t')
                subject = canonical_item_uuid(item_type=ITEM_TYPE_RECORDING_MSID, key_value=parts[0].decode())
                count = parts[2] if self._counted else b'1'
                out.append(b'\t'.join((str(subject).encode(), parts[1], count, self._period)) + b'\n')
                self.row_count += 1
            self._buffer += b''.join(out)
        data, self._buffer = self._buffer[:size], self._buffer[size:]
        return data

    def close(self) -> None:
        self._file.close()


def load_listenbrainz_identity_evidence(
    source_version: str,
    *,
    schemes: list[str] | None = None,
    output_root: str | Path | None = None,
    staging_tablespace: str | None = None,
    group_size: int = DEFAULT_GROUP_SIZE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_groups: int | None = None,
    work_mem: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> IdentityEvidenceLoadResult:
    if group_size < 1 or batch_size < 1:
        raise ValueError('group_size and batch_size must be greater than zero')
    if staging_tablespace is not None and not TABLESPACE_RE.match(staging_tablespace):
        raise ValueError(f'Invalid tablespace name: {staging_tablespace!r}')
    if work_mem is not None and not WORK_MEM_RE.match(work_mem):
        raise ValueError(f'Invalid work_mem: {work_mem!r} (use e.g. 512MB)')
    schemes = schemes or list(SCHEME_FILES)
    unknown = [scheme for scheme in schemes if scheme not in SCHEME_FILES]
    if unknown:
        raise ValueError(f'Unknown evidence scheme(s): {", ".join(unknown)}')

    started = time.monotonic()
    shards = list(
        ListenBrainzIdentityShard.objects.filter(
            source_version=source_version,
            status='succeeded',
            extraction_schema_version__gte=EXTRACTION_SCHEMA_VERSION,
        ).order_by('shard_key')
    )
    loaded = skipped = raw_total = evidence_total = 0
    for scheme in schemes:
        covered = set()
        in_flight: list[IdentityEvidenceLoadGroup] = []
        for group in IdentityEvidenceLoadGroup.objects.filter(
            source=EVIDENCE_SOURCE, source_version=source_version, scheme=scheme,
        ).order_by('id'):
            covered.update(group.shard_keys)
            if group.status == 'succeeded':
                skipped += 1
            else:
                in_flight.append(group)
        remaining = [shard for shard in shards if shard.shard_key not in covered]
        planned = list(in_flight)
        for start in range(0, len(remaining), group_size):
            planned.append(_new_group(source_version, scheme, remaining[start:start + group_size]))
        for group in planned:
            if max_groups is not None and loaded >= max_groups:
                break
            raw_rows, evidence_rows = _load_group(
                group,
                shards_by_key={shard.shard_key: shard for shard in shards},
                output_root=output_root,
                staging_tablespace=staging_tablespace,
                work_mem=work_mem,
                batch_size=batch_size,
                progress_callback=progress_callback,
            )
            loaded += 1
            raw_total += raw_rows
            evidence_total += evidence_rows
    return IdentityEvidenceLoadResult(
        source_version=source_version,
        groups_loaded=loaded,
        groups_skipped=skipped,
        raw_row_count=raw_total,
        evidence_row_count=evidence_total,
        elapsed_seconds=time.monotonic() - started,
    )


def _new_group(source_version: str, scheme: str, shards: list[ListenBrainzIdentityShard]) -> IdentityEvidenceLoadGroup:
    return IdentityEvidenceLoadGroup(
        source=EVIDENCE_SOURCE,
        source_version=source_version,
        scheme=scheme,
        shard_keys=[shard.shard_key for shard in shards],
    )


def _load_group(
    group: IdentityEvidenceLoadGroup,
    *,
    shards_by_key: dict[str, ListenBrainzIdentityShard],
    output_root: str | Path | None,
    staging_tablespace: str | None,
    work_mem: str | None,
    batch_size: int,
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> tuple[int, int]:
    group_started = time.monotonic()
    if group.pk is None:
        group.status = 'running'
        group.save()
    else:
        IdentityEvidenceLoadGroup.objects.filter(pk=group.pk).update(status='running', last_error='')
        group.refresh_from_db()
    try:
        if not _stage_is_intact(group):
            _stage_group(group, shards_by_key, output_root, staging_tablespace, work_mem)
            group.refresh_from_db()
        total = group.stage_row_count
        applied = group.applied_through
        scheme_started = time.monotonic()
        applied_at_start = applied
        while applied < total:
            upper = min(applied + batch_size, total)
            _apply_batch(group, lower=applied, upper=upper)
            applied = upper
            elapsed = max(time.monotonic() - scheme_started, 0.001)
            rate = (applied - applied_at_start) / elapsed
            _report(progress_callback, {
                'event': 'evidence_batch',
                'scheme': group.scheme,
                'group_first_shard': group.shard_keys[0] if group.shard_keys else '',
                'applied_rows': applied,
                'stage_rows': total,
                'rows_per_second': rate,
                'eta_seconds': (total - applied) / rate if rate else None,
            })
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS {RAW_STAGE_TABLE}')
            cursor.execute(f'DROP TABLE IF EXISTS {STAGE_TABLE}')
            IdentityEvidenceLoadGroup.objects.filter(pk=group.pk).update(
                status='succeeded', completed_at=timezone.now(), last_error='',
            )
        _report(progress_callback, {
            'event': 'evidence_group_complete',
            'scheme': group.scheme,
            'shards': len(group.shard_keys),
            'raw_rows': group.raw_row_count,
            'evidence_rows': total,
            'elapsed_seconds': time.monotonic() - group_started,
        })
        return group.raw_row_count, total
    except Exception as exc:
        IdentityEvidenceLoadGroup.objects.filter(pk=group.pk).update(status='failed', last_error=str(exc))
        raise


def _stage_is_intact(group: IdentityEvidenceLoadGroup) -> bool:
    if group.stage_row_count <= 0:
        return False
    with connection.cursor() as cursor:
        cursor.execute('SELECT to_regclass(%s)', [STAGE_TABLE])
        if cursor.fetchone()[0] is None:
            return False
        cursor.execute(f'SELECT COUNT(*) FROM {STAGE_TABLE}')
        return int(cursor.fetchone()[0]) == group.stage_row_count


def _stage_group(
    group: IdentityEvidenceLoadGroup,
    shards_by_key: dict[str, ListenBrainzIdentityShard],
    output_root: str | Path | None,
    staging_tablespace: str | None,
    work_mem: str | None,
) -> None:
    """COPY the group's files, aggregate once in key order. Never touches IdentityEvidence."""
    scheme_file = SCHEME_FILES[group.scheme]
    quote = connection.ops.quote_name
    tablespace_sql = f'TABLESPACE {quote(staging_tablespace)}' if staging_tablespace else ''
    now = timezone.now()
    raw_rows = 0
    with transaction.atomic(), connection.cursor() as cursor:
        if staging_tablespace:  # sort spill for the aggregate goes to the same (fast) tablespace
            cursor.execute(f'SET LOCAL temp_tablespaces = {quote(staging_tablespace)}')
        if work_mem:
            cursor.execute(f"SET LOCAL work_mem = '{work_mem}'")
        cursor.execute(f'DROP TABLE IF EXISTS {RAW_STAGE_TABLE}')
        cursor.execute(f'DROP TABLE IF EXISTS {STAGE_TABLE}')
        cursor.execute(f'''
            CREATE UNLOGGED TABLE {RAW_STAGE_TABLE} (
                subject_id uuid NOT NULL,
                value varchar(255) NOT NULL,
                observation_count bigint NOT NULL,
                period timestamptz NOT NULL
            ) {tablespace_sql}
        ''')
        raw_cursor = getattr(cursor, 'cursor', cursor)
        if not hasattr(raw_cursor, 'copy_expert'):
            raise RuntimeError('Identity evidence loading requires PostgreSQL COPY support')
        for shard_key in group.shard_keys:
            shard = shards_by_key[shard_key]
            path = scheme_file_path(
                shard.output_path, group.scheme,
                output_root=output_root, source_version=group.source_version, shard_key=shard_key,
            )
            if not path.is_file():
                raise FileNotFoundError(f'Evidence file missing for {shard_key}: {path}')
            reader = _EvidenceStageReader(path, counted=scheme_file.counted, period=shard_period(shard_key, now))
            try:
                raw_cursor.copy_expert(
                    f'COPY {RAW_STAGE_TABLE} (subject_id, value, observation_count, period) FROM STDIN', reader,
                )
            finally:
                reader.close()
            raw_rows += reader.row_count
        cursor.execute(f'ANALYZE {RAW_STAGE_TABLE}')  # real row counts, so the planner sorts/aggregates sensibly
        cursor.execute(f'''
            CREATE UNLOGGED TABLE {STAGE_TABLE} (
                row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                subject_id uuid NOT NULL,
                value varchar(255) NOT NULL,
                observation_count bigint NOT NULL,
                shard_count integer NOT NULL,
                first_seen timestamptz NOT NULL,
                last_seen timestamptz NOT NULL
            ) {tablespace_sql}
        ''')
        cursor.execute(f'''
            INSERT INTO {STAGE_TABLE} (subject_id, value, observation_count, shard_count, first_seen, last_seen)
            SELECT subject_id, value, SUM(observation_count), COUNT(*), MIN(period), MAX(period)
            FROM {RAW_STAGE_TABLE}
            GROUP BY subject_id, value
            ORDER BY value, subject_id
        ''')
        stage_rows = cursor.rowcount
        cursor.execute(f'DROP TABLE {RAW_STAGE_TABLE}')
        IdentityEvidenceLoadGroup.objects.filter(pk=group.pk).update(
            raw_row_count=raw_rows,
            stage_row_count=stage_rows,
            staging_tablespace=staging_tablespace or '',
        )


APPLY_BATCH_SQL = f'''
    INSERT INTO {IdentityEvidence._meta.db_table} AS ev (
        subject_canonical_item_id, scheme, value, source, source_version,
        observation_count, shard_count, first_seen, last_seen
    )
    SELECT subject_id, %s, value, %s, %s, observation_count, shard_count, first_seen, last_seen
    FROM {STAGE_TABLE}
    WHERE row_id > %s AND row_id <= %s
    ORDER BY row_id
    ON CONFLICT (scheme, value, subject_canonical_item_id, source) DO UPDATE SET
        observation_count = ev.observation_count + EXCLUDED.observation_count,
        shard_count = ev.shard_count + EXCLUDED.shard_count,
        first_seen = LEAST(ev.first_seen, EXCLUDED.first_seen),
        last_seen = GREATEST(ev.last_seen, EXCLUDED.last_seen),
        source_version = EXCLUDED.source_version
'''


def _apply_batch(group: IdentityEvidenceLoadGroup, *, lower: int, upper: int) -> None:
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(APPLY_BATCH_SQL, [group.scheme, group.source, group.source_version, lower, upper])
        advanced = IdentityEvidenceLoadGroup.objects.filter(pk=group.pk, applied_through=lower).update(
            applied_through=upper,
        )
        if not advanced:
            raise RuntimeError(f'Evidence load group {group.pk} moved while applying rows {lower}-{upper}; another loader?')


def _report(callback: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
    if callback is not None:
        callback(payload)

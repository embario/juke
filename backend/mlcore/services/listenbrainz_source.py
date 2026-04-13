from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from mlcore.ingestion.listenbrainz import LISTENBRAINZ_SOURCE_ID, ImportResult, import_listenbrainz_dump
from mlcore.models import SourceIngestionRun
from mlcore.services.corpus import LicensePolicy

logger = logging.getLogger(__name__)

DEFAULT_REMOTE_ROOT_URL = 'https://ftp.musicbrainz.org/pub/musicbrainz/listenbrainz/'
DEFAULT_REMOTE_SYNC_TIMEOUT_SECONDS = 60
DEFAULT_REMOTE_SYNC_MAX_INCREMENTALS_PER_RUN = 14
DEFAULT_STALE_INFLIGHT_TIMEOUT_SECONDS = 60 * 30

RELEASE_NAME_RE = re.compile(
    r'^listenbrainz-dump-(?P<sequence>\d+)-(?P<date>\d{8})-(?P<time>\d{6})-(?P<mode>full|incremental)$'
)
ARTIFACT_NAME_RE = re.compile(
    r'^listenbrainz-listens-dump-(?P<sequence>\d+)-(?P<date>\d{8})-(?P<time>\d{6})-'
    r'(?P<mode>full|incremental)\.tar\.(?:zst|gz)$|'
    r'^listenbrainz-listens-dump-(?P<sequence_alt>\d+)-(?P<date_alt>\d{8})-(?P<time_alt>\d{6})-'
    r'(?P<mode_alt>full|incremental)\.tar$'
)


@dataclass(frozen=True)
class RemoteDumpRelease:
    source_version: str
    import_mode: str
    released_at: datetime
    listing_url: str


@dataclass(frozen=True)
class RemoteDumpArtifact:
    release: RemoteDumpRelease
    artifact_name: str
    artifact_url: str


@dataclass(frozen=True)
class RemoteSyncResult:
    status: str
    policy_classification: str
    full_source_version: str | None
    incremental_source_versions: list[str]
    downloaded_paths: list[str]
    skipped_source_versions: list[str]


class _AnchorHrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != 'a':
            return
        href = dict(attrs).get('href')
        if not href or href in {'../', './'} or href.startswith('?'):
            return
        self.hrefs.append(href)


def configured_remote_root_url() -> str:
    return getattr(settings, 'MLCORE_LISTENBRAINZ_REMOTE_ROOT_URL', DEFAULT_REMOTE_ROOT_URL)


def configured_download_dir() -> Path:
    value = getattr(settings, 'MLCORE_LISTENBRAINZ_DOWNLOAD_DIR', '/srv/data/listenbrainz')
    return Path(value)


def configured_remote_timeout_seconds() -> int:
    return int(
        getattr(
            settings,
            'MLCORE_LISTENBRAINZ_REMOTE_TIMEOUT_SECONDS',
            DEFAULT_REMOTE_SYNC_TIMEOUT_SECONDS,
        )
    )


def configured_max_incrementals_per_run() -> int:
    return int(
        getattr(
            settings,
            'MLCORE_LISTENBRAINZ_REMOTE_SYNC_MAX_INCREMENTALS_PER_RUN',
            DEFAULT_REMOTE_SYNC_MAX_INCREMENTALS_PER_RUN,
        )
    )


def configured_stale_inflight_timeout_seconds() -> int:
    return int(
        getattr(
            settings,
            'MLCORE_LISTENBRAINZ_STALE_INFLIGHT_TIMEOUT_SECONDS',
            DEFAULT_STALE_INFLIGHT_TIMEOUT_SECONDS,
        )
    )


def sync_listenbrainz_remote_dumps(
    *,
    root_url: str | None = None,
    download_dir: str | Path | None = None,
    max_incrementals_per_run: int | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> RemoteSyncResult:
    from mlcore.services.full_ingestion import full_ingestion_conflict_metadata

    lease_conflict = full_ingestion_conflict_metadata(LISTENBRAINZ_SOURCE_ID)
    if lease_conflict is not None:
        logger.warning(
            'listenbrainz remote sync skipped because full ingestion run %s owns the provider lease',
            lease_conflict['lease_run_id'],
        )
        return RemoteSyncResult(
            status='skipped',
            policy_classification='n/a',
            full_source_version=None,
            incremental_source_versions=[],
            downloaded_paths=[],
            skipped_source_versions=[],
        )

    policy = LicensePolicy().classify_source(LISTENBRAINZ_SOURCE_ID)
    if policy == 'blocked':
        logger.warning('listenbrainz remote sync skipped because policy classification is blocked')
        return RemoteSyncResult(
            status='skipped',
            policy_classification=policy,
            full_source_version=None,
            incremental_source_versions=[],
            downloaded_paths=[],
            skipped_source_versions=[],
        )

    remote_root = root_url or configured_remote_root_url()
    target_dir = Path(download_dir) if download_dir is not None else configured_download_dir()
    incremental_limit = (
        configured_max_incrementals_per_run()
        if max_incrementals_per_run is None
        else max_incrementals_per_run
    )
    logger.info(
        'listenbrainz remote sync starting root=%s download_dir=%s policy=%s max_incrementals=%d',
        remote_root,
        target_dir,
        policy,
        incremental_limit,
    )
    stale_versions = _expire_stale_inflight_runs()
    if stale_versions:
        logger.info(
            'listenbrainz remote sync expired stale in-flight runs=%s',
            ','.join(stale_versions),
        )

    successful_rows = list(
        SourceIngestionRun.objects.filter(
            source=LISTENBRAINZ_SOURCE_ID,
            status='succeeded',
        ).values_list('source_version', 'raw_path')
    )
    in_flight_rows = list(
        SourceIngestionRun.objects.filter(
            source=LISTENBRAINZ_SOURCE_ID,
            status__in=('pending', 'running'),
        ).values_list('source_version', 'raw_path')
    )
    successful_versions = _canonical_source_versions(successful_rows)
    in_flight_versions = _canonical_source_versions(in_flight_rows)
    skipped_versions = sorted(in_flight_versions)

    imported_full_source_version: str | None = None
    imported_incrementals: list[str] = []
    downloaded_paths: list[str] = []

    baseline_full = _latest_imported_release(successful_versions, import_mode='full')
    effective_full = baseline_full
    local_full_artifact = _latest_local_artifact(target_dir=target_dir, import_mode='full')
    if baseline_full is None:
        logger.info('listenbrainz remote sync has no successful full baseline yet')
    else:
        logger.info(
            'listenbrainz remote sync current successful full baseline=%s',
            baseline_full.source_version,
        )

    if effective_full is None and local_full_artifact is not None:
        if local_full_artifact.release.source_version in in_flight_versions:
            logger.info(
                'listenbrainz remote sync skipping local full baseline=%s because it is already in flight',
                local_full_artifact.release.source_version,
            )
            skipped_versions.append(local_full_artifact.release.source_version)
            result = RemoteSyncResult(
                status='noop',
                policy_classification=policy,
                full_source_version=None,
                incremental_source_versions=[],
                downloaded_paths=downloaded_paths,
                skipped_source_versions=sorted(set(skipped_versions)),
            )
            logger.info(
                'listenbrainz remote sync completed status=%s imported_full=%s imported_incrementals=%d downloads=%d skipped=%d',
                result.status,
                result.full_source_version or '-',
                len(result.incremental_source_versions),
                len(result.downloaded_paths),
                len(result.skipped_source_versions),
            )
            return result
        else:
            logger.info(
                'listenbrainz remote sync importing local full baseline=%s path=%s',
                local_full_artifact.release.source_version,
                local_full_artifact.artifact_url,
            )
            _run_import(
                Path(local_full_artifact.artifact_url),
                release=local_full_artifact.release,
                progress_callback=progress_callback,
            )
            successful_versions.add(local_full_artifact.release.source_version)
            imported_full_source_version = local_full_artifact.release.source_version
            effective_full = local_full_artifact.release

    if effective_full is None:
        full_releases = list_remote_releases(import_mode='full', root_url=remote_root)
        if not full_releases:
            raise ValueError('No remote ListenBrainz full dumps discovered')

        latest_remote_full = full_releases[-1]
        logger.info(
            'listenbrainz remote sync discovered full releases=%d latest_full=%s',
            len(full_releases),
            latest_remote_full.source_version,
        )
        if latest_remote_full.source_version in in_flight_versions:
            skipped_versions.append(latest_remote_full.source_version)
            logger.info(
                'listenbrainz remote sync skipping remote full baseline=%s because it is already in flight',
                latest_remote_full.source_version,
            )
        else:
            logger.info(
                'listenbrainz remote sync importing remote full baseline=%s',
                latest_remote_full.source_version,
            )
            artifact = resolve_release_artifact(latest_remote_full)
            local_path, downloaded = download_release_artifact(artifact, target_dir=target_dir)
            if downloaded:
                downloaded_paths.append(str(local_path))
            _run_import(
                local_path,
                release=artifact.release,
                progress_callback=progress_callback,
            )
            successful_versions.add(artifact.release.source_version)
            imported_full_source_version = artifact.release.source_version
            effective_full = artifact.release

    if effective_full is None:
        raise ValueError('Unable to determine ListenBrainz full-dump baseline for incremental replay')

    all_incremental_releases = list_remote_releases(import_mode='incremental', root_url=remote_root)
    incremental_releases = [
        release
        for release in all_incremental_releases
        if release.released_at > effective_full.released_at
    ]
    logger.info(
        'listenbrainz remote sync discovered incrementals=%d candidates_after_baseline=%d baseline=%s',
        len(all_incremental_releases),
        len(incremental_releases),
        effective_full.source_version,
    )

    imported_count = 0
    for release in incremental_releases:
        if imported_count >= incremental_limit:
            logger.info(
                'listenbrainz remote sync reached incremental limit=%d remaining=%d',
                incremental_limit,
                len(incremental_releases) - imported_count,
            )
            break
        if release.source_version in successful_versions or release.source_version in in_flight_versions:
            skipped_versions.append(release.source_version)
            if release.source_version in in_flight_versions:
                logger.info(
                    'listenbrainz remote sync skipping incremental=%s because it is already in flight',
                    release.source_version,
                )
            continue

        logger.info('listenbrainz remote sync importing incremental=%s', release.source_version)
        artifact = resolve_release_artifact(release)
        local_path, downloaded = download_release_artifact(artifact, target_dir=target_dir)
        if downloaded:
            downloaded_paths.append(str(local_path))
        _run_import(
            local_path,
            release=artifact.release,
            progress_callback=progress_callback,
        )
        successful_versions.add(artifact.release.source_version)
        imported_incrementals.append(artifact.release.source_version)
        imported_count += 1

    status = 'noop'
    if imported_full_source_version or imported_incrementals:
        status = 'succeeded'

    result = RemoteSyncResult(
        status=status,
        policy_classification=policy,
        full_source_version=imported_full_source_version,
        incremental_source_versions=imported_incrementals,
        downloaded_paths=downloaded_paths,
        skipped_source_versions=sorted(set(skipped_versions)),
    )
    logger.info(
        'listenbrainz remote sync completed status=%s imported_full=%s imported_incrementals=%d downloads=%d skipped=%d',
        result.status,
        result.full_source_version or '-',
        len(result.incremental_source_versions),
        len(result.downloaded_paths),
        len(result.skipped_source_versions),
    )
    return result


def list_remote_releases(*, import_mode: str, root_url: str | None = None) -> list[RemoteDumpRelease]:
    base_url = root_url or configured_remote_root_url()
    index_url = urljoin(_normalized_remote_root(base_url), f'{_release_subdir(import_mode)}/')
    releases: list[RemoteDumpRelease] = []
    for href in _fetch_index_hrefs(index_url):
        name = href.rstrip('/').split('/')[-1]
        parsed = _parse_release_name(name)
        if parsed is None or parsed.import_mode != import_mode:
            continue
        releases.append(
            RemoteDumpRelease(
                source_version=parsed.source_version,
                import_mode=parsed.import_mode,
                released_at=parsed.released_at,
                listing_url=urljoin(index_url, href.rstrip('/') + '/'),
            )
        )
    releases.sort(key=lambda release: release.released_at)
    logger.info(
        'listenbrainz remote sync indexed mode=%s releases=%d index=%s',
        import_mode,
        len(releases),
        index_url,
    )
    return releases


def resolve_release_artifact(release: RemoteDumpRelease) -> RemoteDumpArtifact:
    for href in _fetch_index_hrefs(release.listing_url):
        artifact_name = href.rstrip('/').split('/')[-1]
        parsed = _parse_artifact_name(artifact_name)
        if parsed is None:
            continue
        if parsed.import_mode != release.import_mode or parsed.source_version != release.source_version:
            continue
        return RemoteDumpArtifact(
            release=release,
            artifact_name=artifact_name,
            artifact_url=urljoin(release.listing_url, href),
        )
    logger.warning(
        'listenbrainz remote sync found no artifact for release=%s listing=%s',
        release.source_version,
        release.listing_url,
    )
    raise ValueError(f'No downloadable listen dump found for release {release.source_version}')


def download_release_artifact(
    artifact: RemoteDumpArtifact,
    *,
    target_dir: Path,
) -> tuple[Path, bool]:
    release_dir = target_dir / artifact.release.import_mode
    release_dir.mkdir(parents=True, exist_ok=True)
    destination = release_dir / artifact.artifact_name
    if destination.exists() and destination.stat().st_size > 0:
        logger.info('listenbrainz remote sync reusing local artifact %s', destination)
        return destination, False

    legacy_destination = target_dir / artifact.artifact_name
    if legacy_destination.exists() and legacy_destination.stat().st_size > 0:
        logger.info(
            'listenbrainz remote sync reusing legacy local artifact %s',
            legacy_destination,
        )
        return legacy_destination, False

    temp_path = destination.with_name(destination.name + '.part')
    if temp_path.exists():
        temp_path.unlink()

    logger.info('listenbrainz remote sync downloading %s to %s', artifact.artifact_url, destination)
    with _open_url(artifact.artifact_url) as response, temp_path.open('wb') as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)

    temp_path.replace(destination)
    return destination, True


def _run_import(
    local_path: Path,
    *,
    release: RemoteDumpRelease,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ImportResult:
    logger.info(
        'listenbrainz remote sync importing %s mode=%s path=%s',
        release.source_version,
        release.import_mode,
        local_path,
    )
    if progress_callback is not None:
        progress_callback(
            {
                'status': 'running',
                'source': LISTENBRAINZ_SOURCE_ID,
                'sync_phase': f'import_{release.import_mode}',
                'import_mode': release.import_mode,
                'source_version': release.source_version,
                'raw_path': str(local_path),
            }
        )
    result = import_listenbrainz_dump(
        local_path,
        source_version=release.source_version,
        import_mode=release.import_mode,
        progress_callback=progress_callback,
    )
    logger.info(
        'listenbrainz remote sync import finished '
        'source_version=%s mode=%s run_id=%s rows=%d imported=%d '
        'duplicates=%d unresolved=%d malformed=%d',
        release.source_version,
        release.import_mode,
        result.run_id,
        result.source_row_count,
        result.imported_row_count,
        result.duplicate_row_count,
        result.unresolved_row_count,
        result.malformed_row_count,
    )
    return result


def _expire_stale_inflight_runs() -> list[str]:
    now = timezone.now()
    cutoff = now - timedelta(seconds=configured_stale_inflight_timeout_seconds())
    stale_versions: list[str] = []
    stale_runs = list(
        SourceIngestionRun.objects.filter(
            source=LISTENBRAINZ_SOURCE_ID,
            status__in=('pending', 'running'),
        ).order_by('started_at')
    )
    for run in stale_runs:
        last_progress_at = _progress_timestamp_from_metadata(run.metadata) or run.started_at
        if last_progress_at > cutoff:
            continue
        run.status = 'failed'
        run.completed_at = now
        stale_reason = (
            f'Stale in-flight ListenBrainz import marked failed after no progress since '
            f'{last_progress_at.isoformat()}'
        )
        run.last_error = stale_reason
        run.metadata = {
            **run.metadata,
            'stage': 'failed',
            'stale_marked_at': now.isoformat(),
        }
        run.save(update_fields=['status', 'completed_at', 'last_error', 'metadata'])
        stale_versions.append(run.source_version)
    return stale_versions


def _progress_timestamp_from_metadata(metadata: dict[str, Any]) -> datetime | None:
    value = metadata.get('last_progress_at')
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _fetch_index_hrefs(index_url: str) -> list[str]:
    with _open_url(index_url) as response:
        html = response.read().decode('utf-8', errors='replace')
    parser = _AnchorHrefParser()
    parser.feed(html)
    return parser.hrefs


def _open_url(url: str):
    request = Request(
        url,
        headers={
            'User-Agent': f'juke-mlcore/{os.environ.get("JUKE_RUNTIME_ENV", "development")}',
        },
    )
    return urlopen(request, timeout=configured_remote_timeout_seconds())


def _latest_imported_release(source_versions: Iterable[str], *, import_mode: str) -> RemoteDumpRelease | None:
    parsed_releases = [
        release
        for version in source_versions
        for release in [_parse_source_version(version)]
        if release is not None and release.import_mode == import_mode
    ]
    if not parsed_releases:
        return None
    latest = max(parsed_releases, key=lambda release: release.released_at)
    return RemoteDumpRelease(
        source_version=latest.source_version,
        import_mode=latest.import_mode,
        released_at=latest.released_at,
        listing_url='',
    )


def _canonical_source_versions(rows: Iterable[tuple[str, str]]) -> set[str]:
    versions: set[str] = set()
    for source_version, raw_path in rows:
        parsed = _parse_source_version(source_version)
        if parsed is None and raw_path:
            parsed = _parse_source_version(raw_path)
        if parsed is None:
            continue
        versions.add(parsed.source_version)
    return versions


def _latest_local_artifact(*, target_dir: Path, import_mode: str) -> RemoteDumpArtifact | None:
    candidates: list[RemoteDumpArtifact] = []
    search_roots = [target_dir / import_mode, target_dir]
    seen_paths: set[Path] = set()
    for root in search_roots:
        if not root.exists() or not root.is_dir():
            continue
        for entry in root.iterdir():
            if not entry.is_file():
                continue
            if entry in seen_paths:
                continue
            seen_paths.add(entry)
            parsed = _parse_artifact_name(entry.name)
            if parsed is None or parsed.import_mode != import_mode:
                continue
            candidates.append(
                RemoteDumpArtifact(
                    release=RemoteDumpRelease(
                        source_version=parsed.source_version,
                        import_mode=parsed.import_mode,
                        released_at=parsed.released_at,
                        listing_url='',
                    ),
                    artifact_name=entry.name,
                    artifact_url=str(entry),
                )
            )
    if not candidates:
        return None
    return max(candidates, key=lambda artifact: artifact.release.released_at)


def _normalized_remote_root(root_url: str) -> str:
    return root_url.rstrip('/') + '/'


def _release_subdir(import_mode: str) -> str:
    if import_mode == 'full':
        return 'fullexport'
    if import_mode == 'incremental':
        return 'incremental'
    raise ValueError(f"Unknown import_mode '{import_mode}'")


@dataclass(frozen=True)
class _ParsedReleaseIdentity:
    source_version: str
    import_mode: str
    released_at: datetime


def _parse_release_name(name: str) -> _ParsedReleaseIdentity | None:
    match = RELEASE_NAME_RE.match(name)
    if not match:
        return None
    return _ParsedReleaseIdentity(
        source_version=name,
        import_mode=match.group('mode'),
        released_at=_parse_release_timestamp(match.group('date'), match.group('time')),
    )


def _parse_artifact_name(name: str) -> _ParsedReleaseIdentity | None:
    match = ARTIFACT_NAME_RE.match(name)
    if not match:
        return None
    sequence = match.group('sequence') or match.group('sequence_alt')
    date = match.group('date') or match.group('date_alt')
    time = match.group('time') or match.group('time_alt')
    mode = match.group('mode') or match.group('mode_alt')
    source_version = f'listenbrainz-dump-{sequence}-{date}-{time}-{mode}'
    return _ParsedReleaseIdentity(
        source_version=source_version,
        import_mode=mode,
        released_at=_parse_release_timestamp(date, time),
    )


def _parse_source_version(value: str) -> _ParsedReleaseIdentity | None:
    stripped = value.rstrip('/').split('/')[-1]
    parsed = _parse_release_name(stripped)
    if parsed is not None:
        return parsed
    return _parse_artifact_name(stripped)


def _parse_release_timestamp(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f'{date_str}{time_str}', '%Y%m%d%H%M%S').replace(tzinfo=UTC)

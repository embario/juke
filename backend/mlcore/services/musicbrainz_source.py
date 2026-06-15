from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from mlcore.models import SourceIngestionRun

MUSICBRAINZ_SOURCE_ID = 'musicbrainz'
DEFAULT_REMOTE_ROOT_URL = 'https://data.metabrainz.org/pub/musicbrainz/data/fullexport/'
DEFAULT_DOWNLOAD_DIR = '/srv/data/backups/juke/musicbrainz'
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_MINIMUM_FREE_BYTES = 100 * 1024**3
DEFAULT_ESTIMATED_EXPANDED_BYTES = 80 * 1024**3
CORE_ARTIFACT_NAME = 'mbdump.tar.bz2'
SOURCE_VERSION_RE = re.compile(r'^\d{8}-\d{6}$')
SHA256_RE = re.compile(r'^(?P<checksum>[0-9a-f]{64})\s+\*?(?P<name>\S+)$')
REQUIRED_CORE_MEMBERS = (
    'mbdump/recording',
    'mbdump/isrc',
    'mbdump/url',
    'mbdump/l_recording_url',
    'mbdump/link',
    'mbdump/link_type',
)


@dataclass(frozen=True)
class MusicBrainzArtifact:
    name: str
    url: str
    sha256: str
    compressed_bytes: int


@dataclass(frozen=True)
class MusicBrainzReleasePlan:
    source_version: str
    release_url: str
    artifact: MusicBrainzArtifact
    target_root: str
    release_dir: str
    manifest_path: str
    estimated_expanded_bytes: int
    minimum_free_bytes: int
    available_bytes: int
    required_members: tuple[str, ...] = REQUIRED_CORE_MEMBERS


@dataclass(frozen=True)
class MusicBrainzStageResult:
    status: str
    source_version: str
    artifact_path: str
    manifest_path: str
    checksum: str
    compressed_bytes: int
    downloaded: bool
    run_id: str | None


def configured_remote_root_url() -> str:
    return getattr(settings, 'MLCORE_MUSICBRAINZ_REMOTE_ROOT_URL', DEFAULT_REMOTE_ROOT_URL)


def configured_download_dir() -> Path:
    return Path(getattr(settings, 'MLCORE_MUSICBRAINZ_DOWNLOAD_DIR', DEFAULT_DOWNLOAD_DIR))


def configured_timeout_seconds() -> int:
    return int(getattr(settings, 'MLCORE_MUSICBRAINZ_REMOTE_TIMEOUT_SECONDS', DEFAULT_TIMEOUT_SECONDS))


def configured_minimum_free_bytes() -> int:
    return int(getattr(settings, 'MLCORE_MUSICBRAINZ_MINIMUM_FREE_BYTES', DEFAULT_MINIMUM_FREE_BYTES))


def discover_musicbrainz_release(
    *,
    root_url: str | None = None,
    source_version: str | None = None,
    download_dir: str | Path | None = None,
    minimum_free_bytes: int | None = None,
) -> MusicBrainzReleasePlan:
    remote_root = (root_url or configured_remote_root_url()).rstrip('/') + '/'
    version = source_version or _read_text(urljoin(remote_root, 'LATEST')).strip()
    if not SOURCE_VERSION_RE.fullmatch(version):
        raise ValueError(f'Invalid MusicBrainz source version: {version!r}')

    release_url = urljoin(remote_root, f'{version}/')
    checksums = _parse_sha256s(_read_text(urljoin(release_url, 'SHA256SUMS')))
    expected_checksum = checksums.get(CORE_ARTIFACT_NAME)
    if not expected_checksum:
        raise ValueError(f'{CORE_ARTIFACT_NAME} is missing from MusicBrainz SHA256SUMS')

    artifact_url = urljoin(release_url, CORE_ARTIFACT_NAME)
    compressed_bytes = _remote_content_length(artifact_url)
    target_root = Path(download_dir) if download_dir is not None else configured_download_dir()
    release_dir = target_root / 'releases' / version
    required_free = configured_minimum_free_bytes() if minimum_free_bytes is None else minimum_free_bytes
    if required_free < 0:
        raise ValueError('minimum_free_bytes must be non-negative')

    return MusicBrainzReleasePlan(
        source_version=version,
        release_url=release_url,
        artifact=MusicBrainzArtifact(
            name=CORE_ARTIFACT_NAME,
            url=artifact_url,
            sha256=expected_checksum,
            compressed_bytes=compressed_bytes,
        ),
        target_root=str(target_root),
        release_dir=str(release_dir),
        manifest_path=str(release_dir / 'manifest.json'),
        estimated_expanded_bytes=DEFAULT_ESTIMATED_EXPANDED_BYTES,
        minimum_free_bytes=required_free,
        available_bytes=_available_bytes(target_root),
    )


def stage_musicbrainz_dump(
    *,
    root_url: str | None = None,
    source_version: str | None = None,
    download_dir: str | Path | None = None,
    minimum_free_bytes: int | None = None,
    force: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> MusicBrainzStageResult:
    plan = discover_musicbrainz_release(
        root_url=root_url,
        source_version=source_version,
        download_dir=download_dir,
        minimum_free_bytes=minimum_free_bytes,
    )
    release_dir = Path(plan.release_dir)
    raw_dir = release_dir / 'raw'
    staging_dir = release_dir / 'staging'
    artifact_path = raw_dir / plan.artifact.name
    manifest_path = Path(plan.manifest_path)

    raw_dir.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    if not force and _verified_existing_artifact(artifact_path, plan.artifact.sha256):
        _validate_required_members(artifact_path)
        manifest = _write_manifest(plan, artifact_path=artifact_path, staging_dir=staging_dir)
        successful_run = _successful_stage_run(plan.source_version, plan.artifact.sha256)
        if successful_run is None:
            successful_run = SourceIngestionRun.objects.create(
                source=MUSICBRAINZ_SOURCE_ID,
                import_mode='full',
                source_version=plan.source_version,
                raw_path=str(artifact_path),
                checksum=plan.artifact.sha256,
                fingerprint=_manifest_fingerprint(manifest),
                status='succeeded',
                policy_classification='production_approved',
                metadata={
                    'phase': 'dump_stage',
                    'adopted_existing_artifact': True,
                    'release_url': plan.release_url,
                    'artifact_url': plan.artifact.url,
                    'manifest_path': str(manifest_path),
                    'compressed_bytes': artifact_path.stat().st_size,
                    'staging_dir': str(staging_dir),
                    'required_members': list(REQUIRED_CORE_MEMBERS),
                },
                completed_at=timezone.now(),
            )
        return MusicBrainzStageResult(
            status='skipped',
            source_version=plan.source_version,
            artifact_path=str(artifact_path),
            manifest_path=str(manifest_path),
            checksum=plan.artifact.sha256,
            compressed_bytes=artifact_path.stat().st_size,
            downloaded=False,
            run_id=str(successful_run.id) if successful_run else None,
        )

    required_bytes = max(
        plan.minimum_free_bytes,
        plan.artifact.compressed_bytes + plan.estimated_expanded_bytes,
    )
    available_bytes = _available_bytes(Path(plan.target_root))
    if available_bytes < required_bytes:
        raise RuntimeError(
            'Insufficient MusicBrainz cold-storage capacity: '
            f'required={required_bytes} available={available_bytes} path={plan.target_root}'
        )

    run = SourceIngestionRun.objects.create(
        source=MUSICBRAINZ_SOURCE_ID,
        import_mode='full',
        source_version=plan.source_version,
        raw_path=str(artifact_path),
        checksum=plan.artifact.sha256,
        status='running',
        policy_classification='production_approved',
        metadata={
            'phase': 'dump_stage',
            'release_url': plan.release_url,
            'artifact_url': plan.artifact.url,
            'manifest_path': str(manifest_path),
            'minimum_free_bytes': required_bytes,
            'estimated_expanded_bytes': plan.estimated_expanded_bytes,
            'available_bytes_at_start': available_bytes,
            'required_members': list(REQUIRED_CORE_MEMBERS),
        },
    )
    try:
        _download_atomic(
            plan.artifact.url,
            artifact_path,
            expected_sha256=plan.artifact.sha256,
            expected_bytes=plan.artifact.compressed_bytes,
            progress_callback=progress_callback,
        )
        manifest = _write_manifest(plan, artifact_path=artifact_path, staging_dir=staging_dir)
        run.fingerprint = _manifest_fingerprint(manifest)
        run.status = 'succeeded'
        run.metadata = {
            **run.metadata,
            'compressed_bytes': artifact_path.stat().st_size,
            'staging_dir': str(staging_dir),
        }
        run.completed_at = timezone.now()
        run.save(update_fields=['fingerprint', 'status', 'metadata', 'completed_at'])
    except Exception as exc:
        run.status = 'failed'
        run.last_error = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'last_error', 'completed_at'])
        raise

    return MusicBrainzStageResult(
        status='succeeded',
        source_version=plan.source_version,
        artifact_path=str(artifact_path),
        manifest_path=str(manifest_path),
        checksum=plan.artifact.sha256,
        compressed_bytes=artifact_path.stat().st_size,
        downloaded=True,
        run_id=str(run.id),
    )


def _read_text(url: str) -> str:
    request = Request(url, headers={'User-Agent': 'Juke-MLCore/1.0'})
    with urlopen(request, timeout=configured_timeout_seconds()) as response:
        return response.read().decode('utf-8')


def _remote_content_length(url: str) -> int:
    request = Request(url, method='HEAD', headers={'User-Agent': 'Juke-MLCore/1.0'})
    with urlopen(request, timeout=configured_timeout_seconds()) as response:
        value = response.headers.get('Content-Length')
    if not value or not value.isdigit():
        raise ValueError(f'MusicBrainz artifact did not provide Content-Length: {url}')
    return int(value)


def _parse_sha256s(payload: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in payload.splitlines():
        match = SHA256_RE.fullmatch(line.strip())
        if match:
            checksums[match.group('name')] = match.group('checksum')
    return checksums


def _available_bytes(path: Path) -> int:
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    return shutil.disk_usage(existing).free


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_existing_artifact(path: Path, expected_sha256: str) -> bool:
    return path.is_file() and _sha256(path) == expected_sha256


def _download_atomic(
    url: str,
    destination: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    progress_callback: Callable[[dict[str, Any]], None] | None,
) -> None:
    partial_path = destination.with_name(f'{destination.name}.part')
    partial_path.unlink(missing_ok=True)
    digest = hashlib.sha256()
    downloaded_bytes = 0
    request = Request(url, headers={'User-Agent': 'Juke-MLCore/1.0'})
    try:
        with urlopen(request, timeout=configured_timeout_seconds()) as response, partial_path.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                downloaded_bytes += len(chunk)
                if progress_callback:
                    progress_callback({
                        'downloaded_bytes': downloaded_bytes,
                        'expected_bytes': expected_bytes,
                    })
            output.flush()
            os.fsync(output.fileno())
        if expected_bytes and downloaded_bytes != expected_bytes:
            raise ValueError(
                f'MusicBrainz artifact size mismatch: expected={expected_bytes} actual={downloaded_bytes}'
            )
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f'MusicBrainz artifact checksum mismatch: expected={expected_sha256} actual={actual_sha256}'
            )
        _validate_required_members(partial_path)
        partial_path.replace(destination)
    except Exception:
        partial_path.unlink(missing_ok=True)
        raise


def _validate_required_members(artifact_path: Path) -> None:
    with tarfile.open(artifact_path, mode='r:bz2') as archive:
        member_names = {member.name.removeprefix('./') for member in archive.getmembers() if member.isfile()}
    missing = sorted(set(REQUIRED_CORE_MEMBERS) - member_names)
    if missing:
        raise ValueError(f'MusicBrainz core dump is missing required members: {", ".join(missing)}')


def _write_manifest(
    plan: MusicBrainzReleasePlan,
    *,
    artifact_path: Path,
    staging_dir: Path,
) -> dict[str, Any]:
    manifest = {
        'source': MUSICBRAINZ_SOURCE_ID,
        'source_version': plan.source_version,
        'release_url': plan.release_url,
        'manifest_version': 1,
        'staged_at': datetime.now(UTC).isoformat(),
        'raw_dir': str(artifact_path.parent),
        'staging_dir': str(staging_dir),
        'estimated_expanded_bytes': plan.estimated_expanded_bytes,
        'required_members': list(REQUIRED_CORE_MEMBERS),
        'artifacts': [
            {
                **asdict(plan.artifact),
                'path': str(artifact_path),
                'actual_bytes': artifact_path.stat().st_size,
            }
        ],
    }
    manifest_path = Path(plan.manifest_path)
    temp_path = manifest_path.with_suffix('.json.tmp')
    temp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temp_path.replace(manifest_path)
    return manifest


def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
    stable = {
        'source': manifest['source'],
        'source_version': manifest['source_version'],
        'manifest_version': manifest['manifest_version'],
        'required_members': manifest['required_members'],
        'artifacts': [
            {
                'name': artifact['name'],
                'sha256': artifact['sha256'],
                'actual_bytes': artifact['actual_bytes'],
            }
            for artifact in manifest['artifacts']
        ],
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode('utf-8')).hexdigest()


def _successful_stage_run(source_version: str, checksum: str) -> SourceIngestionRun | None:
    return (
        SourceIngestionRun.objects.filter(
            source=MUSICBRAINZ_SOURCE_ID,
            source_version=source_version,
            checksum=checksum,
            status='succeeded',
            metadata__phase='dump_stage',
        )
        .order_by('-started_at')
        .first()
    )

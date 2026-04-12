from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from mlcore.ingestion.listenbrainz import (
    configured_dump_path,
    import_listenbrainz_dump,
    infer_source_version_from_path,
)
from mlcore.services.dataset_orchestration import (
    DatasetMaterializationResult,
    DatasetOrchestrationPlan,
    configured_dataset_max_shards_per_run,
    configured_dataset_shard_parallelism,
)
from mlcore.services.listenbrainz_source import configured_download_dir

LISTENBRAINZ_MANIFEST_VERSION = 1


@dataclass(frozen=True)
class MaterializedListenBrainzShard:
    member_name: str
    relative_path: str
    year: int
    month: int
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class ListenBrainzShardMaterializationResult:
    source_version: str
    archive_path: str
    output_root: str
    manifest_path: str
    shard_count: int
    total_uncompressed_bytes: int


def configured_listenbrainz_shard_root() -> Path:
    return configured_download_dir() / 'shards'


def materialize_listenbrainz_shards(
    archive_path: str | Path,
    *,
    source_version: str | None = None,
    shard_root: str | Path | None = None,
    force: bool = False,
    shard_parallelism: int | None = None,
    max_shards_per_run: int | None = None,
) -> ListenBrainzShardMaterializationResult:
    path = Path(archive_path)
    if not path.exists():
        raise FileNotFoundError(f'ListenBrainz archive not found: {path}')

    resolved_source_version = source_version or infer_source_version_from_path(path)
    resolved_shard_root = Path(shard_root) if shard_root is not None else configured_listenbrainz_shard_root()
    output_root = resolved_shard_root / resolved_source_version
    manifest_path = output_root / 'manifest.json'

    if output_root.exists():
        if not force:
            if manifest_path.exists():
                return _rewrite_listenbrainz_orchestration_plan(
                    archive_path=path,
                    source_version=resolved_source_version,
                    output_root=output_root,
                    manifest_path=manifest_path,
                    shard_parallelism=shard_parallelism,
                    max_shards_per_run=max_shards_per_run,
                )
            raise ValueError(
                f'Shard output already exists at {output_root}; rerun with force=True to replace it'
            )
        shutil.rmtree(output_root)

    output_root.mkdir(parents=True, exist_ok=True)

    shards: list[MaterializedListenBrainzShard] = []
    total_uncompressed_bytes = 0
    with tarfile.open(path, 'r:*') as archive:
        for member in archive:
            relative_path = _listen_shard_relative_path(member.name)
            if relative_path is None:
                continue

            extracted = archive.extractfile(member)
            if extracted is None:
                continue

            destination = output_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp_destination = destination.with_name(destination.name + '.part')
            if temp_destination.exists():
                temp_destination.unlink()

            digest = hashlib.sha256()
            size_bytes = 0
            with temp_destination.open('wb') as handle:
                while True:
                    chunk = extracted.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
            temp_destination.replace(destination)

            year, month = _parse_year_month(relative_path)
            shards.append(
                MaterializedListenBrainzShard(
                    member_name=member.name,
                    relative_path=relative_path.as_posix(),
                    year=year,
                    month=month,
                    size_bytes=size_bytes,
                    sha256=digest.hexdigest(),
                )
            )
            total_uncompressed_bytes += size_bytes

    if not shards:
        raise ValueError(f'No ListenBrainz monthly listen shards found in {path}')

    manifest = {
        'manifest_version': LISTENBRAINZ_MANIFEST_VERSION,
        'source': 'listenbrainz',
        'import_mode': 'full',
        'source_version': resolved_source_version,
        'archive_path': str(path),
        'archive_size_bytes': path.stat().st_size,
        'created_at': datetime.now(tz=UTC).isoformat(),
        'shard_count': len(shards),
        'total_uncompressed_bytes': total_uncompressed_bytes,
        'shards': [
            {
                'member_name': shard.member_name,
                'relative_path': shard.relative_path,
                'year': shard.year,
                'month': shard.month,
                'size_bytes': shard.size_bytes,
                'sha256': shard.sha256,
            }
            for shard in shards
        ],
    }
    temp_manifest_path = manifest_path.with_name(manifest_path.name + '.tmp')
    temp_manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temp_manifest_path.replace(manifest_path)

    return _rewrite_listenbrainz_orchestration_plan(
        archive_path=path,
        source_version=resolved_source_version,
        output_root=output_root,
        manifest_path=manifest_path,
        shard_parallelism=shard_parallelism,
        max_shards_per_run=max_shards_per_run,
    )


def build_listenbrainz_shard_orchestration(
    *,
    source_version: str,
    manifest_path: str | Path,
    output_root: str | Path,
    shard_parallelism: int | None = None,
    max_shards_per_run: int | None = None,
) -> DatasetOrchestrationPlan:
    resolved_shard_parallelism = max(1, shard_parallelism or configured_dataset_shard_parallelism())
    resolved_max_shards = max_shards_per_run if max_shards_per_run is not None else configured_dataset_max_shards_per_run()
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    scheduled_shards = _scheduled_shards_from_manifest(manifest, max_shards_per_run=resolved_max_shards)
    return DatasetOrchestrationPlan(
        provider='listenbrainz',
        source_version=source_version,
        manifest_path=str(manifest_path),
        output_root=str(output_root),
        orchestration_path=str(Path(output_root) / 'orchestration.json'),
        shard_parallelism=resolved_shard_parallelism,
        max_shards_per_run=resolved_max_shards,
        shard_count=int(manifest['shard_count']),
        scheduled_shard_count=len(scheduled_shards),
        total_uncompressed_bytes=int(manifest['total_uncompressed_bytes']),
        scheduled_uncompressed_bytes=sum(int(shard['size_bytes']) for shard in scheduled_shards),
    )


def _rewrite_listenbrainz_orchestration_plan(
    *,
    archive_path: str | Path,
    source_version: str,
    output_root: str | Path,
    manifest_path: str | Path,
    shard_parallelism: int | None = None,
    max_shards_per_run: int | None = None,
) -> ListenBrainzShardMaterializationResult:
    resolved_output_root = Path(output_root)
    resolved_manifest_path = Path(manifest_path)
    manifest = json.loads(resolved_manifest_path.read_text(encoding='utf-8'))
    orchestration = build_listenbrainz_shard_orchestration(
        source_version=source_version,
        manifest_path=resolved_manifest_path,
        output_root=resolved_output_root,
        shard_parallelism=shard_parallelism,
        max_shards_per_run=max_shards_per_run,
    )
    orchestration_path = resolved_output_root / 'orchestration.json'
    temp_orchestration_path = orchestration_path.with_name(orchestration_path.name + '.tmp')
    temp_orchestration_path.write_text(
        json.dumps(
            {
                'provider': orchestration.provider,
                'source_version': orchestration.source_version,
                'manifest_path': orchestration.manifest_path,
                'output_root': orchestration.output_root,
                'orchestration_path': orchestration.orchestration_path,
                'shard_parallelism': orchestration.shard_parallelism,
                'max_shards_per_run': orchestration.max_shards_per_run,
                'shard_count': orchestration.shard_count,
                'scheduled_shard_count': orchestration.scheduled_shard_count,
                'total_uncompressed_bytes': orchestration.total_uncompressed_bytes,
                'scheduled_uncompressed_bytes': orchestration.scheduled_uncompressed_bytes,
                'progress_fields': [
                    'source_row_count',
                    'imported_row_count',
                    'duplicate_row_count',
                    'canonicalized_row_count',
                    'unresolved_row_count',
                    'malformed_row_count',
                ],
                'shards': _scheduled_shards_from_manifest(manifest, max_shards_per_run=orchestration.max_shards_per_run),
            },
            indent=2,
            sort_keys=True,
        )
        + '\n',
        encoding='utf-8',
    )
    temp_orchestration_path.replace(orchestration_path)
    return ListenBrainzShardMaterializationResult(
        source_version=source_version,
        archive_path=str(archive_path),
        output_root=str(resolved_output_root),
        manifest_path=str(resolved_manifest_path),
        shard_count=int(manifest['shard_count']),
        total_uncompressed_bytes=int(manifest['total_uncompressed_bytes']),
    )


def _scheduled_shards_from_manifest(
    manifest: dict[str, object],
    *,
    max_shards_per_run: int | None,
) -> list[dict[str, object]]:
    shards = list(manifest['shards'])
    if max_shards_per_run is None:
        return shards
    return shards[:max_shards_per_run]


def _listen_shard_relative_path(member_name: str) -> Path | None:
    parts = PurePosixPath(member_name).parts
    if 'listens' not in parts:
        return None
    listens_index = parts.index('listens')
    relative_parts = parts[listens_index:]
    if len(relative_parts) != 3:
        return None
    _, year, filename = relative_parts
    month = Path(filename).stem
    if not year.isdigit() or not month.isdigit() or not filename.endswith('.listens'):
        return None
    return Path(*relative_parts)


def _parse_year_month(relative_path: Path) -> tuple[int, int]:
    return int(relative_path.parts[1]), int(relative_path.stem)


class ListenBrainzShardOrchestrationService:
    provider = 'listenbrainz'
    import_mode = 'full'

    def configured_archive_path(self) -> str | None:
        return configured_dump_path('full')

    def configured_shard_root(self) -> Path:
        return configured_listenbrainz_shard_root()

    def materialize_shards(
        self,
        archive_path: str | Path,
        *,
        source_version: str | None = None,
        shard_root: str | Path | None = None,
        force: bool = False,
        shard_parallelism: int | None = None,
        max_shards_per_run: int | None = None,
    ) -> DatasetMaterializationResult:
        materialized = materialize_listenbrainz_shards(
            archive_path,
            source_version=source_version,
            shard_root=shard_root,
            force=force,
            shard_parallelism=shard_parallelism,
            max_shards_per_run=max_shards_per_run,
        )
        orchestration = build_listenbrainz_shard_orchestration(
            source_version=materialized.source_version,
            manifest_path=materialized.manifest_path,
            output_root=materialized.output_root,
            shard_parallelism=shard_parallelism,
            max_shards_per_run=max_shards_per_run,
        )
        return DatasetMaterializationResult(
            provider=self.provider,
            source_version=materialized.source_version,
            archive_path=materialized.archive_path,
            output_root=materialized.output_root,
            manifest_path=materialized.manifest_path,
            orchestration_path=orchestration.orchestration_path,
            shard_count=materialized.shard_count,
            total_uncompressed_bytes=materialized.total_uncompressed_bytes,
            shard_parallelism=orchestration.shard_parallelism,
            max_shards_per_run=orchestration.max_shards_per_run,
        )

    def import_shard(
        self,
        shard_path: str | Path,
        *,
        source_version: str,
        progress_callback=None,
    ):
        return import_listenbrainz_dump(
            shard_path,
            source_version=source_version,
            import_mode=self.import_mode,
            progress_callback=progress_callback,
            resume=True,
        )


LISTENBRAINZ_SHARD_SERVICE = ListenBrainzShardOrchestrationService()

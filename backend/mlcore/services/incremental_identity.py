from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from django.utils import timezone

from mlcore.models import SourceIngestionRun
from mlcore.services.listenbrainz_identity_bridge import (
    expand_listenbrainz_identity_graph,
    import_listenbrainz_identity_bridge,
    resolve_listenbrainz_identity_conflicts,
)
from mlcore.services.listenbrainz_shards import materialize_listenbrainz_shards
from mlcore.services.listenbrainz_source import RemoteSyncResult, sync_listenbrainz_remote_dumps

logger = logging.getLogger(__name__)

INCREMENTAL_IDENTITY_SOURCE_ID = 'mlcore-incremental-identity'
LISTENBRAINZ_SOURCE_ID = 'listenbrainz'
LISTENBRAINZ_IDENTITY_SOURCE_ID = 'listenbrainz-identity-bridge'


@dataclass(frozen=True)
class IncrementalIdentityVersionResult:
    source_version: str
    archive_path: str
    manifest_path: str
    shard_count: int
    active_mapping_count: int
    conflict_msid_count: int
    redirect_count: int
    redirect_conflict_count: int
    expansion_created_msid_count: int
    conflict_resolved_msid_count: int
    conflict_resolution_redirect_count: int


@dataclass(frozen=True)
class IncrementalIdentityIngestionResult:
    run_id: str
    status: str
    synced_full_source_version: str | None
    synced_incremental_source_versions: list[str]
    skipped_source_versions: list[str]
    processed_versions: list[IncrementalIdentityVersionResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0


def run_incremental_identity_ingestion(
    *,
    max_incrementals: int = 14,
    include_existing_unprocessed: bool = True,
    dry_run: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> IncrementalIdentityIngestionResult:
    started = time.monotonic()
    run = SourceIngestionRun.objects.create(
        source=INCREMENTAL_IDENTITY_SOURCE_ID,
        import_mode='incremental',
        source_version=timezone.now().strftime('incremental-identity-%Y%m%d%H%M%S'),
        raw_path='',
        checksum='',
        status='running',
        policy_classification='production_approved',
        metadata={
            'phase': 'sync',
            'max_incrementals': max_incrementals,
            'include_existing_unprocessed': include_existing_unprocessed,
            'dry_run': dry_run,
        },
    )
    processed: list[IncrementalIdentityVersionResult] = []
    try:
        sync_result = (
            RemoteSyncResult(
                status='dry_run',
                policy_classification='n/a',
                full_source_version=None,
                incremental_source_versions=[],
                downloaded_paths=[],
                skipped_source_versions=[],
            )
            if dry_run
            else sync_listenbrainz_remote_dumps(max_incrementals_per_run=max_incrementals)
        )
        candidate_versions = [
            version
            for version in [
                sync_result.full_source_version,
                *sync_result.incremental_source_versions,
            ]
            if version
        ]
        if include_existing_unprocessed:
            candidate_versions.extend(_existing_unprocessed_listenbrainz_versions(limit=max_incrementals))
        candidate_versions = _dedupe_preserving_order(candidate_versions)
        _report(progress_callback, {
            'event': 'incremental_identity_sync_complete',
            'candidate_versions': candidate_versions,
            'sync_status': sync_result.status,
        })
        run.metadata = {
            **run.metadata,
            'phase': 'identity',
            'sync_status': sync_result.status,
            'synced_full_source_version': sync_result.full_source_version,
            'synced_incremental_source_versions': sync_result.incremental_source_versions,
            'skipped_source_versions': sync_result.skipped_source_versions,
            'candidate_versions': candidate_versions,
        }
        run.save(update_fields=['metadata'])

        if not dry_run:
            for index, source_version in enumerate(candidate_versions, start=1):
                version_result = _process_listenbrainz_identity_version(source_version)
                processed.append(version_result)
                run.metadata = {
                    **run.metadata,
                    'processed_versions': [result.__dict__ for result in processed],
                    'completed_versions': index,
                    'total_versions': len(candidate_versions),
                    'current_source_version': source_version,
                }
                run.imported_row_count = sum(result.active_mapping_count for result in processed)
                run.canonicalized_row_count = sum(
                    result.redirect_count + result.conflict_resolution_redirect_count
                    for result in processed
                )
                run.unresolved_row_count = sum(result.conflict_msid_count for result in processed)
                run.save(update_fields=[
                    'metadata',
                    'imported_row_count',
                    'canonicalized_row_count',
                    'unresolved_row_count',
                ])
                _report(progress_callback, {
                    'event': 'incremental_identity_version_complete',
                    **version_result.__dict__,
                })

        run.status = 'succeeded'
        run.completed_at = timezone.now()
        elapsed_seconds = time.monotonic() - started
        run.metadata = {
            **run.metadata,
            'phase': 'complete',
            'elapsed_seconds': elapsed_seconds,
        }
        run.save(update_fields=['status', 'completed_at', 'metadata'])
        return IncrementalIdentityIngestionResult(
            run_id=str(run.id),
            status=run.status,
            synced_full_source_version=sync_result.full_source_version,
            synced_incremental_source_versions=sync_result.incremental_source_versions,
            skipped_source_versions=sync_result.skipped_source_versions,
            processed_versions=processed,
            elapsed_seconds=elapsed_seconds,
        )
    except Exception as exc:
        run.status = 'failed'
        run.last_error = str(exc)
        run.completed_at = timezone.now()
        run.metadata = {**run.metadata, 'phase': 'failed'}
        run.save(update_fields=['status', 'last_error', 'completed_at', 'metadata'])
        raise


def _process_listenbrainz_identity_version(source_version: str) -> IncrementalIdentityVersionResult:
    source_run = _latest_listenbrainz_source_run(source_version)
    archive_path = source_run.raw_path
    materialized = materialize_listenbrainz_shards(archive_path, source_version=source_version)
    bridge = import_listenbrainz_identity_bridge(materialized.manifest_path)
    expansion = expand_listenbrainz_identity_graph(source_version)
    conflict = resolve_listenbrainz_identity_conflicts(source_version)
    return IncrementalIdentityVersionResult(
        source_version=source_version,
        archive_path=archive_path,
        manifest_path=materialized.manifest_path,
        shard_count=materialized.shard_count,
        active_mapping_count=bridge.active_mapping_count,
        conflict_msid_count=bridge.conflict_msid_count,
        redirect_count=expansion.redirect_count,
        redirect_conflict_count=expansion.redirect_conflict_count,
        expansion_created_msid_count=expansion.created_msid_count,
        conflict_resolved_msid_count=conflict.resolved_msid_count,
        conflict_resolution_redirect_count=conflict.redirect_count,
    )


def _latest_listenbrainz_source_run(source_version: str) -> SourceIngestionRun:
    run = SourceIngestionRun.objects.filter(
        source=LISTENBRAINZ_SOURCE_ID,
        source_version=source_version,
        status='succeeded',
    ).order_by('-completed_at', '-started_at').first()
    if run is None:
        raise ValueError(f'No successful ListenBrainz source ingestion run found for {source_version}')
    if not run.raw_path or not Path(run.raw_path).exists():
        raise FileNotFoundError(f'ListenBrainz archive is missing for {source_version}: {run.raw_path}')
    return run


def _existing_unprocessed_listenbrainz_versions(*, limit: int) -> list[str]:
    successful_identity_versions = set(
        SourceIngestionRun.objects.filter(
            source=LISTENBRAINZ_IDENTITY_SOURCE_ID,
            status='succeeded',
        ).values_list('source_version', flat=True)
    )
    versions: list[str] = []
    for source_version in SourceIngestionRun.objects.filter(
        source=LISTENBRAINZ_SOURCE_ID,
        status='succeeded',
    ).exclude(
        import_mode='full',
    ).order_by('completed_at', 'started_at').values_list('source_version', flat=True):
        if source_version not in successful_identity_versions:
            versions.append(source_version)
        if len(versions) >= limit:
            break
    return versions


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _report(callback: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
    if callback:
        callback(payload)

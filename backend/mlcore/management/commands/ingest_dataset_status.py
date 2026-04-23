from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from mlcore.services.full_ingestion import (
    configured_full_ingestion_scratch_root,
    full_ingestion_cleanup_status,
    full_ingestion_finalize_status,
    full_ingestion_manifest_path,
    full_ingestion_partition_state_counts,
    full_ingestion_runtime_residue_counts,
    get_full_ingestion_provider,
    load_full_ingestion_plan,
)


class Command(BaseCommand):
    help = 'Show the current manifest-backed status for one provider full-ingestion run.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--provider',
            required=True,
            help='Dataset provider name, for example listenbrainz.',
        )
        parser.add_argument(
            '--archive-path',
            default='',
            help='Optional archive path used to infer the source version.',
        )
        parser.add_argument(
            '--source-version',
            default='',
            help='Explicit source-version label. Required when archive-path is omitted.',
        )
        parser.add_argument(
            '--scratch-root',
            default=str(configured_full_ingestion_scratch_root()),
            help='Scratch root where the full-ingestion run manifest lives.',
        )
        parser.add_argument(
            '--manifest-path',
            default='',
            help='Optional explicit manifest path. Overrides provider/source-version lookup.',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Emit a JSON summary instead of the compact text form.',
        )

    def handle(self, *args, **options):
        provider_name = str(options['provider'] or '').strip()
        provider = get_full_ingestion_provider(provider_name)
        manifest_path = str(options['manifest_path'] or '').strip()
        source_version = str(options['source_version'] or '').strip()
        archive_path = str(options['archive_path'] or '').strip()

        if not manifest_path:
            if not source_version:
                configured_archive_path = archive_path or provider.configured_archive_path() or ''
                if not configured_archive_path:
                    raise CommandError(
                        'source-version or archive-path is required when manifest-path is not provided.'
                    )
                source_version = provider.infer_source_version(configured_archive_path)
            manifest_path = str(
                full_ingestion_manifest_path(
                    provider=provider.provider,
                    source_version=source_version,
                    scratch_root=str(options['scratch_root'] or '').strip() or None,
                )
            )

        try:
            plan = load_full_ingestion_plan(manifest_path)
        except FileNotFoundError as exc:
            raise CommandError(f'No full-ingestion manifest found at {manifest_path}.') from exc

        partition_states = full_ingestion_partition_state_counts(plan)
        finalize_status = full_ingestion_finalize_status(plan)
        cleanup_status = full_ingestion_cleanup_status(plan)
        runtime_residue = full_ingestion_runtime_residue_counts(plan)
        payload = {
            'provider': plan.provider,
            'source_version': plan.source_version,
            'run_id': plan.run_id,
            'stage': plan.stage,
            'status': plan.status,
            'source_ingestion_run_id': plan.source_ingestion_run_id,
            'manifest_path': plan.manifest_path,
            'metrics_path': plan.metrics_path,
            'archive_path': plan.archive_path,
            'partition_count': plan.partition_count,
            'policy_mode': plan.policy_mode,
            'partition_worker_budget': plan.partition_worker_budget,
            'load_worker_budget': plan.load_worker_budget,
            'merge_worker_budget': plan.merge_worker_budget,
            'scratch_soft_cap_bytes': plan.scratch_soft_cap_bytes,
            'partition_states': partition_states,
            'finalize': finalize_status,
            'cleanup': {
                **cleanup_status,
                **runtime_residue,
            },
            'counters': dict(plan.counters),
            'created_at': plan.created_at,
            'updated_at': plan.updated_at,
        }

        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self.stdout.write(
            (
                'provider={provider} source_version={source_version} run_id={run_id} '
                'stage={stage} status={status} '
                'policy={policy} budgets=partition:{partition_budget},load:{load_budget},merge:{merge_budget} '
                'partitions={partitions} states={states} '
                'rows_parsed={rows_parsed} '
                'candidates=mbid:{rows_with_mbid_candidate},'
                'spotify:{rows_with_spotify_candidate},'
                'none:{rows_with_no_candidate} '
                'resolved=total:{rows_resolved},'
                'mbid:{rows_resolved_by_mbid},'
                'spotify:{rows_resolved_by_spotify} '
                'rows_staged={rows_staged} session_rows_loaded={session_rows_loaded} '
                'chunks_written={chunks_written} chunks_loaded={chunks_loaded} rows_merged={rows_merged} '
                'rows_deduplicated={rows_deduplicated} unresolved={rows_unresolved} malformed={rows_malformed} '
                'finalize=phase:{finalize_phase},drained:{drained_partitions}/{partitions},'
                'hot_build:{hot_built_partitions}/{partitions},'
                'drain_backlog:{drain_backlog_partitions},'
                'hot_gap:{hot_build_gap_partitions},'
                'indexes:{shadow_indexes_complete},swap:{swap_completed} '
                'cleanup=partition_root:{partition_root_exists},logs:{log_root_exists},'
                'spool:{spool_exists},events:{partition_event_artifacts_present},'
                'run_residue:{run_root_residue_bytes},'
                'event_load_rows:{event_load_rows},session_load_rows:{session_load_rows},'
                'session_stage_rows:{session_stage_rows},checkpoints:{finalize_checkpoint_rows} '
                'host=device_util:{host_device_util_milli_pct}milli_pct,'
                'iowait:{host_iowait_milli_pct}milli_pct,'
                'mem_avail:{host_available_memory_bytes},'
                'swap_used:{host_swap_used_bytes},'
                'scratch_actual:{scratch_actual_bytes} '
                'manifest={manifest}'
            ).format(
                provider=plan.provider,
                source_version=plan.source_version,
                run_id=plan.run_id,
                stage=plan.stage,
                status=plan.status,
                policy=plan.policy_mode,
                partition_budget=plan.partition_worker_budget,
                load_budget=plan.load_worker_budget,
                merge_budget=plan.merge_worker_budget,
                partitions=plan.partition_count,
                states=','.join(f'{state}:{count}' for state, count in sorted(partition_states.items())),
                rows_parsed=int(plan.counters.get('rows_parsed') or 0),
                rows_with_mbid_candidate=int(plan.counters.get('rows_with_mbid_candidate') or 0),
                rows_with_spotify_candidate=int(plan.counters.get('rows_with_spotify_candidate') or 0),
                rows_with_no_candidate=int(plan.counters.get('rows_with_no_candidate') or 0),
                rows_resolved=int(plan.counters.get('rows_resolved') or 0),
                rows_resolved_by_mbid=int(plan.counters.get('rows_resolved_by_mbid') or 0),
                rows_resolved_by_spotify=int(plan.counters.get('rows_resolved_by_spotify') or 0),
                rows_staged=int(plan.counters.get('rows_staged') or 0),
                session_rows_loaded=int(plan.counters.get('session_rows_loaded') or 0),
                chunks_written=int(plan.counters.get('chunks_written') or 0),
                chunks_loaded=int(plan.counters.get('chunks_loaded') or 0),
                rows_merged=int(plan.counters.get('rows_merged') or 0),
                rows_deduplicated=int(plan.counters.get('rows_deduplicated') or 0),
                rows_unresolved=int(plan.counters.get('rows_unresolved') or 0),
                rows_malformed=int(plan.counters.get('rows_malformed') or 0),
                finalize_phase=str(finalize_status['phase']),
                drained_partitions=int(finalize_status['drained_partitions']),
                hot_built_partitions=int(finalize_status['hot_built_partitions']),
                drain_backlog_partitions=int(finalize_status['drain_backlog_partitions']),
                hot_build_gap_partitions=int(finalize_status['hot_build_gap_partitions']),
                shadow_indexes_complete=int(bool(finalize_status['shadow_indexes_complete'])),
                swap_completed=int(bool(finalize_status['swap_completed'])),
                partition_root_exists=int(bool(cleanup_status['partition_root_exists'])),
                log_root_exists=int(bool(cleanup_status['log_root_exists'])),
                spool_exists=int(bool(cleanup_status['spool_exists'])),
                partition_event_artifacts_present=int(bool(cleanup_status['partition_event_artifacts_present'])),
                run_root_residue_bytes=int(cleanup_status['run_root_residue_bytes']),
                event_load_rows=int(runtime_residue['event_load_rows']),
                session_load_rows=int(runtime_residue['session_load_rows']),
                session_stage_rows=int(runtime_residue['session_stage_rows']),
                finalize_checkpoint_rows=int(runtime_residue['finalize_checkpoint_rows']),
                host_device_util_milli_pct=int(plan.counters.get('host_device_util_milli_pct') or 0),
                host_iowait_milli_pct=int(plan.counters.get('host_iowait_milli_pct') or 0),
                host_available_memory_bytes=int(plan.counters.get('host_available_memory_bytes') or 0),
                host_swap_used_bytes=int(plan.counters.get('host_swap_used_bytes') or 0),
                scratch_actual_bytes=int(plan.counters.get('scratch_actual_bytes') or 0),
                manifest=plan.manifest_path,
            )
        )

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from mlcore.services.full_ingestion import (
    acquire_full_ingestion_lease,
    build_full_ingestion_plan,
    configured_full_ingestion_load_workers,
    configured_full_ingestion_merge_workers,
    configured_full_ingestion_partition_count,
    configured_full_ingestion_partition_workers,
    configured_full_ingestion_scratch_root,
    execute_full_ingestion_copy_stage,
    execute_full_ingestion_merge_stage,
    execute_full_ingestion_pipeline,
    execute_full_ingestion_partition_stage,
    FullIngestionLeaseHeldError,
    get_full_ingestion_provider,
    initialize_full_ingestion_plan,
    load_full_ingestion_plan,
    release_full_ingestion_lease,
    touch_full_ingestion_lease,
    write_full_ingestion_metrics,
)


class Command(BaseCommand):
    help = (
        'Plan a provider-aware full dataset ingestion run, write a durable manifest under NVMe scratch, '
        'and publish aggregate progress metrics through the existing node_exporter textfile collector.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--provider',
            required=True,
            help='Dataset provider name, for example listenbrainz.',
        )
        parser.add_argument(
            '--archive-path',
            default='',
            help='Path to the provider full archive. Defaults to the provider-configured full import path.',
        )
        parser.add_argument(
            '--source-version',
            default='',
            help='Optional explicit source-version label. Defaults to the archive filename.',
        )
        parser.add_argument(
            '--scratch-root',
            default=str(configured_full_ingestion_scratch_root()),
            help='NVMe scratch root for full-ingestion manifests, partition files, and logs.',
        )
        parser.add_argument(
            '--partition-count',
            type=int,
            default=configured_full_ingestion_partition_count(),
            help='Number of fixed hash partitions to plan for the full-ingestion run.',
        )
        parser.add_argument(
            '--partition-workers',
            type=int,
            default=configured_full_ingestion_partition_workers(),
            help='Target process count for archive -> compact chunk extraction after member spooling.',
        )
        parser.add_argument(
            '--load-workers',
            type=int,
            default=configured_full_ingestion_load_workers(),
            help='Target worker count for compact event chunk -> load table COPY work.',
        )
        parser.add_argument(
            '--merge-workers',
            type=int,
            default=configured_full_ingestion_merge_workers(),
            help='Reserved provider finalization parallelism hint. ListenBrainz currently finalizes set-wise in one swap.',
        )
        parser.add_argument(
            '--materialized-manifest-path',
            default='',
            help=(
                'Optional path to an existing monthly shard manifest used to estimate per-partition input bytes. '
                'Defaults to the provider-discovered materialized manifest for the same source version.'
            ),
        )
        parser.add_argument(
            '--metrics-path',
            default='',
            help='Optional explicit Prometheus textfile path. Defaults to the configured node_exporter path.',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Replace an existing planned full-ingestion run root for the same provider and source version.',
        )
        parser.add_argument(
            '--resume',
            action='store_true',
            help='Load an existing manifest for the same provider and source version and refresh metrics instead of recreating it.',
        )
        parser.add_argument(
            '--execute-partition-stage',
            action='store_true',
            help='Run Stage A now and extract compact provider event chunks under the scratch root.',
        )
        parser.add_argument(
            '--execute-copy-stage',
            action='store_true',
            help='Run Stage B now and load compact event chunks into the provider load tables.',
        )
        parser.add_argument(
            '--execute-merge-stage',
            action='store_true',
            help='Run Stage C now and finalize the provider load tables into the compact hot/cold tables.',
        )
        parser.add_argument(
            '--execute-pipeline',
            action='store_true',
            help=(
                'Run the full-ingestion pipeline end to end: extract compact chunks, '
                'load lean tables, and finalize into the compact hot/cold tables.'
            ),
        )

    def handle(self, *args, **options):
        provider_name = str(options['provider'] or '').strip()
        provider = get_full_ingestion_provider(provider_name)
        archive_path = str(options['archive_path'] or '').strip() or provider.configured_archive_path() or ''
        if not archive_path:
            raise CommandError(
                f'archive-path is required or the provider must expose a configured default archive path ({provider.provider})'
            )

        plan = build_full_ingestion_plan(
            provider.provider,
            archive_path,
            source_version=str(options['source_version'] or '').strip() or None,
            scratch_root=str(options['scratch_root'] or '').strip() or None,
            partition_count=int(options['partition_count']),
            partition_workers=int(options['partition_workers']),
            load_workers=int(options['load_workers']),
            merge_workers=int(options['merge_workers']),
            materialized_manifest_path=str(options['materialized_manifest_path'] or '').strip() or None,
            metrics_path=str(options['metrics_path'] or '').strip() or None,
        )

        execute_requested = any(
            options[flag]
            for flag in (
                'execute_partition_stage',
                'execute_copy_stage',
                'execute_merge_stage',
                'execute_pipeline',
            )
        )

        if options['resume']:
            try:
                existing_plan = load_full_ingestion_plan(plan.manifest_path)
            except FileNotFoundError as exc:
                raise CommandError(
                    f'No existing full-ingestion manifest found at {plan.manifest_path}; cannot resume.'
                ) from exc
            existing_plan = self._execute_requested_stages(existing_plan, options, execute_requested=execute_requested)
            write_full_ingestion_metrics(existing_plan)
            self.stdout.write(
                (
                    'resumed provider={provider} source_version={source_version} stage={stage} status={status} '
                    'partitions={partitions} manifest={manifest} metrics={metrics}'
                ).format(
                    provider=existing_plan.provider,
                    source_version=existing_plan.source_version,
                    stage=existing_plan.stage,
                    status=existing_plan.status,
                    partitions=existing_plan.partition_count,
                    manifest=existing_plan.manifest_path,
                    metrics=existing_plan.metrics_path or '-',
                )
            )
            return

        try:
            initialize_full_ingestion_plan(plan, force=bool(options['force']))
        except FileExistsError as exc:
            raise CommandError(str(exc)) from exc

        plan = self._execute_requested_stages(plan, options, execute_requested=execute_requested)

        if options['execute_pipeline'] or options['execute_merge_stage']:
            action = 'completed'
        elif options['execute_copy_stage']:
            action = 'loaded'
        elif options['execute_partition_stage']:
            action = 'partitioned'
        else:
            action = 'planned'
        self.stdout.write(
            (
                '{action} provider={provider} source_version={source_version} stage={stage} status={status} '
                'partitions={partitions} partition_workers={partition_workers} '
                'load_workers={load_workers} merge_workers={merge_workers} '
                'estimated_bytes={estimated_bytes} manifest={manifest} metrics={metrics} '
                'materialized_manifest={materialized_manifest}'
            ).format(
                action=action,
                provider=plan.provider,
                source_version=plan.source_version,
                stage=plan.stage,
                status=plan.status,
                partitions=plan.partition_count,
                partition_workers=plan.partition_workers,
                load_workers=plan.load_workers,
                merge_workers=plan.merge_workers,
                estimated_bytes=plan.total_estimated_uncompressed_bytes,
                manifest=plan.manifest_path,
                metrics=plan.metrics_path or '-',
                materialized_manifest=plan.materialized_manifest_path or '-',
            )
        )

    def _execute_requested_stages(self, plan, options, *, execute_requested: bool):
        if not execute_requested:
            return plan

        try:
            acquire_full_ingestion_lease(
                provider=plan.provider,
                run_id=plan.run_id,
                source_version=plan.source_version,
                stage=plan.stage,
                metadata={
                    'manifest_path': plan.manifest_path,
                    'archive_path': plan.archive_path,
                    'source_version': plan.source_version,
                },
            )
        except FullIngestionLeaseHeldError as exc:
            raise CommandError(str(exc)) from exc

        try:
            if options['execute_partition_stage']:
                plan = execute_full_ingestion_partition_stage(plan, force=bool(options['force']))
            if options['execute_copy_stage']:
                if plan.stage == 'planned':
                    plan = execute_full_ingestion_partition_stage(plan, force=bool(options['force']))
                plan = execute_full_ingestion_copy_stage(plan, force=bool(options['force']))
            if options['execute_merge_stage']:
                if plan.stage == 'planned':
                    plan = execute_full_ingestion_partition_stage(plan, force=bool(options['force']))
                if plan.stage == 'partition':
                    plan = execute_full_ingestion_copy_stage(plan, force=bool(options['force']))
                plan = execute_full_ingestion_merge_stage(plan, force=bool(options['force']))
            if options['execute_pipeline']:
                plan = execute_full_ingestion_pipeline(plan, force=bool(options['force']))
        except ValueError as exc:
            release_full_ingestion_lease(
                provider=plan.provider,
                run_id=plan.run_id,
                status='failed',
                metadata={'manifest_path': plan.manifest_path, 'error': str(exc)},
            )
            raise CommandError(str(exc)) from exc
        except Exception:
            release_full_ingestion_lease(
                provider=plan.provider,
                run_id=plan.run_id,
                status='failed',
                metadata={'manifest_path': plan.manifest_path},
            )
            raise

        if plan.status in ('succeeded', 'failed'):
            release_full_ingestion_lease(
                provider=plan.provider,
                run_id=plan.run_id,
                status=plan.status,
                metadata={
                    'manifest_path': plan.manifest_path,
                    'stage': plan.stage,
                    'source_version': plan.source_version,
                },
            )
        else:
            touch_full_ingestion_lease(
                provider=plan.provider,
                run_id=plan.run_id,
                stage=plan.stage,
                metadata={
                    'manifest_path': plan.manifest_path,
                    'source_version': plan.source_version,
                },
            )
        return plan

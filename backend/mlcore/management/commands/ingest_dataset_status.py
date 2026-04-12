from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from mlcore.services.full_ingestion import (
    configured_full_ingestion_scratch_root,
    full_ingestion_manifest_path,
    full_ingestion_partition_state_counts,
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
            'partition_states': partition_states,
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
                'stage={stage} status={status} partitions={partitions} states={states} '
                'rows_parsed={rows_parsed} rows_staged={rows_staged} rows_merged={rows_merged} '
                'rows_deduplicated={rows_deduplicated} unresolved={rows_unresolved} malformed={rows_malformed} '
                'manifest={manifest}'
            ).format(
                provider=plan.provider,
                source_version=plan.source_version,
                run_id=plan.run_id,
                stage=plan.stage,
                status=plan.status,
                partitions=plan.partition_count,
                states=','.join(f'{state}:{count}' for state, count in sorted(partition_states.items())),
                rows_parsed=int(plan.counters.get('rows_parsed') or 0),
                rows_staged=int(plan.counters.get('rows_staged') or 0),
                rows_merged=int(plan.counters.get('rows_merged') or 0),
                rows_deduplicated=int(plan.counters.get('rows_deduplicated') or 0),
                rows_unresolved=int(plan.counters.get('rows_unresolved') or 0),
                rows_malformed=int(plan.counters.get('rows_malformed') or 0),
                manifest=plan.manifest_path,
            )
        )

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from mlcore.services.full_ingestion import (
    FULL_INGESTION_POLICY_CHOICES,
    configured_full_ingestion_scratch_root,
    full_ingestion_manifest_path,
    get_full_ingestion_provider,
    load_full_ingestion_plan,
    sync_full_ingestion_runtime_control,
    write_full_ingestion_control,
    write_full_ingestion_metrics,
    write_full_ingestion_plan,
)


class Command(BaseCommand):
    help = 'Inspect or update runtime control for one provider full-ingestion run.'

    def add_arguments(self, parser):
        parser.add_argument('--provider', required=True, help='Dataset provider name, for example listenbrainz.')
        parser.add_argument('--archive-path', default='', help='Optional archive path used to infer source version.')
        parser.add_argument('--source-version', default='', help='Explicit source-version label. Required when archive-path is omitted.')
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
        parser.add_argument('--policy', choices=FULL_INGESTION_POLICY_CHOICES, help='Set runtime policy mode.')
        parser.add_argument('--partition-budget', type=int, help='Override current partition worker budget.')
        parser.add_argument('--load-budget', type=int, help='Override current load worker budget.')
        parser.add_argument('--merge-budget', type=int, help='Override current merge worker budget.')
        parser.add_argument('--scratch-soft-cap-gb', type=int, help='Override scratch soft cap in GiB.')
        parser.add_argument('--json', action='store_true', help='Emit JSON instead of compact text.')

    def handle(self, *args, **options):
        provider = get_full_ingestion_provider(str(options['provider'] or '').strip())
        manifest_path = str(options['manifest_path'] or '').strip()
        source_version = str(options['source_version'] or '').strip()
        archive_path = str(options['archive_path'] or '').strip()

        if not manifest_path:
            if not source_version:
                configured_archive_path = archive_path or provider.configured_archive_path() or ''
                if not configured_archive_path:
                    raise CommandError('source-version or archive-path is required when manifest-path is not provided.')
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

        if any(
            options.get(key) is not None
            for key in ('policy', 'partition_budget', 'load_budget', 'merge_budget', 'scratch_soft_cap_gb')
        ):
            scratch_soft_cap_bytes = (
                int(options['scratch_soft_cap_gb']) * 1024**3
                if options.get('scratch_soft_cap_gb') is not None
                else None
            )
            write_full_ingestion_control(
                plan,
                policy_mode=options.get('policy'),
                partition_worker_budget=options.get('partition_budget'),
                load_worker_budget=options.get('load_budget'),
                merge_worker_budget=options.get('merge_budget'),
                scratch_soft_cap_bytes=scratch_soft_cap_bytes,
            )
            plan = sync_full_ingestion_runtime_control(plan)
            write_full_ingestion_plan(plan)
            write_full_ingestion_metrics(plan)

        payload = {
            'provider': plan.provider,
            'source_version': plan.source_version,
            'run_id': plan.run_id,
            'stage': plan.stage,
            'status': plan.status,
            'policy_mode': plan.policy_mode,
            'partition_worker_budget': plan.partition_worker_budget,
            'load_worker_budget': plan.load_worker_budget,
            'merge_worker_budget': plan.merge_worker_budget,
            'scratch_soft_cap_bytes': plan.scratch_soft_cap_bytes,
            'manifest_path': plan.manifest_path,
            'control_path': plan.control_path,
        }

        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self.stdout.write(
            (
                'provider={provider} source_version={source_version} run_id={run_id} stage={stage} status={status} '
                'policy={policy_mode} budgets=partition:{partition_worker_budget},load:{load_worker_budget},merge:{merge_worker_budget} '
                'scratch_soft_cap_bytes={scratch_soft_cap_bytes} control={control_path}'
            ).format(**payload)
        )

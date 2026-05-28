from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count

from mlcore.models import CanonicalItem, ListenBrainzSessionTrack, SourceIngestionRun
from mlcore.services.cooccurrence import compute_pmi_table
from mlcore.services.evaluation import build_loo_dataset
from mlcore.services.full_ingestion import (
    configured_full_ingestion_scratch_root,
    full_ingestion_manifest_path,
    get_full_ingestion_provider,
    load_full_ingestion_plan,
)


class Command(BaseCommand):
    help = (
        'Run a lightweight post-ingestion readiness check against the canonical-item '
        'ListenBrainz hot dataset.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--provider',
            default='listenbrainz',
            help='Dataset provider to verify. Currently only listenbrainz is supported.',
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
            help='Scratch root where the full-ingestion manifest lives.',
        )
        parser.add_argument(
            '--manifest-path',
            default='',
            help='Optional explicit manifest path. Overrides provider/source-version lookup.',
        )
        parser.add_argument(
            '--sample-sessions',
            type=int,
            default=128,
            help='How many eligible hot sessions to sample for the training preview.',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Emit the verification summary as JSON.',
        )

    def handle(self, *args, **options):
        provider = str(options['provider'] or '').strip().casefold()
        ingestion_provider = get_full_ingestion_provider(provider)
        if ingestion_provider.provider != 'listenbrainz':
            raise CommandError('Only --provider listenbrainz is currently supported.')

        sample_sessions = int(options['sample_sessions'] or 0)
        if sample_sessions <= 0:
            raise CommandError('--sample-sessions must be > 0')

        manifest_path = str(options['manifest_path'] or '').strip()
        source_version = str(options['source_version'] or '').strip()
        archive_path = str(options['archive_path'] or '').strip()
        if not manifest_path:
            if not source_version:
                configured_archive_path = archive_path or ingestion_provider.configured_archive_path() or ''
                if configured_archive_path:
                    source_version = ingestion_provider.infer_source_version(configured_archive_path)
                else:
                    candidate_runs = list(
                        SourceIngestionRun.objects
                        .filter(source=provider, status='succeeded', metadata__stage='completed')
                        .order_by('-completed_at', '-started_at')[:25]
                    )
                    latest_run = None
                    latest_manifest_mtime = -1.0
                    for candidate_run in candidate_runs:
                        candidate_manifest_path = str(candidate_run.metadata.get('manifest_path') or '').strip()
                        if not candidate_manifest_path:
                            continue
                        try:
                            candidate_manifest_mtime = Path(candidate_manifest_path).stat().st_mtime
                        except OSError:
                            continue
                        if latest_run is None or candidate_manifest_mtime > latest_manifest_mtime:
                            latest_run = candidate_run
                            latest_manifest_mtime = candidate_manifest_mtime
                    if latest_run is None and candidate_runs:
                        latest_run = candidate_runs[0]
                    if latest_run is None:
                        raise CommandError(
                            'source-version or archive-path is required when manifest-path is not provided '
                            'and no completed full ingestion run can be discovered.'
                        )
                    source_version = latest_run.source_version
                    manifest_path = str(latest_run.metadata.get('manifest_path') or '').strip()
            manifest_path = str(
                manifest_path
                or full_ingestion_manifest_path(
                    provider=provider,
                    source_version=source_version,
                    scratch_root=str(options['scratch_root'] or '').strip() or None,
                )
            )

        try:
            plan = load_full_ingestion_plan(manifest_path)
        except FileNotFoundError as exc:
            raise CommandError(f'No full-ingestion manifest found at {manifest_path}.') from exc

        if plan.status != 'succeeded' or plan.stage != 'complete':
            raise CommandError(
                f'Full-ingestion manifest at {manifest_path} is not complete yet '
                f'(stage={plan.stage} status={plan.status}).'
            )

        required_tables = {
            'mlcore_canonical_item',
            'mlcore_listenbrainz_session_track',
        }
        available_tables = set(connection.introspection.table_names())
        missing_tables = sorted(required_tables - available_tables)
        if missing_tables:
            raise CommandError(
                'The finished ListenBrainz training tables are not present in the configured database: '
                + ', '.join(missing_tables)
            )

        eligible_session_keys = list(
            ListenBrainzSessionTrack.objects
            .filter(canonical_item__isnull=False)
            .values('session_key')
            .annotate(item_count=Count('canonical_item_id', distinct=True))
            .filter(item_count__gte=2)
            .order_by('session_key')
            .values_list('session_key', flat=True)[:sample_sessions]
        )

        session_to_items: dict[bytes, set] = defaultdict(set)
        if eligible_session_keys:
            for session_key, canonical_item_id in (
                ListenBrainzSessionTrack.objects
                .filter(session_key__in=eligible_session_keys, canonical_item__isnull=False)
                .values_list('session_key', 'canonical_item_id')
            ):
                normalized_session_key = (
                    session_key.tobytes() if isinstance(session_key, memoryview) else bytes(session_key)
                )
                session_to_items[normalized_session_key].add(canonical_item_id)

        baskets = [
            sorted(items, key=str)
            for _, items in sorted(session_to_items.items(), key=lambda item: item[0])
            if len(items) >= 2
        ]
        pair_table, training_preview = compute_pmi_table(baskets)
        loo_dataset = build_loo_dataset(baskets=baskets)

        payload = {
            'provider': provider,
            'source_version': plan.source_version,
            'full_ingestion_run_id': plan.run_id,
            'manifest_path': plan.manifest_path,
            'imported_row_count': int(plan.counters.get('rows_merged') or 0),
            'canonicalized_row_count': int(plan.counters.get('rows_resolved') or 0),
            'unresolved_row_count': int(plan.counters.get('rows_unresolved') or 0),
            'canonical_item_count': CanonicalItem.objects.count(),
            'sample_sessions_requested': sample_sessions,
            'sample_sessions_loaded': len(baskets),
            'sample_pairs': len(pair_table),
            'sample_trials': len(loo_dataset.trials),
            'sample_dataset_hash': loo_dataset.dataset_hash,
            'sample_baskets_processed': training_preview.baskets_processed,
            'ready': bool(
                int(plan.counters.get('rows_merged') or 0) > 0
                and int(plan.counters.get('rows_resolved') or 0) > 0
                and len(baskets) > 0
                and len(pair_table) > 0
                and len(loo_dataset.trials) > 0
            ),
        }

        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self.stdout.write(
            (
                'provider={provider} source_version={source_version} run_id={run_id} '
                'imported_rows={imported_rows} canonicalized_rows={canonicalized_rows} '
                'unresolved_rows={unresolved_rows} canonical_items={canonical_items} '
                'sample_sessions={sample_sessions_loaded}/{sample_sessions_requested} '
                'sample_pairs={sample_pairs} sample_trials={sample_trials} '
                'dataset_hash={dataset_hash} ready={ready}'
            ).format(
                provider=payload['provider'],
                source_version=payload['source_version'],
                run_id=payload['full_ingestion_run_id'],
                imported_rows=payload['imported_row_count'],
                canonicalized_rows=payload['canonicalized_row_count'],
                unresolved_rows=payload['unresolved_row_count'],
                canonical_items=payload['canonical_item_count'],
                sample_sessions_loaded=payload['sample_sessions_loaded'],
                sample_sessions_requested=payload['sample_sessions_requested'],
                sample_pairs=payload['sample_pairs'],
                sample_trials=payload['sample_trials'],
                dataset_hash=payload['sample_dataset_hash'][:12],
                ready=str(payload['ready']).lower(),
            )
        )

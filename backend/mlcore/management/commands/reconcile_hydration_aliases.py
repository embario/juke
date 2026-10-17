import json

from django.core.management.base import BaseCommand

from mlcore.services.hydration_reconcile import DEFAULT_BATCH_SIZE, reconcile_hydration_with_spotify_aliases


class Command(BaseCommand):
    help = (
        'Mark pending Spotify hydration items matched (resolved_by=final_target_spotify_alias) when the '
        'item they belong to, after redirects, already has a Spotify alias. Set-based, idempotent; '
        'running/leased/locked items are skipped. Makes no Spotify API request.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Stage and count; write nothing.')
        parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE, help='Queue rows per transaction.')
        parser.add_argument('--after-id', type=int, default=0, help='Only consider queue rows with id above this (resume).')
        parser.add_argument('--limit', type=int, help='Stage at most this many pending rows (bounded validation run).')
        parser.add_argument('--staging-tablespace', help='temp_tablespaces for the staging tables, e.g. the NVMe one.')
        parser.add_argument('--json', action='store_true', help='Emit machine-readable final output.')

    def handle(self, *args, **options):
        def report(progress):
            event = progress['event']
            if event == 'reconcile_batch':
                eta = progress.get('eta_seconds')
                self.stderr.write(
                    'event=reconcile_batch processed={processed}/{resolvable} matched={matched} '
                    'last_item_id={last_item_id} rows_per_second={rows_per_second:.0f} eta_seconds={eta}'.format(
                        eta='unknown' if eta is None else f'{eta:.0f}', **progress,
                    )
                )
            elif event == 'reconcile_hop':
                self.stderr.write(f'event=reconcile_hop {progress["message"]}')
            else:
                self.stderr.write('event={event} '.format(**progress) + ' '.join(
                    f'{key}={value}' for key, value in progress.items() if key != 'event'
                ))

        result = reconcile_hydration_with_spotify_aliases(
            batch_size=options['batch_size'],
            after_id=options['after_id'],
            limit=options.get('limit'),
            dry_run=options['dry_run'],
            staging_tablespace=options.get('staging_tablespace'),
            progress_callback=report,
        )
        payload = result.__dict__
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))

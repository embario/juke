import time

from django.core.management.base import BaseCommand, CommandError

from mlcore.services.provider_hydration import rescore_pending_priorities


class Command(BaseCommand):
    help = (
        'Backfill popularity priorities on pending Spotify hydration items in bounded batches. '
        'Safe beside the worker: it only updates priority on pending/retry rows, never the whole table.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=400)
        parser.add_argument('--after-id', type=int, default=0)
        parser.add_argument('--max-batches', type=int, help='Stop after this many batches (default: one full pass).')
        parser.add_argument('--sleep-seconds', type=float, default=1.0, help='Pause between batches.')

    def handle(self, *args, **options):
        for option in ('batch_size', 'max_batches'):
            if options[option] is not None and options[option] < 1:
                raise CommandError(f'--{option.replace("_", "-")} must be greater than zero.')
        if options['sleep_seconds'] < 0:
            raise CommandError('--sleep-seconds cannot be negative.')
        cursor = options['after_id']
        scanned = updated = batches = 0
        while True:
            result = rescore_pending_priorities(after_id=cursor, batch_size=options['batch_size'])
            batches += 1
            scanned += result.scanned
            updated += result.updated
            cursor = result.next_cursor
            self.stdout.write(
                f'batch={batches} scanned={scanned} updated={updated} next_cursor={cursor} '
                f'pass_complete={result.pass_complete}'
            )
            if result.pass_complete or (options['max_batches'] and batches >= options['max_batches']):
                break
            if options['sleep_seconds']:
                time.sleep(options['sleep_seconds'])

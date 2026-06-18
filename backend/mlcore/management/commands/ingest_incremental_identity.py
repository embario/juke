import json

from django.core.management.base import BaseCommand

from mlcore.services.incremental_identity import run_incremental_identity_ingestion


class Command(BaseCommand):
    help = 'Run incremental MLCore identity ingestion from provider deltas.'

    def add_arguments(self, parser):
        parser.add_argument('--max-incrementals', type=int, default=14)
        parser.add_argument(
            '--no-existing-unprocessed',
            action='store_true',
            help='Only process versions discovered in this sync run.',
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        def report(progress):
            event = progress.get('event')
            if event == 'incremental_identity_sync_complete':
                self.stderr.write(
                    'event=incremental_identity_sync_complete '
                    'sync_status={sync_status} candidates={candidate_count}'.format(
                        sync_status=progress['sync_status'],
                        candidate_count=len(progress['candidate_versions']),
                    )
                )
            elif event == 'incremental_identity_version_complete':
                self.stderr.write(
                    'event=incremental_identity_version_complete '
                    'source_version={source_version} redirects={redirect_count} conflicts={conflict_msid_count}'.format(
                        **progress
                    )
                )

        result = run_incremental_identity_ingestion(
            max_incrementals=options['max_incrementals'],
            include_existing_unprocessed=not options['no_existing_unprocessed'],
            dry_run=options['dry_run'],
            progress_callback=report,
        )
        payload = {
            **result.__dict__,
            'processed_versions': [
                processed.__dict__
                for processed in result.processed_versions
            ],
        }
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        self.stdout.write(
            'run_id={run_id} status={status} processed={processed} elapsed_seconds={elapsed:.1f}'.format(
                run_id=result.run_id,
                status=result.status,
                processed=len(result.processed_versions),
                elapsed=result.elapsed_seconds,
            )
        )

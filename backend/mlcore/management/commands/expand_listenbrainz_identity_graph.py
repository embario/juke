import json

from django.core.management.base import BaseCommand, CommandError

from mlcore.models import SourceIngestionRun
from mlcore.services.listenbrainz_identity_bridge import expand_listenbrainz_identity_graph


class Command(BaseCommand):
    help = 'Create missing canonical MSID items for clean ListenBrainz MSID-to-MBID mappings.'

    def add_arguments(self, parser):
        parser.add_argument('--source-version', help='ListenBrainz source version to expand.')
        parser.add_argument('--batch-size', type=int, default=100_000, help='Canonical items to insert per batch.')
        parser.add_argument('--dry-run', action='store_true', help='Count work without inserting rows.')
        parser.add_argument('--json', action='store_true', help='Emit machine-readable final output.')

    def handle(self, *args, **options):
        source_version = options.get('source_version') or self._latest_source_version()

        def report(progress):
            if progress.get('event') == 'msid_canonical_batch':
                self.stderr.write(
                    'event=msid_canonical_batch created={created_msid_count}/{missing_msid_count} '
                    'batch_size={batch_size}'.format(**progress)
                )

        result = expand_listenbrainz_identity_graph(
            source_version,
            batch_size=options['batch_size'],
            dry_run=options['dry_run'],
            progress_callback=report,
        )
        payload = result.__dict__
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))

    def _latest_source_version(self) -> str:
        run = SourceIngestionRun.objects.filter(
            source='listenbrainz-identity-bridge',
            status='succeeded',
        ).order_by('-completed_at', '-started_at').first()
        if run is None:
            raise CommandError('No succeeded ListenBrainz identity bridge run found.')
        return run.source_version

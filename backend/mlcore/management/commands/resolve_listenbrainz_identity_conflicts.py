import json

from django.core.management.base import BaseCommand, CommandError

from mlcore.models import SourceIngestionRun
from mlcore.services.listenbrainz_identity_bridge import (
    CONFLICT_RESOLVER_POLICY_VERSION,
    resolve_listenbrainz_identity_conflicts,
)


class Command(BaseCommand):
    help = 'Auto-resolve dominant ListenBrainz MSID-to-MBID conflicts into canonical redirects.'

    def add_arguments(self, parser):
        parser.add_argument('--source-version', help='ListenBrainz source version to resolve.')
        parser.add_argument('--policy-version', default=CONFLICT_RESOLVER_POLICY_VERSION)
        parser.add_argument('--min-winner-share', type=float, default=0.95)
        parser.add_argument('--min-winner-shards', type=int, default=2)
        parser.add_argument('--batch-size', type=int, default=100_000)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        source_version = options.get('source_version') or self._latest_source_version()

        def report(progress):
            if progress.get('event') == 'conflict_msid_canonical_batch':
                self.stderr.write(
                    'event=conflict_msid_canonical_batch created={created_msid_count} '
                    'batch_size={batch_size} policy={policy_version}'.format(**progress)
                )

        result = resolve_listenbrainz_identity_conflicts(
            source_version,
            policy_version=options['policy_version'],
            min_winner_share=options['min_winner_share'],
            min_winner_shards=options['min_winner_shards'],
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

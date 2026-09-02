import json

from django.core.management.base import BaseCommand, CommandError

from mlcore.models import SourceIngestionRun
from mlcore.services.listenbrainz_identity_bridge import materialize_listenbrainz_isrc_aliases


class Command(BaseCommand):
    help = 'Promote schema-v2 ListenBrainz MSID-to-ISRC evidence into canonical aliases.'

    def add_arguments(self, parser):
        parser.add_argument('--source-version', help='ListenBrainz identity source version; defaults to latest v2 run.')
        parser.add_argument('--json', action='store_true', help='Emit machine-readable output.')

    def handle(self, *args, **options):
        source_version = options.get('source_version') or self._latest_source_version()
        result = materialize_listenbrainz_isrc_aliases(source_version)
        payload = result.__dict__
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))

    @staticmethod
    def _latest_source_version():
        run = (
            SourceIngestionRun.objects.filter(
                source='listenbrainz-identity-bridge',
                status='succeeded',
                metadata__extraction_schema_version__gte=2,
            )
            .order_by('-completed_at', '-started_at')
            .first()
        )
        if run is None:
            raise CommandError('No succeeded schema-v2 ListenBrainz identity bridge run found.')
        return run.source_version

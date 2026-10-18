import json
from django.core.management.base import BaseCommand
from mlcore.services.musicbrainz_metadata import import_recording_metadata


class Command(BaseCommand):
    help = 'Backfill source-versioned recording metadata from a local dump, without replaying identity evidence.'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', required=True)

    def handle(self, *args, **options):
        result = import_recording_metadata(options['manifest'], progress=lambda p: self.stderr.write(json.dumps(p)))
        self.stdout.write(json.dumps(result))

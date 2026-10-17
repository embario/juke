import json
from pathlib import Path

from django.core.management.base import BaseCommand

from mlcore.services.musicbrainz_url_aliases import (
    build_workspace,
    latest_musicbrainz_url_source_version,
    precision_report,
)


class Command(BaseCommand):
    help = (
        'Read-only precision check: compare MusicBrainz Spotify track links with existing API-hydrated '
        'Spotify aliases of the same canonical item (same / different / different-but-same-ISRC).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--source-version', help='MusicBrainz bridge source version; defaults to latest.')
        parser.add_argument('--mbid-prefix', default='', help='Hex MBID prefix to run on a slice (e.g. 0a ~ 1/256).')
        parser.add_argument('--examples', type=int, default=25, help='Disagreeing examples to include.')
        parser.add_argument('--out', help='Write the JSON report here; --write on materialize_musicbrainz_url_aliases requires it.')
        parser.add_argument('--explain', action='store_true', help='Print EXPLAIN of the main statements.')

    def handle(self, *args, **options):
        source_version = options.get('source_version') or latest_musicbrainz_url_source_version()
        stats = build_workspace(
            source_version,
            mbid_prefix=options['mbid_prefix'],
            explain=options['explain'],
            progress=lambda message: self.stderr.write(message),
        )
        report = precision_report(explain=options['explain'], example_limit=options['examples'])
        payload = {
            'source_version': source_version,
            'mbid_prefix': options['mbid_prefix'],
            **{key: value for key, value in report.items() if key != 'explains'},
            'workspace': stats.as_dict(),
        }
        if options['explain']:
            for name, lines in {**stats.explains, **report['explains']}.items():
                self.stderr.write(f'--- EXPLAIN {name}')
                for line in lines:
                    self.stderr.write(line)
        if options.get('out'):
            Path(options['out']).write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))

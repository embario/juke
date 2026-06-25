import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from mlcore.services.musicbrainz_bridge import import_musicbrainz_bridge
from mlcore.services.musicbrainz_source import configured_download_dir


class Command(BaseCommand):
    help = 'Import MusicBrainz recording MBID-to-ISRC and direct URL evidence into cold bridge tables.'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', help='Path to a staged MusicBrainz manifest.json.')
        parser.add_argument('--json', action='store_true', help='Emit machine-readable JSON.')

    def handle(self, *args, **options):
        manifest_path = Path(options['manifest']) if options.get('manifest') else self._latest_manifest()

        def report(progress):
            self.stderr.write(
                'member={member} recordings={recording_rows} isrc_rows={isrc_rows} '
                'valid_isrc_rows={valid_isrc_rows} malformed_isrc_rows={malformed_isrc_rows} '
                'url_relationship_rows={url_relationship_rows}'.format(**progress)
            )

        result = import_musicbrainz_bridge(manifest_path, progress_callback=report)
        payload = result.__dict__
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))

    def _latest_manifest(self) -> Path:
        releases_dir = configured_download_dir() / 'releases'
        manifests = sorted(releases_dir.glob('*/manifest.json'), reverse=True)
        if not manifests:
            raise CommandError(f'No staged MusicBrainz manifest found under {releases_dir}')
        return manifests[0]

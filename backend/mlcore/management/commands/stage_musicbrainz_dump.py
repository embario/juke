import json

from django.core.management.base import BaseCommand

from mlcore.services.musicbrainz_source import (
    configured_minimum_free_bytes,
    discover_musicbrainz_release,
    stage_musicbrainz_dump,
)


class Command(BaseCommand):
    help = 'Discover, verify, and stage the official MusicBrainz core dump in cold storage.'

    def add_arguments(self, parser):
        parser.add_argument('--source-version', help='Pin a release such as 20260613-002047; defaults to LATEST.')
        parser.add_argument('--download-dir', help='Override the configured MusicBrainz cold-storage root.')
        parser.add_argument(
            '--minimum-free-gib',
            type=float,
            default=configured_minimum_free_bytes() / 1024**3,
            help='Required free cold-storage capacity before a download starts.',
        )
        parser.add_argument('--plan', action='store_true', help='Print the release/capacity plan without downloading.')
        parser.add_argument('--force', action='store_true', help='Redownload an already verified release.')
        parser.add_argument('--json', action='store_true', help='Emit machine-readable JSON.')

    def handle(self, *args, **options):
        minimum_free_bytes = int(options['minimum_free_gib'] * 1024**3)
        common = {
            'source_version': options.get('source_version'),
            'download_dir': options.get('download_dir'),
            'minimum_free_bytes': minimum_free_bytes,
        }
        if options['plan']:
            payload = discover_musicbrainz_release(**common)
        else:
            last_reported_bytes = 0

            def report_progress(progress):
                nonlocal last_reported_bytes
                downloaded_bytes = progress['downloaded_bytes']
                expected_bytes = progress['expected_bytes']
                if downloaded_bytes - last_reported_bytes < 512 * 1024**2 and downloaded_bytes != expected_bytes:
                    return
                last_reported_bytes = downloaded_bytes
                percent = (downloaded_bytes / expected_bytes * 100) if expected_bytes else 0
                self.stderr.write(
                    f'downloaded_bytes={downloaded_bytes} expected_bytes={expected_bytes} percent={percent:.1f}'
                )

            payload = stage_musicbrainz_dump(
                force=options['force'],
                progress_callback=report_progress,
                **common,
            )

        data = payload.__dict__
        if hasattr(payload, 'artifact'):
            data = {**data, 'artifact': payload.artifact.__dict__}
        if options['json']:
            self.stdout.write(json.dumps(data, indent=2, sort_keys=True))
            return

        if options['plan']:
            self.stdout.write(
                'source_version={source_version} artifact={artifact} compressed_bytes={compressed_bytes} '
                'estimated_expanded_bytes={estimated_expanded_bytes} minimum_free_bytes={minimum_free_bytes} '
                'available_bytes={available_bytes} release_dir={release_dir}'.format(
                    source_version=payload.source_version,
                    artifact=payload.artifact.name,
                    compressed_bytes=payload.artifact.compressed_bytes,
                    estimated_expanded_bytes=payload.estimated_expanded_bytes,
                    minimum_free_bytes=payload.minimum_free_bytes,
                    available_bytes=payload.available_bytes,
                    release_dir=payload.release_dir,
                )
            )
            return

        self.stdout.write(
            'status={status} source_version={source_version} artifact={artifact_path} '
            'manifest={manifest_path} downloaded={downloaded} run_id={run_id}'.format(**data)
        )

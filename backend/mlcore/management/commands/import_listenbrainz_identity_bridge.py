import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from mlcore.services.listenbrainz_identity_bridge import import_listenbrainz_identity_bridge
from mlcore.services.listenbrainz_shards import configured_listenbrainz_shard_root


class Command(BaseCommand):
    help = 'Extract exact MSID-to-MBID evidence from cold ListenBrainz shards and materialize canonical redirects.'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', help='Path to a materialized ListenBrainz shard manifest.')
        parser.add_argument('--output-root', help='Cold output root for per-shard pair files.')
        parser.add_argument('--max-shards', type=int, help='Limit processing for a bounded validation run.')
        parser.add_argument('--force', action='store_true', help='Replace this source version and re-extract every shard.')
        parser.add_argument('--json', action='store_true', help='Emit machine-readable final output.')

    def handle(self, *args, **options):
        manifest_path = Path(options['manifest']) if options.get('manifest') else self._latest_manifest()

        def report(progress):
            event = progress.get('event')
            if event == 'extract_progress':
                self.stderr.write(
                    'event=extract_progress shard={shard_key} rows={source_row_count} mapped={mapped_row_count} '
                    'malformed={malformed_row_count}'.format(**progress)
                )
            elif event == 'shard_complete':
                eta = progress.get('eta_seconds')
                self.stderr.write(
                    'event=shard_complete shard={current_shard} completed={completed_shards}/{shard_count} '
                    'rows={source_row_count} mapped={mapped_row_count} unique_pairs={unique_pair_count} '
                    'throughput_bps={throughput_bytes_per_second:.0f} eta_seconds={eta}'.format(
                        eta='unknown' if eta is None else f'{eta:.0f}',
                        **progress,
                    )
                )

        result = import_listenbrainz_identity_bridge(
            manifest_path,
            output_root=options.get('output_root'),
            max_shards=options.get('max_shards'),
            force=options['force'],
            progress_callback=report,
        )
        payload = result.__dict__
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))

    def _latest_manifest(self) -> Path:
        manifests = sorted(configured_listenbrainz_shard_root().glob('*/manifest.json'), reverse=True)
        if not manifests:
            raise CommandError(f'No ListenBrainz shard manifests found under {configured_listenbrainz_shard_root()}')
        return manifests[0]

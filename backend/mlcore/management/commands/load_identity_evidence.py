import json

from django.core.management.base import BaseCommand, CommandError

from mlcore.models import ListenBrainzIdentityShard
from mlcore.services.identity_evidence import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_GROUP_SIZE,
    SCHEME_FILES,
    load_listenbrainz_identity_evidence,
)


class Command(BaseCommand):
    help = (
        'Load ListenBrainz schema-v3 shard files (msid-spotify, msid-isrc, msid-mbid) into the cold '
        'mlcore_identity_evidence table. Set-based and resumable: rerun the same command to resume.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--source-version', help='Shard source version (default: the newest with succeeded v3 shards).')
        parser.add_argument('--scheme', action='append', choices=sorted(SCHEME_FILES), help='Repeatable; default all.')
        parser.add_argument('--output-root', help='Relocated evidence root (files at <root>/<source-version>/<shard>...).')
        parser.add_argument('--staging-tablespace', help='Tablespace for the unlogged staging tables, e.g. the NVMe one.')
        parser.add_argument('--work-mem', help='work_mem for the staging aggregate, e.g. 2GB (sort spills go to the staging tablespace).')
        parser.add_argument('--group-size', type=int, default=DEFAULT_GROUP_SIZE, help='Shard files aggregated per group.')
        parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE, help='Evidence rows per transaction.')
        parser.add_argument('--max-groups', type=int, help='Stop after this many groups (bounded validation run).')
        parser.add_argument('--json', action='store_true', help='Emit machine-readable final output.')

    def handle(self, *args, **options):
        source_version = options.get('source_version') or self._latest_source_version()

        def report(progress):
            if progress['event'] == 'evidence_batch':
                eta = progress.get('eta_seconds')
                self.stderr.write(
                    'event=evidence_batch scheme={scheme} first_shard={group_first_shard} '
                    'applied={applied_rows}/{stage_rows} rows_per_second={rows_per_second:.0f} eta_seconds={eta}'.format(
                        eta='unknown' if eta is None else f'{eta:.0f}', **progress,
                    )
                )
            elif progress['event'] == 'evidence_group_complete':
                self.stderr.write(
                    'event=evidence_group_complete scheme={scheme} shards={shards} raw_rows={raw_rows} '
                    'evidence_rows={evidence_rows} elapsed_seconds={elapsed_seconds:.0f}'.format(**progress)
                )

        result = load_listenbrainz_identity_evidence(
            source_version,
            schemes=options.get('scheme'),
            output_root=options.get('output_root'),
            staging_tablespace=options.get('staging_tablespace'),
            group_size=options['group_size'],
            batch_size=options['batch_size'],
            max_groups=options.get('max_groups'),
            work_mem=options.get('work_mem'),
            progress_callback=report,
        )
        payload = result.__dict__
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))

    def _latest_source_version(self) -> str:
        shard = ListenBrainzIdentityShard.objects.filter(status='succeeded').order_by('-source_version').first()
        if shard is None:
            raise CommandError('No succeeded ListenBrainz identity shards found; run import_listenbrainz_identity_bridge first.')
        return shard.source_version

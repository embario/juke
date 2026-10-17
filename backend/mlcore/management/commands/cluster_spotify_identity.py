import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from mlcore.services.spotify_clusters import (
    ALGORITHM, apply_workspace, build_workspace, export_audit, export_review,
)


class Command(BaseCommand):
    help = 'Cluster dominant Spotify evidence (dry-run default). Freeze evidence/bridge imports for replay.'

    def add_arguments(self, parser):
        parser.add_argument('--musicbrainz-version', required=True)
        parser.add_argument('--source-version', required=True, help='Operator run/evidence snapshot identifier.')
        parser.add_argument('--sample-percent', type=float, default=1, help='Stable hash of whole Spotify groups; default 1.')
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument('--write', action='store_true')
        mode.add_argument('--dry-run', action='store_true', help='Default; no persistent graph writes.')
        parser.add_argument('--owner-approved-full-run', action='store_true',
                            help='Operator attests owner approved after auditing ~200 sample merges.')
        parser.add_argument('--audit-export', required=True, help='JSONL sample of proposed merges with local metadata.')
        parser.add_argument('--audit-metadata', help='Offline JSONL metadata supplement keyed by canonical_key.')
        parser.add_argument('--audit-limit', type=int, default=200)
        parser.add_argument('--review-export', required=True, help='JSONL conflicts/oversize groups.')
        parser.add_argument('--explain-export', help='JSON EXPLAIN plans of main staging statements.')
        parser.add_argument('--resume-state', help='JSON checkpoint; rerun the identical command to resume.')
        parser.add_argument('--batch-size', type=int, default=50_000, help='10000..100000 action rows per transaction.')
        parser.add_argument('--max-batches', type=int, help='Bounded operator validation; rerun without it to finish.')
        parser.add_argument('--staging-tablespace', help='NVMe temp/sort tablespace.')

    def handle(self, *args, **o):
        if not 0 < o['sample_percent'] <= 100 or not 10_000 <= o['batch_size'] <= 100_000:
            raise CommandError('sample-percent must be >0..100; batch-size must be 10000..100000')
        if o['audit_limit'] < 1 or (o['max_batches'] is not None and o['max_batches'] < 1):
            raise CommandError('audit-limit and max-batches must be positive')
        if o['write'] and o['sample_percent'] > 1 and not o['owner_approved_full_run']:
            raise CommandError('More than 1% requires --owner-approved-full-run after the owner audits ~200 merges')
        state_path = Path(o['resume_state']) if o['resume_state'] else None
        identity = dict(algorithm=ALGORITHM, source_version=o['source_version'],
                        musicbrainz_version=o['musicbrainz_version'], sample_percent=o['sample_percent'])
        after = ''
        if state_path and state_path.exists():
            state = json.loads(state_path.read_text())
            if state['identity'] != identity:
                raise CommandError('Resume parameters differ from the saved run; use the original parameters')
            after = state['after_key']

        def checkpoint(key):
            if state_path:
                temp = state_path.with_suffix(state_path.suffix + '.tmp')
                temp.write_text(json.dumps(dict(identity=identity, after_key=key), sort_keys=True))
                temp.replace(state_path)

        def progress(message):
            self.stderr.write(message)

        plans = {} if o['explain_export'] else None
        # Session-wide lock: temp workspace and external checkpoint belong to one B6 runner.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(hashtext('mlcore-spotify-cluster-v1'))")
            if not cursor.fetchone()[0]:
                raise CommandError('Another Spotify clustering runner is active')
        try:
            if o['staging_tablespace']:
                with connection.cursor() as cursor:
                    cursor.execute('SET temp_tablespaces = ' + connection.ops.quote_name(o['staging_tablespace']))
            counts = build_workspace(sample_percent=o['sample_percent'], musicbrainz_version=o['musicbrainz_version'],
                                     progress=progress, plans=plans)
            if after and Path(o['audit_export']).exists():
                progress('preserving original audit export on resume')
                audited = None
            else:
                audited = export_audit(o['audit_export'], limit=o['audit_limit'], metadata_path=o['audit_metadata'])
            export_review(o['review_export'])
            if plans is not None:
                Path(o['explain_export']).write_text(json.dumps(plans, indent=2))
            result = apply_workspace(write=o['write'], source_version=o['source_version'],
                                     batch_size=o['batch_size'], after_key=after, checkpoint=checkpoint,
                                     progress=progress, max_batches=o['max_batches'])
            self.stdout.write(json.dumps(dict(groups=counts, audit_rows=audited, **result), sort_keys=True))
        finally:
            with connection.cursor() as cursor:
                if o['staging_tablespace']:
                    cursor.execute('RESET temp_tablespaces')
                cursor.execute("SELECT pg_advisory_unlock(hashtext('mlcore-spotify-cluster-v1'))")

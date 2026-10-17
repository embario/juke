import json
import time
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from mlcore.models import CanonicalAliasMaterializationRun
from mlcore.services.isrc_redirect_bridge import (
    ALGORITHM_VERSION,
    AUDIT_SAMPLE_BASIS_POINTS,
    STATUS_NEW,
    apply_redirect_batch,
    build_workspace,
    collect_audit_rows,
    latest_musicbrainz_isrc_source_version,
    sample_basis_points,
    write_audit_export,
)


class Command(BaseCommand):
    help = (
        'Redirect MSIDs (or clusters) without an MBID to the MusicBrainz recording their ISRCs map to '
        'unambiguously. Dry-run unless --write; writes above 1%% also need --full-run-approved.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--source-version', help='MusicBrainz bridge source version; defaults to latest.')
        parser.add_argument('--sample-percent', type=float, help='Deterministic whole-root sample, e.g. 1 for the audit run.')
        parser.add_argument('--write', action='store_true', help='Write redirects (default is a dry run).')
        parser.add_argument(
            '--full-run-approved', action='store_true',
            help='Required for writes above 1%%: set only after the ~200-merge audit and owner approval.',
        )
        parser.add_argument('--batch-size', type=int, default=50_000, help='Redirects per transaction (10k-100k).')
        parser.add_argument('--max-batches', type=int, help='Stop after this many batches (resume later).')
        parser.add_argument('--resume-run-id', type=UUID)
        parser.add_argument('--export-audit-run-id', type=UUID, help='Export a saved run audit without staging or writes.')
        parser.add_argument('--audit-path', help='Write a CSV audit export of planned/written merges.')
        parser.add_argument('--audit-limit', type=int, default=200)
        parser.add_argument('--explain', action='store_true', help='Print EXPLAIN of the main statements.')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        if not 1 <= options['batch_size'] <= 100_000:
            raise CommandError('--batch-size must be between 1 and 100000')
        if not 1 <= options['audit_limit'] <= 200:
            raise CommandError('--audit-limit must be between 1 and 200')
        if options.get('export_audit_run_id'):
            if not options.get('audit_path') or options['write'] or options.get('resume_run_id'):
                raise CommandError('--export-audit-run-id requires --audit-path and excludes --write/--resume-run-id')
            saved = CanonicalAliasMaterializationRun.objects.get(pk=options['export_audit_run_id'])
            if saved.algorithm_version != ALGORITHM_VERSION or 'audit_rows' not in saved.checkpoints:
                raise CommandError('This run has no compatible saved audit.')
            count = write_audit_export(options['audit_path'], saved.checkpoints['audit_rows'])
            self.stdout.write(json.dumps({'run_id': str(saved.id), 'audit_rows': count}))
            return
        write = options['write']
        run = None
        checkpoint = {}
        sample_percent = options.get('sample_percent')
        if options.get('resume_run_id'):
            if not write:
                raise CommandError('--resume-run-id requires --write')
            run = CanonicalAliasMaterializationRun.objects.get(pk=options['resume_run_id'])
            if run.algorithm_version != ALGORITHM_VERSION:
                raise CommandError(f'Run {run.id} uses incompatible algorithm {run.algorithm_version}.')
            if run.status == 'succeeded':
                raise CommandError(f'Run {run.id} has already succeeded.')
            checkpoint = dict(run.checkpoints or {})
            stored = float(checkpoint.get('sample_percent', 100.0))
            if sample_percent is not None and sample_percent != stored:
                raise CommandError(f'Run {run.id} was started with --sample-percent {stored}; resume uses it.')
            sample_percent = stored
            source_version = run.source_version
        else:
            source_version = options.get('source_version') or latest_musicbrainz_isrc_source_version()
        sample_percent = 100.0 if sample_percent is None else sample_percent
        try:
            basis_points = sample_basis_points(sample_percent)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        sample_percent = basis_points / 100
        if write and basis_points > AUDIT_SAMPLE_BASIS_POINTS and not options['full_run_approved']:
            raise CommandError(
                'A write above 1% needs --full-run-approved: run --sample-percent 1 --write first, audit ~200 merges '
                'with --audit-path, and get owner approval.'
            )

        log = self.stderr.write
        workspace = build_workspace(
            source_version, sample_percent=sample_percent, explain_plans=options['explain'], progress=log,
        )
        for name, lines in workspace.explains.items():
            log(f'--- EXPLAIN {name}')
            for line in lines:
                log(line)
        total = workspace.root_status.get(STATUS_NEW, 0)

        audit_rows = checkpoint.get('audit_rows') if run else None
        if audit_rows is None:
            audit_rows = collect_audit_rows(limit=options['audit_limit'])

        if write and run is None:
            run = CanonicalAliasMaterializationRun.objects.create(
                source_version=source_version,
                algorithm_version=ALGORITHM_VERSION,
                status='running',
                current_phase='redirects',
                batch_size=options['batch_size'],
                total_items=total,
                checkpoints={'sample_percent': sample_percent, 'audit_rows': audit_rows},
            )
        elif run is not None:
            run.status = 'running'
            run.current_phase = 'redirects'
            run.last_error = ''
            run.completed_at = None
            run.save()

        total = int(run.total_items) if run else total
        last_root = checkpoint.get('last_root')
        processed = int(run.processed_items) if run else 0
        inserted = int(run.created_count) if run else 0
        repointed = int(checkpoint.get('repointed') or 0)
        batches = 0
        done_now = 0
        started = time.monotonic()
        paused = False
        try:
            while True:
                with transaction.atomic():
                    result = apply_redirect_batch(
                        source_version=source_version, last_root=last_root,
                        batch_size=options['batch_size'], write=write,
                    )
                    if result.processed == 0:
                        break
                    batches += 1
                    done_now += result.processed
                    processed += result.processed
                    inserted += result.inserted
                    repointed += result.repointed
                    last_root = result.last_key
                    if run is not None:
                        run.processed_items = processed
                        run.created_count = inserted
                        run.batches_processed += 1
                        run.checkpoints = {**run.checkpoints, 'last_root': last_root, 'repointed': repointed}
                        run.save()
                rate = done_now / max(time.monotonic() - started, 1e-9)
                log(
                    f'phase=redirects processed={processed}/{total} '
                    f'{"inserted" if write else "would_insert"}={inserted} '
                    f'{"repointed" if write else "would_repoint"}={repointed} '
                    f'rate={rate:.0f}/s eta={max(total - processed, 0) / rate if rate else 0:.0f}s last_root={last_root}'
                )
                if options.get('max_batches') and batches >= options['max_batches']:
                    paused = True
                    break
        except Exception as exc:
            if run is not None:
                run.refresh_from_db()
                run.status = 'failed'
                run.last_error = str(exc)
                run.save()
            raise

        if run is not None:
            run.status = 'pending' if paused else 'succeeded'
            run.current_phase = 'paused' if paused else 'complete'
            run.completed_at = None if paused else timezone.now()
            run.save()

        audited = None
        if options.get('audit_path'):
            audited = write_audit_export(options['audit_path'], audit_rows)

        payload = {
            'mode': 'write' if write else 'dry-run',
            'run_id': str(run.id) if run else None,
            'status': 'paused' if paused else 'complete',
            **workspace.as_dict(),
            'redirects_inserted' if write else 'redirects_would_insert': inserted,
            'inbound_repointed' if write else 'inbound_would_repoint': repointed,
            'audit_rows': audited,
        }
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))

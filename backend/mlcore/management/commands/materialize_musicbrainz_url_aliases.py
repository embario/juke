import json
import time
from pathlib import Path
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from mlcore.models import CanonicalAliasMaterializationRun
from mlcore.services.musicbrainz_url_aliases import (
    ALGORITHM_VERSION,
    STATUS_NEW,
    apply_alias_batch,
    apply_hydration_batch,
    build_workspace,
    collect_hydration_targets,
    latest_musicbrainz_url_source_version,
)


def load_precision_gate(path, *, source_version, min_precision, min_compared):
    """Refuse to write unless a precision report for this source version is good enough."""
    try:
        report = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CommandError(f'Cannot read precision report {path}: {exc}') from exc
    if report.get('source_version') != source_version:
        raise CommandError(
            f'Precision report is for {report.get("source_version")}, not {source_version}; rerun the check.'
        )
    compared = int(report.get('compared') or 0)
    precision = report.get('precision')
    if compared < min_compared or precision is None:
        raise CommandError(f'Precision report compared only {compared} recordings (need {min_compared}).')
    if float(precision) < min_precision:
        raise CommandError(f'Precision {float(precision):.4f} is below the required {min_precision:.4f}.')
    return report


class Command(BaseCommand):
    help = (
        'Turn MusicBrainz Spotify track links into canonical Spotify aliases (match_source=musicbrainz_url) '
        'and mark the matching pending hydration items matched. Dry-run unless --write.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--source-version', help='MusicBrainz bridge source version; defaults to latest.')
        parser.add_argument('--write', action='store_true', help='Apply changes (default is a dry run).')
        parser.add_argument('--precision-report', help='JSON from check_musicbrainz_url_precision --out (required with --write).')
        parser.add_argument('--min-precision', type=float, default=0.95)
        parser.add_argument('--min-compared', type=int, default=1000)
        parser.add_argument('--batch-size', type=int, default=50_000, help='Rows per write transaction (10k-100k).')
        parser.add_argument('--skip-hydration', action='store_true', help='Do not mark hydration items matched.')
        parser.add_argument('--mbid-prefix', default='', help='Hex MBID prefix to run on a slice (e.g. 0a ~ 1/256).')
        parser.add_argument('--max-batches', type=int, help='Stop after this many write batches (resume later).')
        parser.add_argument('--resume-run-id', type=UUID)
        parser.add_argument('--explain', action='store_true', help='Print EXPLAIN of the main statements.')
        parser.add_argument('--evidence-path', help='Write recordings with several Spotify IDs (evidence only) as TSV.')
        parser.add_argument('--json', action='store_true')

    def handle(self, *args, **options):
        if not 1 <= options['batch_size'] <= 100_000:
            raise CommandError('--batch-size must be between 1 and 100000')
        write = options['write']
        run = None
        resume = {}
        if options.get('resume_run_id'):
            run = CanonicalAliasMaterializationRun.objects.get(pk=options['resume_run_id'])
            if run.algorithm_version != ALGORITHM_VERSION:
                raise CommandError(f'Run {run.id} uses incompatible algorithm {run.algorithm_version}.')
            if run.status == 'succeeded':
                raise CommandError(f'Run {run.id} has already succeeded.')
            if not write:
                raise CommandError('--resume-run-id requires --write')
            resume = dict(run.checkpoints or {})
            source_version = run.source_version
        else:
            source_version = options.get('source_version') or latest_musicbrainz_url_source_version()

        if write:
            if not options.get('precision_report'):
                raise CommandError('--write requires --precision-report (run check_musicbrainz_url_precision first).')
            load_precision_gate(
                options['precision_report'],
                source_version=source_version,
                min_precision=options['min_precision'],
                min_compared=options['min_compared'],
            )

        log = self.stderr.write
        stats = build_workspace(
            source_version,
            mbid_prefix=options['mbid_prefix'],
            explain=options['explain'],
            progress=lambda message: log(message),
        )
        new_total = stats.status_counts.get(STATUS_NEW, 0)
        if options.get('evidence_path'):
            self._write_evidence(options['evidence_path'])

        if write and run is None:
            run = CanonicalAliasMaterializationRun.objects.create(
                source_version=source_version,
                algorithm_version=ALGORITHM_VERSION,
                status='running',
                current_phase='aliases',
                batch_size=options['batch_size'],
                total_items=new_total,
                checkpoints={'mbid_prefix': options['mbid_prefix']},
            )
        elif run is not None:
            run.status = 'running'
            run.last_error = ''
            run.completed_at = None
            run.save()

        batches = 0
        created = int(run.created_count) if run else 0
        started = time.monotonic()
        processed_total = int(run.processed_items) if run else 0
        last_mbid = resume.get('last_mbid')
        hydration_matched = int(resume.get('hydration_matched') or 0)
        hydration_candidates = 0
        paused = False
        try:
            if resume.get('phase') != 'hydration':
                done_this_run = 0
                while True:
                    result = apply_alias_batch(
                        source_version=source_version, last_mbid=last_mbid,
                        batch_size=options['batch_size'], write=write,
                    )
                    if result.processed == 0:
                        break
                    batches += 1
                    done_this_run += result.processed
                    processed_total += result.processed
                    created += result.changed
                    last_mbid = result.cursor_value
                    rate = done_this_run / max(time.monotonic() - started, 1e-9)
                    remaining = max(new_total - processed_total, 0)
                    log(
                        f'phase=aliases processed={processed_total}/{new_total} '
                        f'{"created" if write else "would_create"}={created} '
                        f'rate={rate:.0f}/s eta={remaining / rate if rate else 0:.0f}s last_mbid={last_mbid}'
                    )
                    if run is not None:
                        run.processed_items = processed_total
                        run.created_count = created
                        run.batches_processed += 1
                        run.checkpoints = {**run.checkpoints, 'phase': 'aliases', 'last_mbid': last_mbid}
                        run.save()
                    if options.get('max_batches') and batches >= options['max_batches']:
                        paused = True
                        break

            if not paused and not options['skip_hydration']:
                hydration_candidates, plan = collect_hydration_targets(explain=options['explain'])
                if plan:
                    log('--- EXPLAIN hydration')
                    for line in plan:
                        log(line)
                if run is not None:
                    run.current_phase = 'hydration'
                    run.checkpoints = {**run.checkpoints, 'phase': 'hydration'}
                    run.save()
                last_id = int(resume.get('last_phi_id') or 0)
                hydration_started = time.monotonic()
                hydration_done = 0
                while True:
                    result = apply_hydration_batch(
                        source_version=source_version, last_id=last_id,
                        batch_size=options['batch_size'], write=write,
                    )
                    if result.processed == 0:
                        break
                    batches += 1
                    hydration_done += result.processed
                    hydration_matched += result.changed
                    last_id = int(result.cursor_value)
                    rate = hydration_done / max(time.monotonic() - hydration_started, 1e-9)
                    log(
                        f'phase=hydration processed={hydration_done}/{hydration_candidates} '
                        f'{"matched" if write else "would_match"}={hydration_matched} '
                        f'rate={rate:.0f}/s eta={max(hydration_candidates - hydration_done, 0) / rate if rate else 0:.0f}s'
                    )
                    if run is not None:
                        run.checkpoints = {
                            **run.checkpoints, 'last_phi_id': last_id, 'hydration_matched': hydration_matched,
                        }
                        run.save()
                    if options.get('max_batches') and batches >= options['max_batches']:
                        paused = True
                        break
        except Exception as exc:
            if run is not None:
                run.status = 'failed'
                run.last_error = str(exc)
                run.save()
            raise

        if run is not None:
            if paused:
                run.status = 'pending'
                run.current_phase = 'paused'
            else:
                run.status = 'succeeded'
                run.current_phase = 'complete'
                run.completed_at = timezone.now()
            run.save()

        payload = {
            'mode': 'write' if write else 'dry-run',
            'run_id': str(run.id) if run else None,
            'status': ('paused' if paused else 'complete'),
            'source_version': source_version,
            **stats.as_dict(),
            'aliases_created' if write else 'aliases_would_create': created,
            'hydration_candidates': hydration_candidates,
            'hydration_matched' if write else 'hydration_would_match': hydration_matched,
        }
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))

    @staticmethod
    def _write_evidence(path):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT s.recording_mbid::text, s.spotify_id
                FROM tmp_mbu_stage s
                JOIN tmp_mbu_recording r ON r.recording_mbid = s.recording_mbid
                WHERE r.id_count > 1
                GROUP BY s.recording_mbid, s.spotify_id
                ORDER BY s.recording_mbid, s.spotify_id
            ''')
            rows = cursor.fetchall()
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('recording_mbid\tspotify_track_id\n')
            for mbid, spotify_id in rows:
                handle.write(f'{mbid}\t{spotify_id}\n')

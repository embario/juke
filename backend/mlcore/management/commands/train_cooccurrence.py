from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from mlcore.services.cooccurrence import (
    BEHAVIOR_SOURCE_LISTENBRAINZ,
    BEHAVIOR_SOURCE_SEARCH_HISTORY,
    DEFAULT_BEHAVIOR_SOURCES,
    train_cooccurrence,
)


class Command(BaseCommand):
    help = 'Train the cooccurrence ranker from behavioral baskets and persist ItemCoOccurrence rows.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--split',
            choices=['train', 'test', 'all'],
            default='train',
            help='Behavioral split to train on. Default: train.',
        )
        parser.add_argument(
            '--split-buckets',
            type=int,
            default=10,
            help='Bucket count for deterministic split selection. Default: 10.',
        )
        parser.add_argument(
            '--source',
            action='append',
            dest='sources',
            choices=[BEHAVIOR_SOURCE_SEARCH_HISTORY, BEHAVIOR_SOURCE_LISTENBRAINZ],
            help='Behavior source to include (repeatable). Default: blended search_history + listenbrainz.',
        )
        parser.add_argument(
            '--resume-run-id',
            type=UUID,
            default=None,
            help='Existing cooccurrence TrainingRun UUID to continue without truncating pair rows.',
        )
        parser.add_argument(
            '--start-bucket',
            type=int,
            default=0,
            help='First cooccurrence SQL bucket to process. Only valid for listenbrainz-only training.',
        )
        parser.add_argument(
            '--resume',
            action='store_true',
            help='Skip buckets already marked succeeded/assumed_succeeded for the selected training run.',
        )

    def handle(self, *args, **options):
        split_buckets = options['split_buckets']
        if split_buckets <= 0:
            raise CommandError('--split-buckets must be > 0')

        sources = options.get('sources') or list(DEFAULT_BEHAVIOR_SOURCES)
        resume_run_id = options['resume_run_id']
        start_bucket = options['start_bucket']
        if start_bucket < 0:
            raise CommandError('--start-bucket must be >= 0')
        uses_resume_options = resume_run_id is not None or start_bucket or options['resume']
        if uses_resume_options and sources != [BEHAVIOR_SOURCE_LISTENBRAINZ]:
            raise CommandError(
                'Bucket resume options are only supported with exactly: --source listenbrainz'
            )

        result = train_cooccurrence(
            split=options['split'],
            split_buckets=split_buckets,
            sources=sources,
            resume_training_run_id=resume_run_id,
            start_bucket=start_bucket,
            resume=options['resume'],
        )

        self.stdout.write(self.style.SUCCESS(
            'cooccurrence trained: '
            f"run={result.training_run_id} "
            f"split={options['split']} "
            f"sources={','.join(sources)} "
            f"baskets={result.baskets_processed} "
            f"pairs={result.pairs_written} "
            f"rows={result.source_row_count} "
            f"hash={result.training_hash[:12]}"
        ))

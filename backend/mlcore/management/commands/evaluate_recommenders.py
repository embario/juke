from django.core.management.base import BaseCommand

from mlcore.models import TrainingRun
from mlcore.services.cooccurrence import (
    BEHAVIOR_SOURCE_LISTENBRAINZ,
    BEHAVIOR_SOURCE_SEARCH_HISTORY,
    DEFAULT_BEHAVIOR_SOURCES,
    _SPLIT_BUCKET_COUNT,
    _baskets_to_hash,
    baskets_from_behavioral_sources_with_count,
)
from mlcore.services.evaluation import (
    DEFAULT_COLD_THRESHOLD,
    DEFAULT_EVALUATION_BATCH_SIZE,
    DEFAULT_K,
    RANKERS,
    run_offline_evaluation,
)


class Command(BaseCommand):
    help = (
        'Run offline leave-one-out evaluation of baseline recommenders over '
        'behavioral baskets and persist metrics to mlcore_model_evaluation.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--ranker', action='append', dest='rankers', choices=sorted(RANKERS),
            help='Ranker label to evaluate (repeatable). Default: all.',
        )
        parser.add_argument('--k', type=int, default=DEFAULT_K)
        parser.add_argument('--cold-threshold', type=int, default=DEFAULT_COLD_THRESHOLD)
        parser.add_argument(
            '--source',
            action='append',
            dest='sources',
            choices=[BEHAVIOR_SOURCE_SEARCH_HISTORY, BEHAVIOR_SOURCE_LISTENBRAINZ],
            help='Behavior source to include (repeatable). Default: blended search_history + listenbrainz.',
        )
        parser.add_argument(
            '--no-persist', action='store_true',
            help='Compute and print metrics without writing ModelEvaluation rows.',
        )
        parser.add_argument(
            '--max-baskets',
            type=int,
            default=None,
            help='Evaluate a deterministic prefix sample of eligible baskets instead of materializing the full split.',
        )
        parser.add_argument(
            '--max-basket-items',
            type=int,
            default=None,
            help='Exclude evaluation baskets with more than this many distinct items.',
        )
        parser.add_argument(
            '--skip-hash-check',
            action='store_true',
            help='Skip recomputing the current training hash before evaluation.',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=DEFAULT_EVALUATION_BATCH_SIZE,
            help='Number of leave-one-out trials to score per database fetch batch.',
        )
        parser.add_argument(
            '--metrics-path',
            default=None,
            help='Optional Prometheus textfile path for evaluation progress metrics.',
        )

    def handle(self, *args, **options):
        labels = options.get('rankers')
        sources = options.get('sources') or list(DEFAULT_BEHAVIOR_SOURCES)
        cooccurrence_training_run = None

        if labels is None or 'cooccurrence' in labels:
            cooccurrence_training_run = TrainingRun.objects.filter(
                ranker_label='cooccurrence',
            ).order_by('-created_at').first()

            if cooccurrence_training_run is None:
                self.stdout.write(
                    self.style.WARNING(
                        'No cooccurrence training run found. Run train_cooccurrence() before evaluating the cooccurrence ranker.'
                    )
                )
            elif not options['skip_hash_check'] and options['max_baskets'] is None:
                current_baskets, _ = baskets_from_behavioral_sources_with_count(
                    split='train',
                    split_buckets=_SPLIT_BUCKET_COUNT,
                    sources=sources,
                )
                current_hash = _baskets_to_hash(current_baskets)
                if current_hash != cooccurrence_training_run.training_hash:
                    self.stdout.write(
                        self.style.WARNING(
                            'cooccurrence training hash mismatch: '
                            f'latest={cooccurrence_training_run.training_hash[:12]} '
                            f'current={current_hash[:12]}'
                        )
                    )

        results = run_offline_evaluation(
            labels=labels,
            k=options['k'],
            cold_threshold=options['cold_threshold'],
            split='test',
            sources=sources,
            cooccurrence_training_run=cooccurrence_training_run,
            max_baskets=options['max_baskets'],
            max_basket_items=options['max_basket_items'],
            batch_size=options['batch_size'],
            metrics_path=options['metrics_path'],
            persist=not options['no_persist'],
        )

        if not results:
            self.stdout.write(self.style.WARNING(
                'No trials generated — need behavioral sessions with >=2 track interactions.'
            ))
            return

        for r in results:
            self.stdout.write(self.style.SUCCESS(
                f"{r.candidate_label}: trials={r.n_trials} (cold={r.n_cold_trials}) "
                f"dataset={r.dataset_hash[:12]}"
            ))
            for name, value in sorted(r.metrics.items()):
                self.stdout.write(f"  {name:<24} {value:.4f}")

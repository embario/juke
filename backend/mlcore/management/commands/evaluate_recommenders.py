from django.core.management.base import BaseCommand

from mlcore.models import TrainingRun
from mlcore.services.cooccurrence import (
    _SPLIT_BUCKET_COUNT,
    _baskets_to_hash,
    baskets_from_search_history_with_count,
)
from mlcore.services.evaluation import (
    DEFAULT_COLD_THRESHOLD,
    DEFAULT_K,
    RANKERS,
    run_offline_evaluation,
)


class Command(BaseCommand):
    help = (
        'Run offline leave-one-out evaluation of baseline recommenders over '
        'SearchHistory baskets and persist metrics to mlcore_model_evaluation.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--ranker', action='append', dest='rankers', choices=sorted(RANKERS),
            help='Ranker label to evaluate (repeatable). Default: all.',
        )
        parser.add_argument('--k', type=int, default=DEFAULT_K)
        parser.add_argument('--cold-threshold', type=int, default=DEFAULT_COLD_THRESHOLD)
        parser.add_argument(
            '--no-persist', action='store_true',
            help='Compute and print metrics without writing ModelEvaluation rows.',
        )

    def handle(self, *args, **options):
        labels = options.get('rankers')
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
            else:
                current_baskets, _ = baskets_from_search_history_with_count(
                    split='train',
                    split_buckets=_SPLIT_BUCKET_COUNT,
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
            cooccurrence_training_run=cooccurrence_training_run,
            persist=not options['no_persist'],
        )

        if not results:
            self.stdout.write(self.style.WARNING(
                'No trials generated — need SearchHistory sessions with >=2 track interactions.'
            ))
            return

        for r in results:
            self.stdout.write(self.style.SUCCESS(
                f"{r.candidate_label}: trials={r.n_trials} (cold={r.n_cold_trials}) "
                f"dataset={r.dataset_hash[:12]}"
            ))
            for name, value in sorted(r.metrics.items()):
                self.stdout.write(f"  {name:<24} {value:.4f}")

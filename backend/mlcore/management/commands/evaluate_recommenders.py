from django.core.management.base import BaseCommand

from mlcore.services.evaluation import DEFAULT_COLD_THRESHOLD, DEFAULT_K, RANKERS, run_offline_evaluation


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
        results = run_offline_evaluation(
            labels=options.get('rankers'),
            k=options['k'],
            cold_threshold=options['cold_threshold'],
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

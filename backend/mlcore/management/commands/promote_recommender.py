from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from mlcore.services.promotion import (
    PromotionError,
    approve_promotion,
    check_promotion_gates,
    request_promotion,
)


class Command(BaseCommand):
    help = (
        'Request a recommender promotion (runs gate checks) and optionally approve. '
        'Without --approve, prints gate results only — no ModelPromotion row is written.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--candidate', required=True, help='Candidate ranker label')
        parser.add_argument('--baseline', required=True, help='Baseline ranker label to compare against')
        parser.add_argument('--dataset-hash', help='Eval dataset hash (default: latest shared)')
        parser.add_argument('--request', action='store_true',
                            help='Create a ModelPromotion row (status=pending or blocked)')
        parser.add_argument('--approve', action='store_true',
                            help='Implies --request; also approve if gates pass (requires --approver)')
        parser.add_argument('--approver', help='Username of approving staff member')

    def handle(self, *args, **opts):
        cand, base = opts['candidate'], opts['baseline']

        # Approval requires an approver up front — fail fast before touching the DB.
        approver = None
        if opts['approve']:
            if not opts.get('approver'):
                raise CommandError('--approve requires --approver <username>')
            User = get_user_model()
            try:
                approver = User.objects.get(username=opts['approver'])
            except User.DoesNotExist:
                raise CommandError(f"approver '{opts['approver']}' not found")

        # Dry-run gate display if neither --request nor --approve.
        if not opts['request'] and not opts['approve']:
            dh = opts.get('dataset_hash')
            if not dh:
                raise CommandError('dry-run requires --dataset-hash (or use --request to auto-resolve)')
            checks = check_promotion_gates(cand, base, dh)
            self._print_gates(checks)
            return

        try:
            promo = request_promotion(cand, base, dataset_hash=opts.get('dataset_hash'))
        except PromotionError as e:
            raise CommandError(str(e))

        self.stdout.write(f"promotion {promo.id} created: status={promo.status} dataset={promo.dataset_hash[:12]}")
        self._print_gates_dict(promo.gate_results)

        if promo.status == 'blocked':
            self.stdout.write(self.style.ERROR(f"BLOCKED: {promo.block_reason}"))
            return

        if opts['approve']:
            try:
                approve_promotion(promo, approver)
            except PromotionError as e:
                raise CommandError(str(e))
            self.stdout.write(self.style.SUCCESS(
                f"APPROVED by {approver.username} at {promo.approved_at.isoformat()}"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                'status=pending — approve via admin or re-run with --approve --approver <username>'
            ))

    def _print_gates(self, checks):
        for c in checks:
            mark = self.style.SUCCESS('PASS') if c.passed else self.style.ERROR('FAIL')
            self.stdout.write(f"  [{mark}] {c.name}: {c.message}")

    def _print_gates_dict(self, gate_results):
        for name, d in gate_results.items():
            mark = self.style.SUCCESS('PASS') if d['passed'] else self.style.ERROR('FAIL')
            self.stdout.write(f"  [{mark}] {name}: {d['message']}")

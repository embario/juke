"""
Tests for mlcore/services/promotion.py — gate checks + approval workflow.

The test harness seeds ModelEvaluation rows directly rather than running the
full evaluator, so each gate's pass/fail boundary can be hit precisely.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from mlcore.models import ModelEvaluation, ModelPromotion
from mlcore.services.evaluation import (
    METRIC_COLD_RECALL,
    METRIC_COVERAGE,
    METRIC_NDCG,
    METRIC_RECALL,
)
from mlcore.services.promotion import (
    GateCheck,
    PromotionError,
    _latest_shared_dataset_hash,
    approve_promotion,
    check_promotion_gates,
    gates_passed,
    reject_promotion,
    request_promotion,
)

User = get_user_model()

HASH_A = 'a' * 64
HASH_B = 'b' * 64


def _seed(label, dataset_hash=HASH_A, *, recall, ndcg, coverage, cold):
    """Write all four metrics for a ranker label on one dataset."""
    for name, val in [(METRIC_RECALL, recall), (METRIC_NDCG, ndcg),
                      (METRIC_COVERAGE, coverage), (METRIC_COLD_RECALL, cold)]:
        ModelEvaluation.objects.create(
            candidate_label=label, metric_name=name, metric_value=val, dataset_hash=dataset_hash,
        )


# Lock thresholds for every test in this module so defaults changing in settings
# doesn't silently shift pass/fail boundaries here.
@override_settings(
    JUKE_PROMOTION_GATE_NDCG_MIN_LIFT=0.05,
    JUKE_PROMOTION_GATE_RECALL_MIN_LIFT=0.03,
    JUKE_PROMOTION_GATE_COLDSTART_MAX_REGRESSION=0.02,
    JUKE_PROMOTION_GATE_COVERAGE_MIN=0.30,
)
class GateCheckTests(TestCase):

    def _check_by_name(self, checks, name):
        return next(c for c in checks if c.name == name)

    # --- all-pass happy path ---

    def test_all_four_gates_pass(self):
        # baseline: recall=0.40 ndcg=0.30 cold=0.20 cov=irrelevant
        # candidate: +6% ndcg, +5% recall, cold down by 0.01 (within tol), cov=0.35
        _seed('base', recall=0.40, ndcg=0.30, coverage=0.10, cold=0.20)
        _seed('cand', recall=0.42, ndcg=0.318, coverage=0.35, cold=0.19)
        checks = check_promotion_gates('cand', 'base', HASH_A)
        self.assertEqual(len(checks), 4)
        self.assertTrue(gates_passed(checks))
        self.assertEqual({c.name for c in checks},
                         {'ndcg_lift', 'recall_lift', 'cold_start_regression', 'coverage_floor'})

    # --- ndcg lift gate ---
    #
    # Boundary tests use values where (cand - base) / base is exactly
    # representable in IEEE-754 — e.g. 0.5 → 0.53125 gives lift = 1/16 = 0.0625.
    # Values like 0.40 → 0.42 look like +5% on paper but compute to 0.049999...
    # which correctly fails >= 0.05. The gate is conservative by design.

    def test_ndcg_lift_above_threshold_passes(self):
        _seed('base', recall=0.50, ndcg=0.50, coverage=0.50, cold=0.30)
        _seed('cand', recall=0.60, ndcg=0.53125, coverage=0.50, cold=0.30)  # lift = 0.0625
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'ndcg_lift')
        self.assertTrue(c.passed)
        self.assertEqual(c.candidate_value, 0.53125)
        self.assertEqual(c.baseline_value, 0.50)
        self.assertEqual(c.threshold, 0.05)

    def test_ndcg_lift_just_under_fails(self):
        _seed('base', recall=0.50, ndcg=0.50, coverage=0.50, cold=0.30)
        _seed('cand', recall=0.60, ndcg=0.515625, coverage=0.50, cold=0.30)  # lift = 0.03125
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'ndcg_lift')
        self.assertFalse(c.passed)

    def test_ndcg_lift_zero_baseline_positive_cand_passes(self):
        # base=0 → relative lift undefined → any positive cand passes
        _seed('base', recall=0.50, ndcg=0.0, coverage=0.50, cold=0.30)
        _seed('cand', recall=0.60, ndcg=0.01, coverage=0.50, cold=0.30)
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'ndcg_lift')
        self.assertTrue(c.passed)
        self.assertIn('inf', c.message)

    def test_ndcg_lift_zero_vs_zero_fails(self):
        _seed('base', recall=0.50, ndcg=0.0, coverage=0.50, cold=0.30)
        _seed('cand', recall=0.60, ndcg=0.0, coverage=0.50, cold=0.30)
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'ndcg_lift')
        self.assertFalse(c.passed)

    # --- recall lift gate ---

    def test_recall_lift_above_threshold_passes(self):
        _seed('base', recall=0.50, ndcg=0.50, coverage=0.50, cold=0.30)
        _seed('cand', recall=0.53125, ndcg=0.60, coverage=0.50, cold=0.30)  # lift = 0.0625 > 0.03
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'recall_lift')
        self.assertTrue(c.passed)

    def test_recall_worse_than_baseline_fails(self):
        _seed('base', recall=0.40, ndcg=0.50, coverage=0.50, cold=0.30)
        _seed('cand', recall=0.35, ndcg=0.60, coverage=0.50, cold=0.30)
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'recall_lift')
        self.assertFalse(c.passed)
        self.assertIn('-', c.message)  # negative lift shown

    # --- cold-start regression gate ---

    def test_cold_regression_within_tolerance(self):
        _seed('base', recall=0.50, ndcg=0.50, coverage=0.50, cold=0.30)
        _seed('cand', recall=0.60, ndcg=0.60, coverage=0.50, cold=0.28)  # dropped 0.02, at limit
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'cold_start_regression')
        self.assertTrue(c.passed)

    def test_cold_regression_exceeded_fails(self):
        _seed('base', recall=0.50, ndcg=0.50, coverage=0.50, cold=0.30)
        _seed('cand', recall=0.60, ndcg=0.60, coverage=0.50, cold=0.27)  # dropped 0.03
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'cold_start_regression')
        self.assertFalse(c.passed)

    def test_cold_improvement_passes(self):
        # Candidate better on cold-start → regression is negative → easily passes
        _seed('base', recall=0.50, ndcg=0.50, coverage=0.50, cold=0.30)
        _seed('cand', recall=0.60, ndcg=0.60, coverage=0.50, cold=0.40)
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'cold_start_regression')
        self.assertTrue(c.passed)

    # --- coverage floor gate ---

    def test_coverage_floor_exact(self):
        _seed('base', recall=0.50, ndcg=0.50, coverage=0.10, cold=0.30)  # base cov irrelevant
        _seed('cand', recall=0.60, ndcg=0.60, coverage=0.30, cold=0.30)
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'coverage_floor')
        self.assertTrue(c.passed)
        self.assertIsNone(c.baseline_value)  # absolute check, no baseline

    def test_coverage_below_floor_fails(self):
        _seed('base', recall=0.50, ndcg=0.50, coverage=0.99, cold=0.30)  # base high, still irrelevant
        _seed('cand', recall=0.60, ndcg=0.60, coverage=0.29, cold=0.30)
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'coverage_floor')
        self.assertFalse(c.passed)

    # --- missing metrics ---

    def test_missing_candidate_metric_fails_gate(self):
        _seed('base', recall=0.50, ndcg=0.50, coverage=0.50, cold=0.30)
        # no candidate rows at all
        checks = check_promotion_gates('ghost', 'base', HASH_A)
        self.assertFalse(gates_passed(checks))
        for c in checks:
            self.assertFalse(c.passed)
            self.assertIn('no ', c.message)

    def test_missing_baseline_metric_fails_gate(self):
        _seed('cand', recall=0.50, ndcg=0.50, coverage=0.50, cold=0.30)
        c = self._check_by_name(check_promotion_gates('cand', 'ghost', HASH_A), 'ndcg_lift')
        self.assertFalse(c.passed)
        self.assertIn('ghost', c.message)

    def test_latest_metric_wins_on_rerun(self):
        # Older cand row with bad ndcg, then newer row with good ndcg → gate uses newer
        _seed('base', recall=0.50, ndcg=0.40, coverage=0.50, cold=0.30)
        ModelEvaluation.objects.create(candidate_label='cand', metric_name=METRIC_NDCG,
                                       metric_value=0.30, dataset_hash=HASH_A)  # old, bad
        _seed('cand', recall=0.60, ndcg=0.50, coverage=0.50, cold=0.30)  # new, good (+25%)
        c = self._check_by_name(check_promotion_gates('cand', 'base', HASH_A), 'ndcg_lift')
        self.assertTrue(c.passed)
        self.assertEqual(c.candidate_value, 0.50)

    # --- gate_results serialization ---

    def test_gatecheck_to_dict_round_trips(self):
        c = GateCheck('x', True, 0.5, 0.4, 0.05, 'msg')
        d = c.to_dict()
        self.assertEqual(d, {'name': 'x', 'passed': True, 'candidate_value': 0.5,
                             'baseline_value': 0.4, 'threshold': 0.05, 'message': 'msg'})


@override_settings(
    JUKE_PROMOTION_GATE_NDCG_MIN_LIFT=0.05,
    JUKE_PROMOTION_GATE_RECALL_MIN_LIFT=0.03,
    JUKE_PROMOTION_GATE_COLDSTART_MAX_REGRESSION=0.02,
    JUKE_PROMOTION_GATE_COVERAGE_MIN=0.30,
)
class RequestPromotionTests(TestCase):

    def test_passing_gates_creates_pending(self):
        _seed('base', recall=0.40, ndcg=0.30, coverage=0.10, cold=0.20)
        _seed('cand', recall=0.50, ndcg=0.40, coverage=0.50, cold=0.20)
        promo = request_promotion('cand', 'base', HASH_A)
        self.assertEqual(promo.status, 'pending')
        self.assertEqual(promo.block_reason, '')
        self.assertEqual(promo.dataset_hash, HASH_A)
        self.assertIsNone(promo.approved_by)
        self.assertIsNone(promo.approved_at)
        # All four gate results stored
        self.assertEqual(set(promo.gate_results.keys()),
                         {'ndcg_lift', 'recall_lift', 'cold_start_regression', 'coverage_floor'})
        for gr in promo.gate_results.values():
            self.assertTrue(gr['passed'])

    def test_failing_gate_creates_blocked(self):
        """THE HEADLINE TEST — failed gates block promotion."""
        _seed('base', recall=0.40, ndcg=0.30, coverage=0.10, cold=0.20)
        # Coverage too low — everything else fine
        _seed('cand', recall=0.50, ndcg=0.40, coverage=0.15, cold=0.20)
        promo = request_promotion('cand', 'base', HASH_A)
        self.assertEqual(promo.status, 'blocked')
        self.assertIn('coverage_floor', promo.block_reason)
        self.assertFalse(promo.gate_results['coverage_floor']['passed'])
        # Passing gates still recorded as passed — full provenance
        self.assertTrue(promo.gate_results['ndcg_lift']['passed'])

    def test_multiple_failed_gates_all_listed(self):
        _seed('base', recall=0.40, ndcg=0.30, coverage=0.10, cold=0.20)
        _seed('cand', recall=0.30, ndcg=0.25, coverage=0.10, cold=0.10)  # worse on everything
        promo = request_promotion('cand', 'base', HASH_A)
        self.assertEqual(promo.status, 'blocked')
        for name in ('ndcg_lift', 'recall_lift', 'cold_start_regression', 'coverage_floor'):
            self.assertIn(name, promo.block_reason)

    def test_auto_resolves_shared_dataset_hash(self):
        _seed('base', HASH_A, recall=0.40, ndcg=0.30, coverage=0.10, cold=0.20)
        _seed('cand', HASH_A, recall=0.50, ndcg=0.40, coverage=0.50, cold=0.20)
        promo = request_promotion('cand', 'base')  # no dataset_hash
        self.assertEqual(promo.dataset_hash, HASH_A)

    def test_raises_when_no_shared_hash(self):
        _seed('base', HASH_A, recall=0.40, ndcg=0.30, coverage=0.10, cold=0.20)
        _seed('cand', HASH_B, recall=0.50, ndcg=0.40, coverage=0.50, cold=0.20)  # different hash
        with self.assertRaises(PromotionError) as ctx:
            request_promotion('cand', 'base')
        self.assertIn('no shared evaluation dataset', str(ctx.exception))

    def test_raises_when_no_eval_rows_at_all(self):
        with self.assertRaises(PromotionError):
            request_promotion('cand', 'base')


class LatestSharedDatasetHashTests(TestCase):

    def test_picks_hash_both_have(self):
        _seed('a', HASH_A, recall=0.1, ndcg=0.1, coverage=0.1, cold=0.1)
        _seed('a', HASH_B, recall=0.1, ndcg=0.1, coverage=0.1, cold=0.1)
        _seed('b', HASH_A, recall=0.1, ndcg=0.1, coverage=0.1, cold=0.1)
        # a has both hashes, b has only A → shared is A
        self.assertEqual(_latest_shared_dataset_hash('a', 'b'), HASH_A)

    def test_none_when_candidate_has_no_rows(self):
        _seed('b', HASH_A, recall=0.1, ndcg=0.1, coverage=0.1, cold=0.1)
        self.assertIsNone(_latest_shared_dataset_hash('a', 'b'))

    def test_none_when_no_overlap(self):
        _seed('a', HASH_A, recall=0.1, ndcg=0.1, coverage=0.1, cold=0.1)
        _seed('b', HASH_B, recall=0.1, ndcg=0.1, coverage=0.1, cold=0.1)
        self.assertIsNone(_latest_shared_dataset_hash('a', 'b'))


@override_settings(
    JUKE_PROMOTION_GATE_NDCG_MIN_LIFT=0.05,
    JUKE_PROMOTION_GATE_RECALL_MIN_LIFT=0.03,
    JUKE_PROMOTION_GATE_COLDSTART_MAX_REGRESSION=0.02,
    JUKE_PROMOTION_GATE_COVERAGE_MIN=0.30,
)
class ApprovePromotionTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(username='staff', email='s@x.com',
                                              password='p', is_staff=True)
        self.pleb = User.objects.create_user(username='pleb', email='p@x.com', password='p')
        _seed('base', recall=0.40, ndcg=0.30, coverage=0.10, cold=0.20)
        _seed('cand', recall=0.50, ndcg=0.40, coverage=0.50, cold=0.20)

    def test_staff_approves_pending(self):
        promo = request_promotion('cand', 'base', HASH_A)
        self.assertEqual(promo.status, 'pending')
        approve_promotion(promo, self.staff)
        promo.refresh_from_db()
        self.assertEqual(promo.status, 'approved')
        self.assertEqual(promo.approved_by, self.staff)
        self.assertIsNotNone(promo.approved_at)

    def test_non_staff_cannot_approve(self):
        promo = request_promotion('cand', 'base', HASH_A)
        with self.assertRaises(PromotionError) as ctx:
            approve_promotion(promo, self.pleb)
        self.assertIn('not staff', str(ctx.exception))
        promo.refresh_from_db()
        self.assertEqual(promo.status, 'pending')  # unchanged

    def test_cannot_approve_blocked(self):
        """THE OTHER HEADLINE TEST — blocked status is terminal, approval refused."""
        _seed('bad', recall=0.30, ndcg=0.20, coverage=0.10, cold=0.10)
        promo = request_promotion('bad', 'base', HASH_A)
        self.assertEqual(promo.status, 'blocked')
        with self.assertRaises(PromotionError) as ctx:
            approve_promotion(promo, self.staff)
        self.assertIn("'blocked'", str(ctx.exception))
        promo.refresh_from_db()
        self.assertEqual(promo.status, 'blocked')
        self.assertIsNone(promo.approved_by)

    def test_cannot_approve_twice(self):
        promo = request_promotion('cand', 'base', HASH_A)
        approve_promotion(promo, self.staff)
        with self.assertRaises(PromotionError) as ctx:
            approve_promotion(promo, self.staff)
        self.assertIn("'approved'", str(ctx.exception))

    def test_gates_rechecked_at_approval_time(self):
        """
        Race window: request_promotion() passed, but a newer regressed eval
        row lands before approval. approve_promotion() re-runs gates and flips
        the row to blocked rather than approving stale results.
        """
        promo = request_promotion('cand', 'base', HASH_A)
        self.assertEqual(promo.status, 'pending')
        # Newer row with terrible coverage arrives after the request
        ModelEvaluation.objects.create(candidate_label='cand', metric_name=METRIC_COVERAGE,
                                       metric_value=0.05, dataset_hash=HASH_A)
        with self.assertRaises(PromotionError) as ctx:
            approve_promotion(promo, self.staff)
        self.assertIn('coverage_floor', str(ctx.exception))
        promo.refresh_from_db()
        self.assertEqual(promo.status, 'blocked')
        self.assertFalse(promo.gate_results['coverage_floor']['passed'])
        self.assertIsNone(promo.approved_by)


@override_settings(
    JUKE_PROMOTION_GATE_NDCG_MIN_LIFT=0.05,
    JUKE_PROMOTION_GATE_RECALL_MIN_LIFT=0.03,
    JUKE_PROMOTION_GATE_COLDSTART_MAX_REGRESSION=0.02,
    JUKE_PROMOTION_GATE_COVERAGE_MIN=0.30,
)
class RejectPromotionTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(username='staff', email='s@x.com',
                                              password='p', is_staff=True)
        _seed('base', recall=0.40, ndcg=0.30, coverage=0.10, cold=0.20)
        _seed('cand', recall=0.50, ndcg=0.40, coverage=0.50, cold=0.20)

    def test_staff_rejects_pending(self):
        promo = request_promotion('cand', 'base', HASH_A)
        reject_promotion(promo, self.staff, reason='not ready for prime time')
        promo.refresh_from_db()
        self.assertEqual(promo.status, 'rejected')
        self.assertEqual(promo.block_reason, 'not ready for prime time')
        self.assertEqual(promo.approved_by, self.staff)  # records decision-maker
        self.assertIsNotNone(promo.approved_at)

    def test_non_staff_cannot_reject(self):
        pleb = User.objects.create_user(username='pleb', email='p@x.com', password='p')
        promo = request_promotion('cand', 'base', HASH_A)
        with self.assertRaises(PromotionError):
            reject_promotion(promo, pleb, reason='x')
        promo.refresh_from_db()
        self.assertEqual(promo.status, 'pending')

    def test_cannot_reject_already_approved(self):
        promo = request_promotion('cand', 'base', HASH_A)
        approve_promotion(promo, self.staff)
        with self.assertRaises(PromotionError):
            reject_promotion(promo, self.staff, reason='changed my mind')


@override_settings(
    JUKE_PROMOTION_GATE_NDCG_MIN_LIFT=0.05,
    JUKE_PROMOTION_GATE_RECALL_MIN_LIFT=0.03,
    JUKE_PROMOTION_GATE_COLDSTART_MAX_REGRESSION=0.02,
    JUKE_PROMOTION_GATE_COVERAGE_MIN=0.30,
)
class PromotionGatesBlockPromotionE2ETests(TestCase):
    """
    End-to-end demo per acceptance criteria: "Demonstration that failed gates
    block promotion." Walks the full request → approve path twice: once with
    a passing candidate, once with a failing one, on the same dataset.
    """

    def setUp(self):
        self.staff = User.objects.create_user(username='owner', email='o@x.com',
                                              password='p', is_staff=True)
        _seed('metadata', recall=0.40, ndcg=0.30, coverage=0.10, cold=0.20)

    def test_passing_candidate_reaches_approved(self):
        # cooccurrence beats metadata on all four gates
        _seed('cooccurrence', recall=0.48, ndcg=0.36, coverage=0.45, cold=0.21)
        promo = request_promotion('cooccurrence', 'metadata', HASH_A)
        approve_promotion(promo, self.staff)
        self.assertEqual(ModelPromotion.objects.get(pk=promo.pk).status, 'approved')

    def test_failing_candidate_never_reaches_approved(self):
        # cooccurrence wins on recall/ndcg/coverage but tanks cold-start by 0.05
        _seed('cooccurrence', recall=0.48, ndcg=0.36, coverage=0.45, cold=0.15)
        promo = request_promotion('cooccurrence', 'metadata', HASH_A)

        # Blocked at request time
        self.assertEqual(promo.status, 'blocked')
        self.assertIn('cold_start_regression', promo.block_reason)

        # And the approval path itself refuses
        with self.assertRaises(PromotionError):
            approve_promotion(promo, self.staff)

        # Final state: still blocked, no approver, no timestamp
        final = ModelPromotion.objects.get(pk=promo.pk)
        self.assertEqual(final.status, 'blocked')
        self.assertIsNone(final.approved_by)
        self.assertIsNone(final.approved_at)

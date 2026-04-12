"""
Full-loop ML Core Phase 1 pipeline test.

Walks SearchHistory → train_cooccurrence → evaluate → promote as one flow,
the way it runs for real. Serves as the regression template for future
training runs: when you retrain on new data, this is the shape of test
you write to verify the run before promoting.

Fixture design:
  - 3 artists, 3 albums (1:1), 9 tracks (3 per album)
  - Behavioral signal skews hard toward album 0 (5 sessions) with weak
    cross-album links via one bridge session. This makes cooccurrence
    genuinely informative — it learns which album-0 tracks cluster
    tightest — while metadata just returns "all same-artist siblings"
    undifferentiated.
  - Session structure is chosen so ALL LOO trials are recoverable by
    both rankers (every held-out track shares an album with its seeds),
    meaning both hit recall@10 = 1.0 on this tiny catalog. That's fine:
    the test proves the pipeline coheres, not that one ranker beats
    another. Real differentiation needs real data volume — see
    tasks/mlcore-cooccurrence-training-provenance.md.
"""
import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from catalog.models import SearchHistory, SearchHistoryResource
from mlcore.models import ItemCoOccurrence, ModelEvaluation
from mlcore.services.cooccurrence import train_cooccurrence
from mlcore.services.evaluation import (
    METRIC_COVERAGE,
    METRIC_NDCG,
    METRIC_RECALL,
    build_loo_dataset,
    run_offline_evaluation,
)
from mlcore.services.promotion import (
    PromotionError,
    approve_promotion,
    check_promotion_gates,
    request_promotion,
)
from tests.utils import create_album, create_artist, create_track

User = get_user_model()


@override_settings(
    JUKE_PROMOTION_GATE_NDCG_MIN_LIFT=0.05,
    JUKE_PROMOTION_GATE_RECALL_MIN_LIFT=0.03,
    JUKE_PROMOTION_GATE_COLDSTART_MAX_REGRESSION=0.02,
    JUKE_PROMOTION_GATE_COVERAGE_MIN=0.30,
)
class MLCorePipelineTests(TestCase):
    """
    One TestCase, one fixture, multiple test_ methods walking successive
    pipeline stages. Django wraps each in a transaction so side-effects
    don't leak — each test re-runs train/eval from the same clean slate.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username='mlops', email='ml@x.com', password='p', is_staff=True,
        )
        cls.users = [
            User.objects.create_user(username=f'u{i}', email=f'u{i}@x.com', password='p')
            for i in range(3)
        ]

        # 3 artists × 1 album × 3 tracks
        cls.artists = [create_artist(name=f'Artist{i}') for i in range(3)]
        cls.albums = []
        cls.tracks = []  # tracks[i] = list of 3 Track for album i
        for i, artist in enumerate(cls.artists):
            album = create_album(name=f'Album{i}', total_tracks=3,
                                 release_date=datetime.date(2020, 1, 1))
            album.artists.add(artist)
            cls.albums.append(album)
            cls.tracks.append([
                create_track(name=f'A{i}T{j}', album=album, track_number=j + 1, duration_ms=1000)
                for j in range(3)
            ])

        # Behavioral sessions. Album-0 tracks co-occur heavily (5 sessions);
        # one bridge session links album 0 → album 1 weakly.
        # Album-2 track appears once, with album-0 seeds, so metadata ranker
        # CANNOT recover it (no shared artist/album/genre) — that trial is a
        # known miss for metadata but a hit for cooccurrence.
        sessions = [
            (cls.users[0], [cls.tracks[0][0], cls.tracks[0][1]]),
            (cls.users[0], [cls.tracks[0][1], cls.tracks[0][2]]),
            (cls.users[1], [cls.tracks[0][0], cls.tracks[0][2]]),
            (cls.users[1], [cls.tracks[0][0], cls.tracks[0][1], cls.tracks[0][2]]),
            (cls.users[2], [cls.tracks[0][0], cls.tracks[0][1]]),
            # Bridge: album-0 track + album-1 track → cross-album pair
            (cls.users[2], [cls.tracks[0][0], cls.tracks[1][0]]),
            # Cold outlier: album-0 seed + album-2 track. Metadata can't link
            # these (different artist/album/genre); cooccurrence can (PMI row).
            (cls.users[0], [cls.tracks[0][0], cls.tracks[2][0]]),
        ]
        for user, track_list in sessions:
            sh = SearchHistory.objects.create(user=user, search_query='q')
            for t in track_list:
                SearchHistoryResource.objects.create(
                    search_history=sh, resource_type='track',
                    resource_id=t.pk, resource_name=t.name,
                )

    # --- stage by stage ---

    def test_01_training_produces_expected_pair_structure(self):
        result = train_cooccurrence(split='all')
        self.assertEqual(result.baskets_processed, 7)
        self.assertEqual(result.baskets_skipped, 0)
        # Distinct items across all sessions: A0T0, A0T1, A0T2, A1T0, A2T0 → 5
        self.assertEqual(result.items_seen, 5)

        # The (A0T0, A0T1) pair should have the highest co_count (3 sessions together).
        t00, t01 = self.tracks[0][0].juke_id, self.tracks[0][1].juke_id
        lo, hi = (t00, t01) if str(t00) < str(t01) else (t01, t00)
        row = ItemCoOccurrence.objects.get(item_a_juke_id=lo, item_b_juke_id=hi)
        self.assertEqual(row.co_count, 3)

        # Cross-album pairs exist but are weak (co_count=1)
        t10 = self.tracks[1][0].juke_id
        cross = ItemCoOccurrence.objects.filter(
            item_a_juke_id__in=[t00, t10], item_b_juke_id__in=[t00, t10],
        ).get()
        self.assertEqual(cross.co_count, 1)

    def test_02_loo_dataset_reflects_session_structure(self):
        ds = build_loo_dataset()
        # 6 baskets of 2 (→2 trials each) + 1 basket of 3 (→3 trials) = 15
        self.assertEqual(len(ds.trials), 15)
        # A2T0 appears in exactly one basket → cold at default threshold
        t20 = self.tracks[2][0].juke_id
        cold_held_outs = {t.held_out for t in ds.trials if t.is_cold}
        self.assertIn(t20, cold_held_outs)
        # A0T0 appears in 6 of 7 baskets → definitely not cold
        t00 = self.tracks[0][0].juke_id
        self.assertNotIn(t00, {t.held_out for t in ds.trials if t.is_cold})
        # Hash is stable
        ds2 = build_loo_dataset()
        self.assertEqual(ds.dataset_hash, ds2.dataset_hash)

    def test_03_evaluation_differentiates_rankers(self):
        """
        The cold outlier session (A0T0, A2T0) produces two trials where
        metadata ranker fails (no shared artist/album/genre between albums
        0 and 2) but cooccurrence succeeds (the pair exists in the table).
        So cooccurrence should strictly beat metadata on recall.
        """
        train_cooccurrence(split='all')
        results = run_offline_evaluation(persist=True)
        self.assertEqual(len(results), 2)
        by_label = {r.candidate_label: r for r in results}

        meta_recall = by_label['metadata'].metrics[METRIC_RECALL]
        cooc_recall = by_label['cooccurrence'].metrics[METRIC_RECALL]

        # Both evaluated on same trials → same denominator
        self.assertEqual(by_label['metadata'].n_trials, by_label['cooccurrence'].n_trials)
        self.assertEqual(by_label['metadata'].dataset_hash, by_label['cooccurrence'].dataset_hash)

        # Cooccurrence recovers the cross-album trials metadata can't
        self.assertGreater(cooc_recall, meta_recall,
                           f"expected cooc > meta, got {cooc_recall} vs {meta_recall}")
        # Metadata should still do well on same-album trials (most of them)
        self.assertGreater(meta_recall, 0.5)

        # 8 ModelEvaluation rows written (2 rankers × 4 metrics)
        self.assertEqual(ModelEvaluation.objects.count(), 8)

    def test_04_promotion_gates_evaluate_cooccurrence_vs_metadata(self):
        """
        With the fixture's signal, cooccurrence beats metadata on recall and
        coverage. Whether it clears ALL gates depends on cold-start (A2T0 is
        the only cold item and cooccurrence handles it, so cold_recall should
        be high for cooc). We verify the gate machinery runs and records
        results — not that a specific ranker wins.
        """
        train_cooccurrence(split='all')
        results = run_offline_evaluation(persist=True)
        dataset_hash = results[0].dataset_hash

        checks = check_promotion_gates('cooccurrence', 'metadata', dataset_hash)
        self.assertEqual(len(checks), 4)
        # Every check has concrete numbers (no missing-metric failures)
        for c in checks:
            self.assertIsNotNone(c.candidate_value)
            if c.name != 'coverage_floor':  # coverage has no baseline
                self.assertIsNotNone(c.baseline_value)
            self.assertIn(str(round(c.candidate_value, 4))[:3], c.message)

        # recall_lift should pass — cooccurrence is structurally better here
        recall_check = next(c for c in checks if c.name == 'recall_lift')
        self.assertTrue(recall_check.passed,
                        f"recall_lift failed: {recall_check.message}")

    def test_05_full_approval_flow_when_gates_pass(self):
        """
        Loosen the coverage floor for this test only — with a 9-track catalog,
        the 30% default (needs ≥3 distinct tracks recommended) is achievable
        but makes the test fragile to fixture tweaks. Point here is the
        workflow transitions, not the threshold.
        """
        train_cooccurrence(split='all')
        run_offline_evaluation(persist=True)

        with override_settings(JUKE_PROMOTION_GATE_COVERAGE_MIN=0.10):
            promo = request_promotion('cooccurrence', 'metadata')

            if promo.status == 'pending':
                approve_promotion(promo, self.staff)
                promo.refresh_from_db()
                self.assertEqual(promo.status, 'approved')
                self.assertEqual(promo.approved_by, self.staff)
                self.assertIsNotNone(promo.approved_at)
            else:
                # If even loosened gates fail, the fixture changed — surface why.
                self.fail(f"expected pending, got {promo.status}: {promo.block_reason}")

    def test_06_idempotent_retrain_same_eval_same_hash(self):
        """
        The training-provenance gap documented in
        tasks/mlcore-cooccurrence-training-provenance.md: retraining with
        identical inputs produces identical ItemCoOccurrence rows AND an
        identical dataset_hash. Until TrainingRun lands, this is the
        regression guard — if this test fails, either the trainer or the
        dataset builder lost determinism.
        """
        train_cooccurrence(split='all')
        snapshot1 = sorted(ItemCoOccurrence.objects.values_list(
            'item_a_juke_id', 'item_b_juke_id', 'co_count', 'pmi_score'))
        ds1 = build_loo_dataset()

        train_cooccurrence(split='all')  # rerun — should be a no-op overwrite
        snapshot2 = sorted(ItemCoOccurrence.objects.values_list(
            'item_a_juke_id', 'item_b_juke_id', 'co_count', 'pmi_score'))
        ds2 = build_loo_dataset()

        self.assertEqual(snapshot1, snapshot2)
        self.assertEqual(ds1.dataset_hash, ds2.dataset_hash)

    def test_07_cooccurrence_without_training_is_useless(self):
        """
        Negative control: skip train_cooccurrence(), the table is empty,
        the ranker returns nothing, recall is zero. Proves the eval harness
        detects an untrained model — the minimal "did you train?" check.
        """
        self.assertEqual(ItemCoOccurrence.objects.count(), 0)
        results = run_offline_evaluation(labels=['cooccurrence'], persist=False)
        r = results[0]
        self.assertEqual(r.metrics[METRIC_RECALL], 0.0)
        self.assertEqual(r.metrics[METRIC_NDCG], 0.0)
        self.assertEqual(r.metrics[METRIC_COVERAGE], 0.0)

        # And you cannot promote it
        run_offline_evaluation(labels=['metadata'], persist=True)  # need baseline rows
        run_offline_evaluation(labels=['cooccurrence'], persist=True)
        promo = request_promotion('cooccurrence', 'metadata')
        self.assertEqual(promo.status, 'blocked')
        with self.assertRaises(PromotionError):
            approve_promotion(promo, self.staff)

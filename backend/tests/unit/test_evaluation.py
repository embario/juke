"""
Tests for mlcore/services/evaluation.py.

Three layers:
  1. Pure metric math (SimpleTestCase, no DB)
  2. Dataset construction — determinism, hashing, cold-slice tagging
  3. DB-integrated rankers + full evaluate/persist pipeline
"""
import datetime
import math
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from catalog.models import SearchHistory, SearchHistoryResource
from mlcore.models import ItemCoOccurrence, ModelEvaluation, NormalizedInteraction, SourceIngestionRun, TrainingRun
from mlcore.services.cooccurrence import BEHAVIOR_SOURCE_LISTENBRAINZ, train_cooccurrence
from mlcore.services.evaluation import (
    METRIC_COLD_RECALL,
    METRIC_COVERAGE,
    METRIC_NDCG,
    METRIC_RECALL,
    CoOccurrenceRanker,
    Dataset,
    MetadataRanker,
    Trial,
    DEFAULT_COLD_THRESHOLD,
    build_loo_dataset,
    coverage,
    EvaluationResult,
    evaluate_ranker,
    ndcg_at_k,
    persist_evaluation,
    recall_at_k,
    run_offline_evaluation,
)
from tests.utils import create_album, create_artist, create_track

User = get_user_model()


def _uid(i):
    return uuid.UUID(int=i)


# --- pure metrics ---

class RecallAtKTests(SimpleTestCase):

    def test_hit_at_top(self):
        self.assertEqual(recall_at_k([_uid(1), _uid(2)], {_uid(1)}, k=10), 1.0)

    def test_miss(self):
        self.assertEqual(recall_at_k([_uid(1), _uid(2)], {_uid(99)}, k=10), 0.0)

    def test_hit_outside_k_window(self):
        ranked = [_uid(1), _uid(2), _uid(3)]
        self.assertEqual(recall_at_k(ranked, {_uid(3)}, k=2), 0.0)
        self.assertEqual(recall_at_k(ranked, {_uid(3)}, k=3), 1.0)

    def test_multiple_relevant_partial(self):
        # 2 relevant, 1 in top-k → 0.5
        ranked = [_uid(1), _uid(2)]
        self.assertEqual(recall_at_k(ranked, {_uid(1), _uid(99)}, k=10), 0.5)

    def test_empty_relevant(self):
        self.assertEqual(recall_at_k([_uid(1)], set(), k=10), 0.0)

    def test_empty_ranked(self):
        self.assertEqual(recall_at_k([], {_uid(1)}, k=10), 0.0)


class NDCGAtKTests(SimpleTestCase):

    def test_hit_rank_1_is_1(self):
        # Single relevant at rank 1: DCG=1/log2(2)=1, IDCG=1 → nDCG=1
        self.assertEqual(ndcg_at_k([_uid(1)], {_uid(1)}, k=10), 1.0)

    def test_hit_rank_3(self):
        # DCG = 1/log2(4) = 0.5; IDCG = 1 → nDCG = 0.5
        ranked = [_uid(9), _uid(8), _uid(1)]
        self.assertAlmostEqual(ndcg_at_k(ranked, {_uid(1)}, k=10), 0.5)

    def test_miss_is_zero(self):
        self.assertEqual(ndcg_at_k([_uid(1), _uid(2)], {_uid(99)}, k=10), 0.0)

    def test_rank_monotonicity(self):
        # Lower rank → strictly higher nDCG
        ranked = [_uid(i) for i in range(1, 11)]
        scores = [ndcg_at_k(ranked, {_uid(r)}, k=10) for r in range(1, 11)]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(len(set(scores)), 10)  # all distinct

    def test_two_relevant_both_top(self):
        # Both at ranks 1,2: DCG = 1/log2(2) + 1/log2(3); IDCG identical → 1.0
        ranked = [_uid(1), _uid(2), _uid(3)]
        self.assertAlmostEqual(ndcg_at_k(ranked, {_uid(1), _uid(2)}, k=10), 1.0)

    def test_two_relevant_one_displaced(self):
        # Relevant at ranks 1 and 3; ideal is ranks 1 and 2.
        ranked = [_uid(1), _uid(99), _uid(2)]
        dcg = 1.0 / math.log2(2) + 1.0 / math.log2(4)
        idcg = 1.0 / math.log2(2) + 1.0 / math.log2(3)
        self.assertAlmostEqual(ndcg_at_k(ranked, {_uid(1), _uid(2)}, k=10), dcg / idcg)

    def test_hit_outside_k(self):
        ranked = [_uid(1), _uid(2), _uid(3)]
        self.assertEqual(ndcg_at_k(ranked, {_uid(3)}, k=2), 0.0)

    def test_empty_relevant(self):
        self.assertEqual(ndcg_at_k([_uid(1)], set(), k=10), 0.0)


class CoverageTests(SimpleTestCase):

    def test_basic_fraction(self):
        self.assertEqual(coverage([_uid(1), _uid(2)], catalog_size=10), 0.2)

    def test_dedupes(self):
        self.assertEqual(coverage([_uid(1), _uid(1), _uid(1)], catalog_size=10), 0.1)

    def test_full_coverage(self):
        self.assertEqual(coverage([_uid(i) for i in range(5)], catalog_size=5), 1.0)

    def test_empty_catalog(self):
        self.assertEqual(coverage([_uid(1)], catalog_size=0), 0.0)

    def test_empty_recommendations(self):
        self.assertEqual(coverage([], catalog_size=10), 0.0)


# --- dataset construction ---

class BuildLOODatasetTests(SimpleTestCase):

    def test_basket_of_3_emits_3_trials(self):
        a, b, c = _uid(1), _uid(2), _uid(3)
        ds = build_loo_dataset(baskets=[[a, b, c]])
        self.assertEqual(len(ds.trials), 3)
        held_outs = {t.held_out for t in ds.trials}
        self.assertEqual(held_outs, {a, b, c})
        # Each trial's seeds = basket minus held_out
        for t in ds.trials:
            self.assertEqual(set(t.seeds) | {t.held_out}, {a, b, c})
            self.assertNotIn(t.held_out, t.seeds)

    def test_seeds_sorted_deterministic(self):
        # Input in arbitrary order → seeds always come out sorted by str(uuid)
        a, b, c = _uid(3), _uid(1), _uid(2)  # scrambled
        ds = build_loo_dataset(baskets=[[a, b, c]])
        for t in ds.trials:
            self.assertEqual(list(t.seeds), sorted(t.seeds, key=str))

    def test_singleton_basket_skipped(self):
        ds = build_loo_dataset(baskets=[[_uid(1)], [_uid(2), _uid(3)]])
        self.assertEqual(len(ds.trials), 2)  # only the pair contributes

    def test_dedup_within_basket(self):
        a, b = _uid(1), _uid(2)
        ds = build_loo_dataset(baskets=[[a, a, a, b]])
        self.assertEqual(len(ds.trials), 2)  # {a,b} → 2 LOO trials

    def test_hash_stable_across_basket_permutations(self):
        a, b, c = _uid(1), _uid(2), _uid(3)
        h1 = build_loo_dataset(baskets=[[a, b, c]]).dataset_hash
        h2 = build_loo_dataset(baskets=[[c, a, b]]).dataset_hash
        self.assertEqual(h1, h2)

    def test_hash_stable_across_basket_ordering(self):
        # Same two baskets in different list order → same hash
        b1 = [_uid(1), _uid(2)]
        b2 = [_uid(3), _uid(4)]
        h1 = build_loo_dataset(baskets=[b1, b2]).dataset_hash
        h2 = build_loo_dataset(baskets=[b2, b1]).dataset_hash
        self.assertEqual(h1, h2)

    def test_hash_differs_on_content_change(self):
        h1 = build_loo_dataset(baskets=[[_uid(1), _uid(2)]]).dataset_hash
        h2 = build_loo_dataset(baskets=[[_uid(1), _uid(3)]]).dataset_hash
        self.assertNotEqual(h1, h2)

    def test_hash_is_sha256_hex(self):
        ds = build_loo_dataset(baskets=[[_uid(1), _uid(2)]])
        self.assertEqual(len(ds.dataset_hash), 64)
        int(ds.dataset_hash, 16)  # raises if not hex

    def test_cold_tagging_below_threshold(self):
        a, b, c = _uid(1), _uid(2), _uid(3)
        # a in 3 baskets, b in 3, c in 1
        baskets = [[a, b], [a, b], [a, b, c]]
        ds = build_loo_dataset(baskets=baskets, cold_threshold=2)
        # c appears once → cold. a,b appear 3× → not cold.
        cold_held_outs = {t.held_out for t in ds.trials if t.is_cold}
        warm_held_outs = {t.held_out for t in ds.trials if not t.is_cold}
        self.assertEqual(cold_held_outs, {c})
        self.assertEqual(warm_held_outs, {a, b})

    def test_cold_threshold_boundary_inclusive(self):
        # freq == threshold → cold (≤, not <)
        a, b = _uid(1), _uid(2)
        baskets = [[a, b], [a, b]]  # both freq=2
        ds = build_loo_dataset(baskets=baskets, cold_threshold=2)
        self.assertTrue(all(t.is_cold for t in ds.trials))
        ds = build_loo_dataset(baskets=baskets, cold_threshold=1)
        self.assertTrue(all(not t.is_cold for t in ds.trials))

    def test_item_frequency_exposed(self):
        a, b, c = _uid(1), _uid(2), _uid(3)
        ds = build_loo_dataset(baskets=[[a, b], [a, c]])
        self.assertEqual(ds.item_frequency[a], 2)
        self.assertEqual(ds.item_frequency[b], 1)
        self.assertEqual(ds.item_frequency[c], 1)

    def test_empty_baskets(self):
        ds = build_loo_dataset(baskets=[])
        self.assertEqual(ds.trials, [])
        self.assertEqual(len(ds.dataset_hash), 64)  # hash of empty still well-defined


class BuildLOODatasetFromBehaviorSourcesTests(TestCase):

    def setUp(self):
        album = create_album(name='LB Album', total_tracks=2, release_date=datetime.date(2025, 1, 1))
        self.t1 = create_track(name='LB T1', album=album, track_number=1, duration_ms=1000)
        self.t2 = create_track(name='LB T2', album=album, track_number=2, duration_ms=1000)
        self.run = SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version='2026-03-22',
            raw_path='/tmp/lb.tar.gz',
            checksum='lb-checksum',
            status='succeeded',
        )

    def _mk_interaction(self, session_hint, track, signature):
        return NormalizedInteraction.objects.create(
            import_run=self.run,
            track=track,
            source_id='listenbrainz',
            source_version='2026-03-22',
            source_event_signature=signature,
            source_user_id='lb-user',
            played_at=datetime.datetime(2026, 3, 22, 12, 0, tzinfo=datetime.UTC),
            session_hint=session_hint,
            track_identifier_candidates={},
            metadata={},
        )

    def test_builds_trials_from_listenbrainz_source(self):
        self._mk_interaction('lb-session-1', self.t1, 'sig-1')
        self._mk_interaction('lb-session-1', self.t2, 'sig-2')

        ds = build_loo_dataset(sources=[BEHAVIOR_SOURCE_LISTENBRAINZ], split='all')

        self.assertEqual(len(ds.trials), 2)
        self.assertEqual({trial.held_out for trial in ds.trials}, {self.t1.juke_id, self.t2.juke_id})

    def test_default_dataset_builder_includes_listenbrainz_rows(self):
        self._mk_interaction('lb-session-default', self.t1, 'sig-default-1')
        self._mk_interaction('lb-session-default', self.t2, 'sig-default-2')

        ds = build_loo_dataset(split='all')

        self.assertEqual(len(ds.trials), 2)
        self.assertEqual({trial.held_out for trial in ds.trials}, {self.t1.juke_id, self.t2.juke_id})


# --- evaluation driver with fake ranker (no DB) ---

class _PerfectRanker:
    """Always returns the held-out item at rank 1 — cheats via closure."""
    label = 'perfect'
    def __init__(self, answers):
        self._answers = answers  # seeds-tuple → held_out
    def rank(self, seeds, exclude, limit):
        return [self._answers[seeds]]


class _UselessRanker:
    label = 'useless'
    def rank(self, seeds, exclude, limit):
        return []


class EvaluateRankerTests(SimpleTestCase):

    def _ds(self, trials):
        return Dataset(trials=trials, dataset_hash='x' * 64)

    def test_perfect_ranker_recall_and_ndcg_1(self):
        a, b = _uid(1), _uid(2)
        trials = [
            Trial(seeds=(a,), held_out=b, is_cold=False),
            Trial(seeds=(b,), held_out=a, is_cold=False),
        ]
        answers = {(a,): b, (b,): a}
        result = evaluate_ranker(_PerfectRanker(answers), self._ds(trials), k=10, catalog_size=10)
        self.assertEqual(result.metrics[METRIC_RECALL], 1.0)
        self.assertEqual(result.metrics[METRIC_NDCG], 1.0)

    def test_useless_ranker_zeros(self):
        trials = [Trial(seeds=(_uid(1),), held_out=_uid(2), is_cold=False)]
        result = evaluate_ranker(_UselessRanker(), self._ds(trials), k=10, catalog_size=10)
        self.assertEqual(result.metrics[METRIC_RECALL], 0.0)
        self.assertEqual(result.metrics[METRIC_NDCG], 0.0)
        self.assertEqual(result.metrics[METRIC_COVERAGE], 0.0)

    def test_coverage_aggregates_across_trials(self):
        a, b, c, d = [_uid(i) for i in range(1, 5)]
        trials = [
            Trial(seeds=(a,), held_out=b, is_cold=False),
            Trial(seeds=(c,), held_out=d, is_cold=False),
        ]
        answers = {(a,): b, (c,): d}  # recommends {b, d} → 2 distinct items
        result = evaluate_ranker(_PerfectRanker(answers), self._ds(trials), k=10, catalog_size=10)
        self.assertEqual(result.metrics[METRIC_COVERAGE], 0.2)

    def test_cold_recall_only_cold_trials(self):
        a, b, c, d = [_uid(i) for i in range(1, 5)]
        # Trial 1: cold, miss. Trial 2: warm, hit.
        # → overall recall = 0.5, cold_recall = 0.0
        trials = [
            Trial(seeds=(a,), held_out=b, is_cold=True),   # ranker returns d, not b
            Trial(seeds=(c,), held_out=d, is_cold=False),  # ranker returns d → hit
        ]
        answers = {(a,): d, (c,): d}
        result = evaluate_ranker(_PerfectRanker(answers), self._ds(trials), k=10, catalog_size=10)
        self.assertEqual(result.metrics[METRIC_RECALL], 0.5)
        self.assertEqual(result.metrics[METRIC_COLD_RECALL], 0.0)
        self.assertEqual(result.n_cold_trials, 1)

    def test_cold_recall_zero_when_no_cold_trials(self):
        trials = [Trial(seeds=(_uid(1),), held_out=_uid(2), is_cold=False)]
        result = evaluate_ranker(_UselessRanker(), self._ds(trials), k=10, catalog_size=10)
        self.assertEqual(result.n_cold_trials, 0)
        self.assertEqual(result.metrics[METRIC_COLD_RECALL], 0.0)  # no division error

    def test_empty_dataset(self):
        result = evaluate_ranker(_UselessRanker(), self._ds([]), k=10, catalog_size=10)
        self.assertEqual(result.n_trials, 0)
        self.assertEqual(result.metrics[METRIC_RECALL], 0.0)

    def test_result_carries_hash_and_label(self):
        trials = [Trial(seeds=(_uid(1),), held_out=_uid(2), is_cold=False)]
        ds = Dataset(trials=trials, dataset_hash='abc123' + '0' * 58)
        result = evaluate_ranker(_UselessRanker(), ds, k=10, catalog_size=10)
        self.assertEqual(result.dataset_hash, ds.dataset_hash)
        self.assertEqual(result.candidate_label, 'useless')


# --- DB-integrated: ranker adapters + persistence ---

def _mk_album(name='A'):
    return create_album(name=name, total_tracks=10, release_date=datetime.date(2020, 1, 1))


class MetadataRankerAdapterTests(TestCase):

    def test_recommends_same_artist_sibling(self):
        artist = create_artist(name='Art')
        album = _mk_album()
        album.artists.add(artist)
        t1 = create_track(name='T1', album=album, track_number=1, duration_ms=1000)
        t2 = create_track(name='T2', album=album, track_number=2, duration_ms=1000)
        t3 = create_track(name='T3', album=album, track_number=3, duration_ms=1000)

        ranker = MetadataRanker()
        ranked = ranker.rank(seeds=(t1.juke_id,), exclude={t1.juke_id}, limit=10)

        self.assertIn(t2.juke_id, ranked)
        self.assertIn(t3.juke_id, ranked)
        self.assertNotIn(t1.juke_id, ranked)

    def test_unrelated_track_not_recommended(self):
        artist_a = create_artist(name='A')
        artist_b = create_artist(name='B')
        album_a = _mk_album('AlbA')
        album_b = _mk_album('AlbB')
        album_a.artists.add(artist_a)
        album_b.artists.add(artist_b)
        ta = create_track(name='Ta', album=album_a, track_number=1, duration_ms=1000)
        tb = create_track(name='Tb', album=album_b, track_number=1, duration_ms=1000)

        ranked = MetadataRanker().rank(seeds=(ta.juke_id,), exclude={ta.juke_id}, limit=10)
        self.assertNotIn(tb.juke_id, ranked)

    def test_empty_seeds(self):
        self.assertEqual(MetadataRanker().rank(seeds=(), exclude=set(), limit=10), [])


class CoOccurrenceRankerAdapterTests(TestCase):

    def test_queries_both_orientations(self):
        # Store one pair each way so both halves of the UNION-equivalent get hit.
        # Canonical ordering is str-lex; _uid(1) < _uid(2) < _uid(3) in str form.
        seed = _uid(2)
        lo = _uid(1)  # stored as (lo, seed) → item_b match
        hi = _uid(3)  # stored as (seed, hi) → item_a match
        ItemCoOccurrence.objects.create(item_a_juke_id=lo, item_b_juke_id=seed, pmi_score=0.5, co_count=1)
        ItemCoOccurrence.objects.create(item_a_juke_id=seed, item_b_juke_id=hi, pmi_score=1.5, co_count=2)

        ranked = CoOccurrenceRanker().rank(seeds=(seed,), exclude={seed}, limit=10)
        self.assertEqual(ranked, [hi, lo])  # pmi desc

    def test_no_neighbours(self):
        self.assertEqual(CoOccurrenceRanker().rank(seeds=(_uid(1),), exclude=set(), limit=10), [])


class PersistEvaluationTests(TestCase):

    def test_writes_one_row_per_metric(self):
        from mlcore.services.evaluation import EvaluationResult
        result = EvaluationResult(
            candidate_label='metadata',
            dataset_hash='h' * 64,
            n_trials=5,
            n_cold_trials=1,
            metrics={METRIC_RECALL: 0.4, METRIC_NDCG: 0.3, METRIC_COVERAGE: 0.2, METRIC_COLD_RECALL: 0.1},
        )
        persist_evaluation(result)
        self.assertEqual(ModelEvaluation.objects.count(), 4)
        row = ModelEvaluation.objects.get(metric_name=METRIC_RECALL)
        self.assertEqual(row.candidate_label, 'metadata')
        self.assertEqual(row.dataset_hash, 'h' * 64)
        self.assertEqual(row.metric_value, 0.4)
        self.assertIsNone(row.model_id)

    def test_writes_training_run_for_cooccurrence_metrics(self):
        run = TrainingRun.objects.create(
            ranker_label='cooccurrence',
            training_hash='0' * 64,
            baskets_processed=1,
            baskets_skipped=0,
            items_seen=2,
            pairs_written=1,
            source_row_count=10,
        )
        result = EvaluationResult(
            candidate_label='cooccurrence',
            dataset_hash='x' * 64,
            n_trials=1,
            n_cold_trials=0,
            training_run=run,
            metrics={METRIC_RECALL: 1.0, METRIC_NDCG: 1.0, METRIC_COVERAGE: 0.5, METRIC_COLD_RECALL: 0.0},
        )
        persist_evaluation(result)

        row = ModelEvaluation.objects.get(candidate_label='cooccurrence', metric_name=METRIC_RECALL)
        self.assertEqual(row.training_run, run)


class RunOfflineEvaluationTests(TestCase):
    """End-to-end: SearchHistory → baskets → trials → rank → persist."""

    def setUp(self):
        self.user = User.objects.create_user(username='u', email='u@x.com', password='p')
        self.artist = create_artist(name='EndToEndArtist')
        self.album = _mk_album('EndToEndAlbum')
        self.album.artists.add(self.artist)
        self.t1 = create_track(name='E1', album=self.album, track_number=1, duration_ms=1000)
        self.t2 = create_track(name='E2', album=self.album, track_number=2, duration_ms=1000)
        self.t3 = create_track(name='E3', album=self.album, track_number=3, duration_ms=1000)

    def _session(self, tracks):
        sh = SearchHistory.objects.create(user=self.user, search_query='q')
        for t in tracks:
            SearchHistoryResource.objects.create(
                search_history=sh, resource_type='track',
                resource_id=t.pk, resource_name=t.name,
            )

    def test_metadata_perfect_recall_on_same_album(self):
        # All 3 tracks same artist+album. Each LOO trial should find the held-out
        # track in top-10 (metadata ranker returns all same-artist tracks).
        self._session([self.t1, self.t2, self.t3])
        results = run_offline_evaluation(labels=['metadata'], persist=False)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.candidate_label, 'metadata')
        self.assertEqual(r.n_trials, 3)
        self.assertEqual(r.metrics[METRIC_RECALL], 1.0)
        self.assertGreater(r.metrics[METRIC_NDCG], 0.0)
        self.assertEqual(ModelEvaluation.objects.count(), 0)  # persist=False

    def test_persists_rows(self):
        self._session([self.t1, self.t2])
        run_offline_evaluation(labels=['metadata'], persist=True)
        rows = ModelEvaluation.objects.filter(candidate_label='metadata')
        self.assertEqual(rows.count(), 4)  # 4 metrics
        # All rows share the same dataset_hash
        hashes = set(rows.values_list('dataset_hash', flat=True))
        self.assertEqual(len(hashes), 1)
        self.assertEqual(len(hashes.pop()), 64)

    def test_cooccurrence_after_training(self):
        # Two sessions so the trainer has signal.
        self._session([self.t1, self.t2])
        self._session([self.t1, self.t2, self.t3])
        train_cooccurrence()  # populate ItemCoOccurrence from the same sessions

        results = run_offline_evaluation(labels=['cooccurrence'], persist=False)
        r = results[0]
        # (t1,t2) co-occur in both baskets — strongest pair. When we hold out t2
        # with t1 as seed (or vice versa), the ranker should find it.
        self.assertGreater(r.metrics[METRIC_RECALL], 0.0)
        self.assertEqual(r.n_trials, 5)  # basket of 2 → 2 trials, basket of 3 → 3 trials

    def test_no_search_history_returns_empty(self):
        results = run_offline_evaluation(labels=['metadata'], persist=False)
        self.assertEqual(results, [])

    def test_all_rankers_share_dataset_hash(self):
        self._session([self.t1, self.t2])
        train_cooccurrence()
        results = run_offline_evaluation(persist=False)  # both rankers
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].dataset_hash, results[1].dataset_hash)

    def test_unknown_ranker_label_raises(self):
        self._session([self.t1, self.t2])
        with self.assertRaises(ValueError):
            run_offline_evaluation(labels=['nope'], persist=False)

    def test_run_offline_evaluation_forwards_split_args_to_dataset_builder(self):
        with patch('mlcore.services.evaluation.build_loo_dataset') as mock_build:
            mock_build.return_value = Dataset(trials=[], dataset_hash='x' * 64)

            results = run_offline_evaluation(
                labels=['metadata'],
                split='test',
                split_buckets=7,
                persist=False,
            )

            self.assertEqual(results, [])
            mock_build.assert_called_once_with(
                cold_threshold=DEFAULT_COLD_THRESHOLD,
                split='test',
                split_buckets=7,
            )

    def test_run_offline_evaluation_passes_explicit_cooccurrence_run(self):
        run = TrainingRun.objects.create(
            ranker_label='cooccurrence',
            training_hash='0' * 64,
            baskets_processed=1,
            baskets_skipped=0,
            items_seen=2,
            pairs_written=1,
            source_row_count=10,
        )
        trial = Trial(
            seeds=(_uid(1),),
            held_out=_uid(2),
            is_cold=False,
        )
        dataset = Dataset(trials=[trial], dataset_hash='x' * 64)

        with patch('mlcore.services.evaluation.build_loo_dataset', return_value=dataset), \
                patch('mlcore.services.evaluation.CoOccurrenceRanker') as mock_ranker_cls, \
                patch('mlcore.services.evaluation.evaluate_ranker') as mock_evaluate:
            mock_evaluate.return_value = EvaluationResult(
                candidate_label='cooccurrence',
                dataset_hash=dataset.dataset_hash,
                n_trials=1,
                n_cold_trials=0,
                training_run=run,
                metrics={METRIC_RECALL: 0.0, METRIC_NDCG: 0.0, METRIC_COVERAGE: 0.0, METRIC_COLD_RECALL: 0.0},
            )

            results = run_offline_evaluation(
                labels=['cooccurrence'],
                split='test',
                cooccurrence_training_run=run,
                persist=False,
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].training_run, run)
            mock_ranker_cls.assert_called_once_with(run)

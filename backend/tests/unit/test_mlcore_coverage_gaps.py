"""
Targeted tests filling branch-level gaps identified in the Stage 6 audit:

  - management commands (call_command)
  - Celery task wrapper
  - WRITE_BATCH_SIZE chunking (second iteration of the write loop)
  - evaluate_ranker() catalog_size=None auto-count path
  - _track_feature_rows() M2M cross-product (multi-artist, multi-genre)
  - _latest_shared_dataset_hash() picks most recent when multiple overlap
  - baskets_from_search_history() unsupported resource_type ValueError
"""
import datetime
import uuid
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from catalog.models import SearchHistory, SearchHistoryResource
from mlcore.models import ItemCoOccurrence, ModelEvaluation, ModelPromotion, NormalizedInteraction, SourceIngestionRun
from mlcore.services.cooccurrence import (
    BEHAVIOR_SOURCE_LISTENBRAINZ,
    BEHAVIOR_SOURCE_SEARCH_HISTORY,
    baskets_from_search_history,
    train_cooccurrence,
)
from mlcore.services.evaluation import (
    METRIC_RECALL,
    MetadataRanker,
    Trial,
    Dataset,
    _track_feature_rows,
    evaluate_ranker,
)
from mlcore.services.promotion import _latest_shared_dataset_hash
from mlcore.tasks import train_cooccurrence_task
from tests.utils import create_album, create_artist, create_genre, create_track

User = get_user_model()


def _mk_album(name='A'):
    return create_album(name=name, total_tracks=10, release_date=datetime.date(2020, 1, 1))


# --- WRITE_BATCH_SIZE chunking ---

class BatchWriteTests(TestCase):

    def test_chunked_bulk_create_writes_all_rows(self):
        """
        Patch WRITE_BATCH_SIZE small so the for-loop at cooccurrence.py:156
        actually iterates. Single basket of 5 items → C(5,2) = 10 pairs
        → with batch_size=3: 4 bulk_create calls (3+3+3+1).
        """
        ids = [uuid.UUID(int=i) for i in range(1, 6)]
        with patch('mlcore.services.cooccurrence.WRITE_BATCH_SIZE', 3):
            result = train_cooccurrence(baskets=[ids])
        self.assertEqual(result.pairs_written, 10)
        self.assertEqual(ItemCoOccurrence.objects.count(), 10)
        # Every pair got a real PMI (single basket → all PMI = log2(1) = 0)
        for row in ItemCoOccurrence.objects.all():
            self.assertEqual(row.co_count, 1)
            self.assertEqual(row.pmi_score, 0.0)


# --- Celery task wrapper ---

class CeleryTaskTests(TestCase):

    def test_task_wraps_trainer_and_returns_dict(self):
        # .apply() runs synchronously in-process, no broker needed.
        # Empty DB → no baskets → pairs_written=0, but task still returns the shape.
        result = train_cooccurrence_task.apply().get()
        self.assertEqual(result['split'], 'train')
        self.assertEqual(result['split_buckets'], 10)
        self.assertEqual(result['sources'], [BEHAVIOR_SOURCE_SEARCH_HISTORY, BEHAVIOR_SOURCE_LISTENBRAINZ])
        self.assertEqual(result['pairs_written'], 0)
        self.assertEqual(result['baskets_processed'], 0)
        self.assertEqual(result['baskets_skipped'], 0)
        self.assertEqual(result['items_seen'], 0)
        self.assertEqual(result['source_row_count'], 0)

    def test_task_with_real_baskets(self):
        user = User.objects.create_user(username='u', email='u@x.com', password='p')
        album = _mk_album()
        t1 = create_track(name='T1', album=album, track_number=1, duration_ms=1000)
        t2 = create_track(name='T2', album=album, track_number=2, duration_ms=1000)
        sh = SearchHistory.objects.create(user=user, search_query='q')
        for t in (t1, t2):
            SearchHistoryResource.objects.create(
                search_history=sh, resource_type='track',
                resource_id=t.pk, resource_name=t.name,
            )
        result = train_cooccurrence_task.apply().get()
        self.assertEqual(result['pairs_written'], 1)
        self.assertEqual(result['baskets_processed'], 1)
        self.assertEqual(ItemCoOccurrence.objects.count(), 1)

    def test_task_accepts_explicit_sources(self):
        album = _mk_album()
        t1 = create_track(name='LT1', album=album, track_number=1, duration_ms=1000)
        t2 = create_track(name='LT2', album=album, track_number=2, duration_ms=1000)
        run = SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version='2026-03-22',
            raw_path='/tmp/listenbrainz.tar.gz',
            checksum='listenbrainz',
            status='succeeded',
        )
        for idx, track in enumerate((t1, t2), start=1):
            NormalizedInteraction.objects.create(
                import_run=run,
                track=track,
                source_id='listenbrainz',
                source_version='2026-03-22',
                source_event_signature=f'sig-{idx}',
                source_user_id='lb-user',
                played_at=datetime.datetime(2026, 3, 22, 12, idx, tzinfo=datetime.UTC),
                session_hint='lb-session',
                track_identifier_candidates={},
                metadata={},
            )

        result = train_cooccurrence_task.apply(kwargs={'split': 'all', 'sources': [BEHAVIOR_SOURCE_LISTENBRAINZ]}).get()

        self.assertEqual(result['split'], 'all')
        self.assertEqual(result['sources'], [BEHAVIOR_SOURCE_LISTENBRAINZ])
        self.assertEqual(result['pairs_written'], 1)
        self.assertEqual(result['source_row_count'], 2)

    def test_task_defaults_to_blended_sources(self):
        user = User.objects.create_user(username='blend', email='blend@x.com', password='p')
        album = _mk_album('Blend')
        t1 = create_track(name='BT1', album=album, track_number=1, duration_ms=1000)
        t2 = create_track(name='BT2', album=album, track_number=2, duration_ms=1000)
        t3 = create_track(name='BT3', album=album, track_number=3, duration_ms=1000)

        sh = SearchHistory.objects.create(user=user, search_query='blend')
        for track in (t1, t2):
            SearchHistoryResource.objects.create(
                search_history=sh, resource_type='track',
                resource_id=track.pk, resource_name=track.name,
            )

        run = SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version='2026-03-22',
            raw_path='/tmp/listenbrainz.tar.gz',
            checksum='listenbrainz-blend',
            status='succeeded',
        )
        for idx, track in enumerate((t2, t3), start=1):
            NormalizedInteraction.objects.create(
                import_run=run,
                track=track,
                source_id='listenbrainz',
                source_version='2026-03-22',
                source_event_signature=f'blend-sig-{idx}',
                source_user_id='lb-user',
                played_at=datetime.datetime(2026, 3, 22, 14, idx, tzinfo=datetime.UTC),
                session_hint='lb-default-blend',
                track_identifier_candidates={},
                metadata={},
            )

        result = train_cooccurrence_task.apply(kwargs={'split': 'all'}).get()

        self.assertEqual(result['sources'], [BEHAVIOR_SOURCE_SEARCH_HISTORY, BEHAVIOR_SOURCE_LISTENBRAINZ])
        self.assertEqual(result['baskets_processed'], 2)
        self.assertEqual(result['pairs_written'], 2)
        self.assertEqual(result['source_row_count'], 4)


# --- evaluate_ranker auto catalog_size ---

class AutoCatalogSizeTests(TestCase):

    def test_catalog_size_none_counts_tracks(self):
        album = _mk_album()
        for i in range(4):
            create_track(name=f'T{i}', album=album, track_number=i + 1, duration_ms=1000)

        # Ranker that returns one fixed juke_id regardless of seeds
        class _OneRanker:
            label = 'one'
            def rank(self, seeds, exclude, limit):
                return [uuid.UUID(int=999)]

        trials = [Trial(seeds=(uuid.UUID(int=1),), held_out=uuid.UUID(int=2), is_cold=False)]
        ds = Dataset(trials=trials, dataset_hash='x' * 64)
        # catalog_size=None → Track.objects.count() = 4 → coverage = 1/4
        result = evaluate_ranker(_OneRanker(), ds, k=10, catalog_size=None)
        self.assertEqual(result.metrics['coverage'], 0.25)


# --- M2M cross-product in ORM feature fetch ---

class TrackFeatureRowsM2MTests(TestCase):

    def test_multi_artist_album_emits_multiple_rows(self):
        """
        Album with 2 artists → _track_feature_rows() emits 2 rows for one
        track (one per artist). Mirrors the engine's LEFT JOIN cross-product.
        """
        artist_a = create_artist(name='A')
        artist_b = create_artist(name='B')
        album = _mk_album()
        album.artists.add(artist_a, artist_b)
        t = create_track(name='T', album=album, track_number=1, duration_ms=1000)

        rows = _track_feature_rows([t.juke_id])
        artist_ids = {r['artist_id'] for r in rows}
        self.assertEqual(artist_ids, {artist_a.pk, artist_b.pk})
        # All rows for same track → same juke_id, same album_id
        self.assertEqual({r['juke_id'] for r in rows}, {t.juke_id})
        self.assertEqual({r['album_id'] for r in rows}, {album.pk})

    def test_multi_genre_artist_emits_multiple_rows(self):
        jazz = create_genre(name='jazz')
        funk = create_genre(name='funk')
        artist = create_artist(name='A')
        artist.genres.add(jazz, funk)
        album = _mk_album()
        album.artists.add(artist)
        t = create_track(name='T', album=album, track_number=1, duration_ms=1000)

        rows = _track_feature_rows([t.juke_id])
        genre_ids = {r['genre_id'] for r in rows}
        self.assertEqual(genre_ids, {jazz.pk, funk.pk})

    def test_no_artist_linkage_single_row_nulls(self):
        # Album with no artists → LEFT JOIN yields nulls
        album = _mk_album()
        t = create_track(name='T', album=album, track_number=1, duration_ms=1000)
        rows = _track_feature_rows([t.juke_id])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['album_id'], album.pk)
        self.assertIsNone(rows[0]['artist_id'])
        self.assertIsNone(rows[0]['genre_id'])

    def test_metadata_ranker_uses_cross_product(self):
        """
        End-to-end: seed track's album has artist A; candidate track's album
        has artists A and B. The candidate should be recommended via the
        shared artist A even though artist B is noise.
        """
        artist_shared = create_artist(name='Shared')
        artist_other = create_artist(name='Other')
        alb_seed = _mk_album('Seed')
        alb_cand = _mk_album('Cand')
        alb_seed.artists.add(artist_shared)
        alb_cand.artists.add(artist_shared, artist_other)  # multi-artist
        t_seed = create_track(name='S', album=alb_seed, track_number=1, duration_ms=1000)
        t_cand = create_track(name='C', album=alb_cand, track_number=1, duration_ms=1000)

        ranked = MetadataRanker().rank(seeds=(t_seed.juke_id,), exclude={t_seed.juke_id}, limit=10)
        self.assertIn(t_cand.juke_id, ranked)


# --- _latest_shared_dataset_hash most-recent semantics ---

class LatestSharedHashMostRecentTests(TestCase):

    def test_picks_most_recent_baseline_hash_among_shared(self):
        # Both labels evaluated on hash A (older) and hash B (newer).
        # The baseline-side newest shared row determines the pick.
        for h in ('a' * 64, 'b' * 64):
            for label in ('cand', 'base'):
                ModelEvaluation.objects.create(
                    candidate_label=label, metric_name=METRIC_RECALL,
                    metric_value=0.5, dataset_hash=h,
                )
        # Insertion order → 'b'*64 rows have later created_at
        self.assertEqual(_latest_shared_dataset_hash('cand', 'base'), 'b' * 64)


# --- unsupported resource_type ---

class BasketsResourceTypeTests(TestCase):

    def test_non_track_type_raises_when_rows_exist(self):
        # ValueError only fires when there ARE rows (after the all_pks guard).
        user = User.objects.create_user(username='u', email='u@x.com', password='p')
        sh = SearchHistory.objects.create(user=user, search_query='q')
        SearchHistoryResource.objects.create(
            search_history=sh, resource_type='artist', resource_id=1, resource_name='x',
        )
        with self.assertRaises(ValueError) as ctx:
            baskets_from_search_history(resource_type='artist')
        self.assertIn('Phase 1', str(ctx.exception))

    def test_non_track_type_empty_returns_empty(self):
        # No rows → short-circuits before the type check
        self.assertEqual(baskets_from_search_history(resource_type='artist'), [])


# --- management command smoke tests ---

class EvaluateRecommendersCommandTests(TestCase):

    def test_no_trials_warning(self):
        out = StringIO()
        call_command('evaluate_recommenders', '--no-persist', stdout=out)
        self.assertIn('No trials generated', out.getvalue())
        self.assertEqual(ModelEvaluation.objects.count(), 0)

    def test_runs_and_persists(self):
        user = User.objects.create_user(username='u', email='u@x.com', password='p')
        artist = create_artist(name='A')
        album = _mk_album()
        album.artists.add(artist)
        t1 = create_track(name='T1', album=album, track_number=1, duration_ms=1000)
        t2 = create_track(name='T2', album=album, track_number=2, duration_ms=1000)
        for _ in range(10):
            sh = SearchHistory.objects.create(user=user, search_query='q')
            for t in (t1, t2):
                SearchHistoryResource.objects.create(
                    search_history=sh, resource_type='track',
                    resource_id=t.pk, resource_name=t.name,
                )

        out = StringIO()
        call_command('evaluate_recommenders', '--ranker', 'metadata', stdout=out)
        output = out.getvalue()
        self.assertIn('metadata:', output)
        self.assertIn('trials=2', output)
        self.assertIn('recall@10', output)
        self.assertEqual(ModelEvaluation.objects.filter(candidate_label='metadata').count(), 4)


class TrainCooccurrenceCommandTests(TestCase):

    def test_rejects_invalid_split_bucket_count(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('train_cooccurrence', '--split-buckets', '0')
        self.assertIn('--split-buckets must be > 0', str(ctx.exception))

    def test_trains_from_listenbrainz_source(self):
        album = _mk_album()
        t1 = create_track(name='LT1', album=album, track_number=1, duration_ms=1000)
        t2 = create_track(name='LT2', album=album, track_number=2, duration_ms=1000)
        run = SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version='2026-03-22',
            raw_path='/tmp/listenbrainz.tar.gz',
            checksum='listenbrainz',
            status='succeeded',
        )
        for idx, track in enumerate((t1, t2), start=1):
            NormalizedInteraction.objects.create(
                import_run=run,
                track=track,
                source_id='listenbrainz',
                source_version='2026-03-22',
                source_event_signature=f'cmd-sig-{idx}',
                source_user_id='lb-user',
                played_at=datetime.datetime(2026, 3, 22, 13, idx, tzinfo=datetime.UTC),
                session_hint='lb-command-session',
                track_identifier_candidates={},
                metadata={},
            )

        out = StringIO()
        call_command('train_cooccurrence', '--split', 'all', '--source', 'listenbrainz', stdout=out)

        output = out.getvalue()
        self.assertIn('cooccurrence trained:', output)
        self.assertIn('sources=listenbrainz', output)
        self.assertEqual(ItemCoOccurrence.objects.count(), 1)

    def test_default_command_uses_blended_sources(self):
        user = User.objects.create_user(username='blend-cmd', email='blend-cmd@x.com', password='p')
        album = _mk_album('Blend Command')
        t1 = create_track(name='CT1', album=album, track_number=1, duration_ms=1000)
        t2 = create_track(name='CT2', album=album, track_number=2, duration_ms=1000)
        t3 = create_track(name='CT3', album=album, track_number=3, duration_ms=1000)

        sh = SearchHistory.objects.create(user=user, search_query='blend')
        for track in (t1, t2):
            SearchHistoryResource.objects.create(
                search_history=sh, resource_type='track',
                resource_id=track.pk, resource_name=track.name,
            )

        run = SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version='2026-03-22',
            raw_path='/tmp/listenbrainz.tar.gz',
            checksum='listenbrainz-command-blend',
            status='succeeded',
        )
        for idx, track in enumerate((t2, t3), start=1):
            NormalizedInteraction.objects.create(
                import_run=run,
                track=track,
                source_id='listenbrainz',
                source_version='2026-03-22',
                source_event_signature=f'cmd-blend-sig-{idx}',
                source_user_id='lb-user',
                played_at=datetime.datetime(2026, 3, 22, 15, idx, tzinfo=datetime.UTC),
                session_hint='lb-command-default',
                track_identifier_candidates={},
                metadata={},
            )

        out = StringIO()
        call_command('train_cooccurrence', '--split', 'all', stdout=out)

        output = out.getvalue()
        self.assertIn('sources=search_history,listenbrainz', output)
        self.assertEqual(ItemCoOccurrence.objects.count(), 2)


@override_settings(
    JUKE_PROMOTION_GATE_NDCG_MIN_LIFT=0.05,
    JUKE_PROMOTION_GATE_RECALL_MIN_LIFT=0.03,
    JUKE_PROMOTION_GATE_COLDSTART_MAX_REGRESSION=0.02,
    JUKE_PROMOTION_GATE_COVERAGE_MIN=0.30,
)
class PromoteRecommenderCommandTests(TestCase):

    def _seed(self, label, h, **metrics):
        from mlcore.services.evaluation import (METRIC_COLD_RECALL, METRIC_COVERAGE,
                                                METRIC_NDCG, METRIC_RECALL)
        for name, val in [(METRIC_RECALL, metrics['recall']), (METRIC_NDCG, metrics['ndcg']),
                          (METRIC_COVERAGE, metrics['coverage']), (METRIC_COLD_RECALL, metrics['cold'])]:
            ModelEvaluation.objects.create(candidate_label=label, metric_name=name,
                                           metric_value=val, dataset_hash=h)

    def test_dry_run_requires_hash(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('promote_recommender', '--candidate', 'c', '--baseline', 'b')
        self.assertIn('--dataset-hash', str(ctx.exception))

    def test_dry_run_prints_gates_no_write(self):
        h = 'a' * 64
        self._seed('base', h, recall=0.4, ndcg=0.3, coverage=0.1, cold=0.2)
        self._seed('cand', h, recall=0.5, ndcg=0.4, coverage=0.5, cold=0.2)
        out = StringIO()
        call_command('promote_recommender', '--candidate', 'cand', '--baseline', 'base',
                     '--dataset-hash', h, stdout=out)
        output = out.getvalue()
        self.assertIn('PASS', output)
        self.assertIn('ndcg_lift', output)
        self.assertEqual(ModelPromotion.objects.count(), 0)

    def test_request_creates_row(self):
        h = 'a' * 64
        self._seed('base', h, recall=0.4, ndcg=0.3, coverage=0.1, cold=0.2)
        self._seed('cand', h, recall=0.5, ndcg=0.4, coverage=0.5, cold=0.2)
        out = StringIO()
        call_command('promote_recommender', '--candidate', 'cand', '--baseline', 'base',
                     '--request', stdout=out)
        self.assertIn('status=pending', out.getvalue())
        self.assertEqual(ModelPromotion.objects.filter(status='pending').count(), 1)

    def test_request_blocked_shows_reason(self):
        h = 'a' * 64
        self._seed('base', h, recall=0.4, ndcg=0.3, coverage=0.1, cold=0.2)
        self._seed('cand', h, recall=0.3, ndcg=0.2, coverage=0.1, cold=0.1)  # worse
        out = StringIO()
        call_command('promote_recommender', '--candidate', 'cand', '--baseline', 'base',
                     '--request', stdout=out)
        output = out.getvalue()
        self.assertIn('BLOCKED', output)
        self.assertIn('FAIL', output)
        self.assertEqual(ModelPromotion.objects.filter(status='blocked').count(), 1)

    def test_approve_requires_approver(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('promote_recommender', '--candidate', 'c', '--baseline', 'b', '--approve')
        self.assertIn('--approver', str(ctx.exception))

    def test_approve_unknown_user(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('promote_recommender', '--candidate', 'c', '--baseline', 'b',
                         '--approve', '--approver', 'ghost')
        self.assertIn('not found', str(ctx.exception))

    def test_approve_full_flow(self):
        User.objects.create_user(username='boss', email='b@x.com', password='p', is_staff=True)
        h = 'a' * 64
        self._seed('base', h, recall=0.4, ndcg=0.3, coverage=0.1, cold=0.2)
        self._seed('cand', h, recall=0.5, ndcg=0.4, coverage=0.5, cold=0.2)
        out = StringIO()
        call_command('promote_recommender', '--candidate', 'cand', '--baseline', 'base',
                     '--approve', '--approver', 'boss', stdout=out)
        self.assertIn('APPROVED by boss', out.getvalue())
        promo = ModelPromotion.objects.get()
        self.assertEqual(promo.status, 'approved')
        self.assertEqual(promo.approved_by.username, 'boss')

    def test_no_shared_hash_command_error(self):
        with self.assertRaises(CommandError) as ctx:
            call_command('promote_recommender', '--candidate', 'c', '--baseline', 'b', '--request')
        self.assertIn('no shared evaluation dataset', str(ctx.exception))

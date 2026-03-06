import datetime
import math
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase

from catalog.models import SearchHistory, SearchHistoryResource
from mlcore.models import ItemCoOccurrence
from mlcore.services.cooccurrence import (
    _canonical_pair,
    baskets_from_search_history,
    compute_pmi_table,
    train_cooccurrence,
)
from tests.utils import create_album, create_track

User = get_user_model()


# --- Pure-function PMI math (no DB) ---

class CanonicalPairTests(TestCase):

    def test_orders_lexicographically(self):
        a = uuid.UUID('00000000-0000-0000-0000-000000000001')
        b = uuid.UUID('00000000-0000-0000-0000-000000000002')
        self.assertEqual(_canonical_pair(a, b), (a, b))
        self.assertEqual(_canonical_pair(b, a), (a, b))

    def test_same_uuid_stable(self):
        a = uuid.uuid4()
        self.assertEqual(_canonical_pair(a, a), (a, a))


class ComputePMITableTests(TestCase):

    def _ids(self, n):
        return [uuid.UUID(int=i) for i in range(1, n + 1)]

    def test_single_basket_two_items(self):
        a, b = self._ids(2)
        table, result = compute_pmi_table([[a, b]])
        self.assertEqual(result.baskets_processed, 1)
        self.assertEqual(result.items_seen, 2)
        self.assertEqual(result.pairs_written, 1)
        # N=1; P(a,b)=1/1=1; P(a)=P(b)=1 → PMI=log2(1)=0
        # (Two items that only exist in one shared basket carry no surprise.)
        (co, pmi), = table.values()
        self.assertEqual(co, 1)
        self.assertAlmostEqual(pmi, 0.0)

    def test_strong_vs_weak_association(self):
        # a,b co-occur often relative to their marginals; a,c only once despite
        # both a and c being common individually → (a,b) PMI > (a,c) PMI.
        a, b, c, d = self._ids(4)
        baskets = [
            [a, b],       # a,b together
            [a, b],       # a,b together
            [a, c],       # a,c together once
            [c, d],       # c appears without a
            [c, d],       # c appears without a
        ]
        table, _ = compute_pmi_table(baskets)
        co_ab, pmi_ab = table[_canonical_pair(a, b)]
        co_ac, pmi_ac = table[_canonical_pair(a, c)]
        self.assertEqual(co_ab, 2)
        self.assertEqual(co_ac, 1)
        # N=5; (a,b): P=2/5, Pa=3/5, Pb=2/5 → PMI=log2((2/5)/(6/25))=log2(5/3)≈0.737
        # (a,c): P=1/5, Pa=3/5, Pc=3/5 → PMI=log2((1/5)/(9/25))=log2(5/9)≈-0.848
        self.assertAlmostEqual(pmi_ab, math.log2(5 / 3), places=6)
        self.assertAlmostEqual(pmi_ac, math.log2(5 / 9), places=6)
        self.assertGreater(pmi_ab, pmi_ac)
        self.assertGreater(pmi_ab, 0)  # positive = more-than-chance
        self.assertLess(pmi_ac, 0)     # negative = less-than-chance

    def test_never_cooccur_not_stored(self):
        # a and b never share a basket → pair not in output (co_count=0 never written)
        a, b, c, d = self._ids(4)
        baskets = [[a, c], [a, d], [b, c], [b, d]]
        table, _ = compute_pmi_table(baskets)
        self.assertNotIn(_canonical_pair(a, b), table)
        # (a,c) does exist: N=4, P(ac)=1/4, Pa=2/4, Pc=2/4 → PMI=log2(1)=0
        _, pmi_ac = table[_canonical_pair(a, c)]
        self.assertAlmostEqual(pmi_ac, 0.0, places=6)

    def test_basket_below_min_size_skipped(self):
        a, b = self._ids(2)
        table, result = compute_pmi_table([[a], [a, b]])
        self.assertEqual(result.baskets_processed, 1)
        self.assertEqual(result.baskets_skipped, 1)

    def test_duplicate_items_in_basket_deduplicated(self):
        a, b = self._ids(2)
        table, result = compute_pmi_table([[a, a, a, b]])
        # Dedup → {a, b}, one pair
        self.assertEqual(result.items_seen, 2)
        self.assertEqual(result.pairs_written, 1)
        (co, _), = table.values()
        self.assertEqual(co, 1)

    def test_empty_input(self):
        table, result = compute_pmi_table([])
        self.assertEqual(table, {})
        self.assertEqual(result.baskets_processed, 0)
        self.assertEqual(result.pairs_written, 0)

    def test_three_item_basket_emits_three_pairs(self):
        a, b, c = self._ids(3)
        table, result = compute_pmi_table([[a, b, c]])
        self.assertEqual(result.pairs_written, 3)  # C(3,2)
        self.assertIn(_canonical_pair(a, b), table)
        self.assertIn(_canonical_pair(a, c), table)
        self.assertIn(_canonical_pair(b, c), table)


# --- DB-integrated trainer ---

def _mk_album():
    return create_album(name='A', total_tracks=10, release_date=datetime.date(2020, 1, 1))


class TrainCoOccurrenceTests(TestCase):

    def test_writes_rows_to_table(self):
        a, b, c = self._ids(3)
        result = train_cooccurrence(baskets=[[a, b], [a, c]])
        self.assertEqual(result.pairs_written, 2)
        self.assertEqual(ItemCoOccurrence.objects.count(), 2)

    def test_idempotent_rerun_updates_not_duplicates(self):
        a, b, c = self._ids(3)
        train_cooccurrence(baskets=[[a, b]])
        self.assertEqual(ItemCoOccurrence.objects.count(), 1)
        row1 = ItemCoOccurrence.objects.get()
        self.assertEqual(row1.co_count, 1)

        # Re-run with more data where a,b co-occur more AND a also appears
        # with c. Should update the (a,b) row, add an (a,c) row.
        train_cooccurrence(baskets=[[a, b], [a, b], [a, c]])
        self.assertEqual(ItemCoOccurrence.objects.count(), 2)
        row2 = ItemCoOccurrence.objects.get(
            item_a_juke_id=row1.item_a_juke_id,
            item_b_juke_id=row1.item_b_juke_id,
        )
        self.assertEqual(row2.co_count, 2)  # overwritten, not incremented
        self.assertEqual(row2.pk, row1.pk)  # same row

    def test_canonical_storage_single_row_per_pair(self):
        a, b = self._ids(2)
        # Feed pairs in both orderings — still one row
        train_cooccurrence(baskets=[[a, b], [b, a]])
        self.assertEqual(ItemCoOccurrence.objects.count(), 1)
        row = ItemCoOccurrence.objects.get()
        self.assertEqual(str(row.item_a_juke_id), str(min(a, b, key=str)))
        self.assertEqual(row.co_count, 2)

    def test_empty_baskets_no_rows(self):
        result = train_cooccurrence(baskets=[])
        self.assertEqual(result.pairs_written, 0)
        self.assertEqual(ItemCoOccurrence.objects.count(), 0)

    def _ids(self, n):
        return [uuid.UUID(int=i) for i in range(1, n + 1)]


class BasketsFromSearchHistoryTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='u', email='u@x.com', password='p')
        self.album = _mk_album()
        self.t1 = create_track(name='T1', album=self.album, track_number=1, duration_ms=1000)
        self.t2 = create_track(name='T2', album=self.album, track_number=2, duration_ms=1000)
        self.t3 = create_track(name='T3', album=self.album, track_number=3, duration_ms=1000)

    def _mk_session(self, tracks):
        sh = SearchHistory.objects.create(user=self.user, search_query='q')
        for t in tracks:
            SearchHistoryResource.objects.create(
                search_history=sh, resource_type='track',
                resource_id=t.pk, resource_name=t.name,
            )
        return sh

    def test_extracts_baskets_grouped_by_session(self):
        self._mk_session([self.t1, self.t2])
        self._mk_session([self.t2, self.t3])
        baskets = baskets_from_search_history()
        self.assertEqual(len(baskets), 2)
        # Each basket contains juke_ids (UUIDs), not PKs
        all_ids = {jid for basket in baskets for jid in basket}
        self.assertIn(self.t1.juke_id, all_ids)
        self.assertIn(self.t2.juke_id, all_ids)
        self.assertIn(self.t3.juke_id, all_ids)

    def test_skips_sessions_below_min_size(self):
        self._mk_session([self.t1])          # singleton — skip
        self._mk_session([self.t2, self.t3]) # keep
        baskets = baskets_from_search_history()
        self.assertEqual(len(baskets), 1)

    def test_skips_dangling_resource_ids(self):
        # Session references a track PK that doesn't exist → filtered out
        sh = SearchHistory.objects.create(user=self.user, search_query='q')
        SearchHistoryResource.objects.create(
            search_history=sh, resource_type='track',
            resource_id=999999, resource_name='ghost',
        )
        SearchHistoryResource.objects.create(
            search_history=sh, resource_type='track',
            resource_id=self.t1.pk, resource_name=self.t1.name,
        )
        # After filtering the dangling PK, basket is size 1 → below min → excluded
        baskets = baskets_from_search_history()
        self.assertEqual(baskets, [])

    def test_ignores_non_track_resources(self):
        sh = SearchHistory.objects.create(user=self.user, search_query='q')
        SearchHistoryResource.objects.create(
            search_history=sh, resource_type='artist', resource_id=1, resource_name='x',
        )
        SearchHistoryResource.objects.create(
            search_history=sh, resource_type='track',
            resource_id=self.t1.pk, resource_name=self.t1.name,
        )
        SearchHistoryResource.objects.create(
            search_history=sh, resource_type='track',
            resource_id=self.t2.pk, resource_name=self.t2.name,
        )
        baskets = baskets_from_search_history()
        self.assertEqual(len(baskets), 1)
        self.assertEqual(len(baskets[0]), 2)  # only the two tracks

    def test_empty_history(self):
        self.assertEqual(baskets_from_search_history(), [])

    def test_end_to_end_train_from_history(self):
        self._mk_session([self.t1, self.t2])
        self._mk_session([self.t1, self.t2, self.t3])
        result = train_cooccurrence()  # no explicit baskets → pulls from history
        self.assertEqual(result.baskets_processed, 2)
        self.assertEqual(result.pairs_written, 3)  # (t1,t2), (t1,t3), (t2,t3)
        # t1,t2 co-occur twice; others once
        pair_12 = ItemCoOccurrence.objects.get(
            item_a_juke_id=min(self.t1.juke_id, self.t2.juke_id, key=str),
            item_b_juke_id=max(self.t1.juke_id, self.t2.juke_id, key=str),
        )
        self.assertEqual(pair_12.co_count, 2)

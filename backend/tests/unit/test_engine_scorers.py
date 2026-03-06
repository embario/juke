"""
Tests for recommender_engine/app/scorers.py — the pure scoring logic behind
/engine/recommend/metadata and /engine/recommend/cooccurrence.

scorers.py has zero third-party deps, so it's importable here even though
the engine container's fastapi/numpy aren't in the backend image.
"""
import uuid

from django.test import SimpleTestCase

from recommender_engine.app.scorers import (
    W_SAME_ALBUM,
    W_SAME_ARTIST,
    W_SHARED_GENRE,
    ScoredItem,
    extract_seed_feature_ids,
    score_cooccurrence,
    score_metadata,
)


def _uid(i):
    return uuid.UUID(int=i)


def _row(jid, album=None, artist=None, genre=None):
    return {'juke_id': jid, 'album_id': album, 'artist_id': artist, 'genre_id': genre}


# --- metadata scorer ---

class ScoreMetadataTests(SimpleTestCase):

    def test_same_artist_scores_1_0(self):
        seed = _uid(1)
        cand = _uid(2)
        seed_rows = [_row(seed, album=10, artist=100)]
        cand_rows = [_row(cand, album=99, artist=100)]  # different album, same artist
        items = score_metadata(seed_rows, cand_rows, exclude={seed}, limit=10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].juke_id, cand)
        self.assertEqual(items[0].score, W_SAME_ARTIST)
        self.assertEqual(items[0].components['same_artist'], W_SAME_ARTIST)
        self.assertEqual(items[0].components['same_album'], 0.0)

    def test_same_album_scores_0_8(self):
        seed = _uid(1)
        cand = _uid(2)
        # Same album but no artist row (artist_id=None simulates NULL join)
        seed_rows = [_row(seed, album=10, artist=None)]
        cand_rows = [_row(cand, album=10, artist=None)]
        items = score_metadata(seed_rows, cand_rows, exclude={seed}, limit=10)
        self.assertEqual(items[0].score, W_SAME_ALBUM)
        self.assertEqual(items[0].components['same_album'], W_SAME_ALBUM)

    def test_shared_genre_scores_0_5(self):
        seed = _uid(1)
        cand = _uid(2)
        seed_rows = [_row(seed, album=10, artist=100, genre=1000)]
        cand_rows = [_row(cand, album=99, artist=999, genre=1000)]  # only genre overlaps
        items = score_metadata(seed_rows, cand_rows, exclude={seed}, limit=10)
        self.assertEqual(items[0].score, W_SHARED_GENRE)

    def test_max_aggregation_artist_beats_genre(self):
        # Candidate shares both artist AND genre with seed → score is max = artist (1.0)
        seed = _uid(1)
        cand = _uid(2)
        seed_rows = [_row(seed, album=10, artist=100, genre=1000)]
        cand_rows = [_row(cand, album=99, artist=100, genre=1000)]
        items = score_metadata(seed_rows, cand_rows, exclude={seed}, limit=10)
        self.assertEqual(items[0].score, W_SAME_ARTIST)
        # Both components present in breakdown
        self.assertEqual(items[0].components['same_artist'], W_SAME_ARTIST)
        self.assertEqual(items[0].components['shared_genre'], W_SHARED_GENRE)

    def test_seeds_excluded_from_results(self):
        seed = _uid(1)
        seed_rows = [_row(seed, album=10, artist=100)]
        # Candidate rows include the seed itself (query would return it — same album)
        cand_rows = [_row(seed, album=10, artist=100), _row(_uid(2), album=10, artist=100)]
        items = score_metadata(seed_rows, cand_rows, exclude={seed}, limit=10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].juke_id, _uid(2))

    def test_explicit_exclude_ids_respected(self):
        seed = _uid(1)
        blocked = _uid(2)
        allowed = _uid(3)
        seed_rows = [_row(seed, artist=100)]
        cand_rows = [_row(blocked, artist=100), _row(allowed, artist=100)]
        items = score_metadata(seed_rows, cand_rows, exclude={seed, blocked}, limit=10)
        self.assertEqual([i.juke_id for i in items], [allowed])

    def test_deterministic_tie_break_by_juke_id(self):
        seed = _uid(1)
        # Two candidates with identical score → lower juke_id first
        c_low = _uid(2)
        c_high = _uid(3)
        seed_rows = [_row(seed, artist=100)]
        cand_rows = [_row(c_high, artist=100), _row(c_low, artist=100)]  # reversed input order
        items = score_metadata(seed_rows, cand_rows, exclude={seed}, limit=10)
        self.assertEqual([i.juke_id for i in items], [c_low, c_high])

    def test_limit_respected(self):
        seed = _uid(1)
        seed_rows = [_row(seed, artist=100)]
        cand_rows = [_row(_uid(i), artist=100) for i in range(2, 20)]
        items = score_metadata(seed_rows, cand_rows, exclude={seed}, limit=5)
        self.assertEqual(len(items), 5)

    def test_multi_row_candidate_features_union(self):
        # Track with two artists (M2M cross-product) — two rows, one juke_id.
        # Only the second artist matches seed → still scores.
        seed = _uid(1)
        cand = _uid(2)
        seed_rows = [_row(seed, artist=100)]
        cand_rows = [
            _row(cand, artist=999),  # no match
            _row(cand, artist=100),  # match
        ]
        items = score_metadata(seed_rows, cand_rows, exclude={seed}, limit=10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].score, W_SAME_ARTIST)

    def test_no_overlap_empty_result(self):
        seed_rows = [_row(_uid(1), album=10, artist=100, genre=1000)]
        cand_rows = [_row(_uid(2), album=99, artist=999, genre=9999)]
        items = score_metadata(seed_rows, cand_rows, exclude={_uid(1)}, limit=10)
        self.assertEqual(items, [])

    def test_empty_seed_features(self):
        # Seed with all-null joins (track with no album artist/genre linkage)
        seed_rows = [_row(_uid(1), album=None, artist=None, genre=None)]
        cand_rows = [_row(_uid(2), artist=100)]
        self.assertEqual(score_metadata(seed_rows, cand_rows, exclude=set(), limit=10), [])

    def test_shared_work_component_always_zero_phase1(self):
        seed_rows = [_row(_uid(1), artist=100)]
        cand_rows = [_row(_uid(2), artist=100)]
        items = score_metadata(seed_rows, cand_rows, exclude={_uid(1)}, limit=10)
        self.assertEqual(items[0].components['shared_work'], 0.0)


class ExtractSeedFeatureIdsTests(SimpleTestCase):

    def test_extracts_and_dedupes(self):
        rows = [
            _row(_uid(1), album=10, artist=100, genre=1000),
            _row(_uid(1), album=10, artist=200, genre=1000),  # same album+genre, diff artist
        ]
        albums, artists, genres = extract_seed_feature_ids(rows)
        self.assertEqual(sorted(albums), [10])
        self.assertEqual(sorted(artists), [100, 200])
        self.assertEqual(sorted(genres), [1000])

    def test_empty_returns_sentinel(self):
        albums, artists, genres = extract_seed_feature_ids([_row(_uid(1))])
        self.assertEqual(albums, [-1])
        self.assertEqual(artists, [-1])
        self.assertEqual(genres, [-1])


# --- co-occurrence scorer ---

class ScoreCoOccurrenceTests(SimpleTestCase):

    @staticmethod
    def _nrow(jid, pmi, co):
        return {'neighbour': jid, 'pmi_score': pmi, 'co_count': co}

    def test_single_neighbour(self):
        rows = [self._nrow(_uid(2), pmi=1.5, co=10)]
        items = score_cooccurrence(rows, exclude=set(), limit=10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].juke_id, _uid(2))
        self.assertEqual(items[0].score, 1.5)
        self.assertEqual(items[0].components, {'pmi_sum': 1.5, 'co_count_sum': 10.0})

    def test_pmi_summed_across_seeds(self):
        # Same neighbour co-occurs with two seeds → PMI sums
        cand = _uid(2)
        rows = [self._nrow(cand, 0.8, 5), self._nrow(cand, 0.6, 3)]
        items = score_cooccurrence(rows, exclude=set(), limit=10)
        self.assertEqual(len(items), 1)
        self.assertAlmostEqual(items[0].score, 1.4)
        self.assertEqual(items[0].components['co_count_sum'], 8.0)

    def test_ranked_by_pmi_desc(self):
        rows = [
            self._nrow(_uid(2), 0.5, 1),
            self._nrow(_uid(3), 1.5, 1),
            self._nrow(_uid(4), 1.0, 1),
        ]
        items = score_cooccurrence(rows, exclude=set(), limit=10)
        self.assertEqual([i.juke_id for i in items], [_uid(3), _uid(4), _uid(2)])

    def test_exclude_filters_neighbours(self):
        seed = _uid(1)
        rows = [self._nrow(seed, 2.0, 10), self._nrow(_uid(2), 0.5, 1)]
        items = score_cooccurrence(rows, exclude={seed}, limit=10)
        self.assertEqual([i.juke_id for i in items], [_uid(2)])

    def test_deterministic_tie_break(self):
        rows = [self._nrow(_uid(5), 1.0, 1), self._nrow(_uid(3), 1.0, 1)]
        items = score_cooccurrence(rows, exclude=set(), limit=10)
        self.assertEqual([i.juke_id for i in items], [_uid(3), _uid(5)])

    def test_limit(self):
        rows = [self._nrow(_uid(i), float(i), 1) for i in range(2, 20)]
        items = score_cooccurrence(rows, exclude=set(), limit=10)
        self.assertEqual(len(items), 10)
        # highest PMI first
        self.assertEqual(items[0].juke_id, _uid(19))

    def test_empty_rows(self):
        self.assertEqual(score_cooccurrence([], exclude=set(), limit=10), [])

    def test_negative_pmi_ranks_below_positive(self):
        rows = [self._nrow(_uid(2), -0.5, 1), self._nrow(_uid(3), 0.1, 1)]
        items = score_cooccurrence(rows, exclude=set(), limit=10)
        self.assertEqual(items[0].juke_id, _uid(3))
        self.assertEqual(items[1].juke_id, _uid(2))


class ScoredItemTests(SimpleTestCase):

    def test_dataclass_fields(self):
        item = ScoredItem(juke_id=_uid(1), score=0.5)
        self.assertEqual(item.components, {})
        item.components['x'] = 1.0
        self.assertEqual(item.components['x'], 1.0)

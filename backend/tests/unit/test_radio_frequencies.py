from decimal import Decimal

from django.test import SimpleTestCase

from radio import frequencies as fq


class FrequencyRuleTests(SimpleTestCase):
    def test_snap_rounds_to_odd_tenths_within_band(self):
        self.assertEqual(fq.from_tenths(fq.snap_tenths(95.0)), Decimal('95.1'))
        self.assertEqual(fq.from_tenths(fq.snap_tenths('95.24')), Decimal('95.3'))
        self.assertEqual(fq.from_tenths(fq.snap_tenths(95.3)), Decimal('95.3'))
        self.assertEqual(fq.from_tenths(fq.snap_tenths(80)), Decimal('88.1'))
        self.assertEqual(fq.from_tenths(fq.snap_tenths(120)), Decimal('107.9'))
        self.assertEqual(fq.from_tenths(fq.snap_tenths(108.0)), Decimal('107.9'))

    def test_place_keeps_free_value(self):
        self.assertEqual(fq.place(100.1, [Decimal('88.7'), Decimal('97.9')]), Decimal('100.1'))

    def test_place_moves_to_nearest_free_slot(self):
        # 95.1 is within 2.2 MHz of 94.1; nearest free slots are 96.3 (above) and 91.9 (below 2.2 from 94.1).
        self.assertEqual(fq.place(95.1, [Decimal('94.1')]), Decimal('96.3'))
        self.assertEqual(fq.place(93.5, [Decimal('94.1')]), Decimal('91.9'))

    def test_place_exactly_two_point_two_apart_is_allowed(self):
        self.assertEqual(fq.place(90.9, [Decimal('88.7')]), Decimal('90.9'))
        self.assertEqual(fq.place(90.7, [Decimal('88.7')]), Decimal('90.9'))

    def test_place_tie_prefers_higher_slot(self):
        self.assertEqual(fq.place(98.1, [Decimal('98.1')]), Decimal('100.3'))

    def test_highest_free_slot(self):
        self.assertEqual(fq.highest_free([]), Decimal('107.9'))
        self.assertEqual(fq.highest_free([Decimal('88.7'), Decimal('107.9')]), Decimal('105.7'))
        self.assertEqual(fq.highest_free([Decimal('106.9')]), Decimal('104.7'))

    def test_full_dial_falls_back_to_least_crowded_unused_slot(self):
        taken = [fq.from_tenths(slot) for slot in range(881, 1080, 22)]  # 10 stations, every 2.2 MHz
        self.assertEqual(len(taken), 10)
        placed = fq.highest_free(taken)
        self.assertNotIn(placed, taken)
        self.assertEqual(int(placed * 10) % 2, 1)
        moved = fq.place(taken[3], taken)
        self.assertNotIn(moved, taken)

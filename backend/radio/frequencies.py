"""FM dial rules: odd tenths in 88.1–107.9 MHz, stations kept ≥2.2 MHz apart.

All arithmetic happens in integer tenths of a MHz (881 … 1079) to avoid float drift.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

MIN_TENTHS = 881
MAX_TENTHS = 1079
MIN_SPACING_TENTHS = 22
PERSONAL_FREQUENCY = Decimal('88.7')
SLOTS = tuple(range(MIN_TENTHS, MAX_TENTHS + 1, 2))


def to_tenths(value) -> int:
    return int((Decimal(str(value)) * 10).to_integral_value(rounding=ROUND_HALF_UP))


def from_tenths(tenths: int) -> Decimal:
    return (Decimal(tenths) / 10).quantize(Decimal('0.1'))


def snap_tenths(value) -> int:
    """Clamp into the band and round to the nearest odd tenth (exact even tenths round up)."""
    tenths = min(max(to_tenths(value), MIN_TENTHS), MAX_TENTHS)
    if tenths % 2 == 0:
        tenths = tenths + 1 if tenths < MAX_TENTHS else tenths - 1
    return tenths


def _min_distance(slot: int, taken: list[int]) -> int:
    return min((abs(slot - other) for other in taken), default=MAX_TENTHS)


def _is_free(slot: int, taken: list[int]) -> bool:
    return _min_distance(slot, taken) >= MIN_SPACING_TENTHS


def _least_crowded(taken: list[int], prefer) -> int:
    """When the dial is full, pick the unoccupied slot farthest from every station."""
    candidates = [slot for slot in SLOTS if slot not in taken] or list(SLOTS)
    return max(candidates, key=lambda slot: (_min_distance(slot, taken), prefer(slot)))


def place(value, others: Iterable) -> Decimal:
    """Snap ``value`` and move it to the nearest free slot if it crowds another station."""
    taken = [to_tenths(other) for other in others]
    target = snap_tenths(value)
    if _is_free(target, taken):
        return from_tenths(target)
    free = [slot for slot in SLOTS if _is_free(slot, taken)]
    if free:
        # Nearest free slot; on equal distance prefer the higher frequency.
        best = min(free, key=lambda slot: (abs(slot - target), -slot))
        return from_tenths(best)
    return from_tenths(_least_crowded(taken, prefer=lambda slot: -abs(slot - target)))


def highest_free(others: Iterable) -> Decimal:
    taken = [to_tenths(other) for other in others]
    free = [slot for slot in SLOTS if _is_free(slot, taken)]
    if free:
        return from_tenths(max(free))
    return from_tenths(_least_crowded(taken, prefer=lambda slot: slot))

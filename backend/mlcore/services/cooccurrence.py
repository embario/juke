"""
Co-occurrence trainer (arch §5.4, §7.2).

Produces symmetric pairwise PMI scores from behavioral baskets and
persists them to mlcore_item_cooccurrence. A basket is any collection
of juke_ids observed together (same search session, same playlist, etc).

PMI(a,b) = log2( P(a,b) / (P(a) * P(b)) )
  where P(x)   = count_baskets_containing_x / N
        P(a,b) = co_count / N
No smoothing needed: we only store pairs with co_count >= 1, and any
item in a stored pair has item_count >= 1, so the log is always finite.

Pairs are stored canonically (a < b lexicographic) so the table holds
exactly one row per unordered pair.
"""
import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable
from uuid import UUID

from catalog.models import SearchHistoryResource, Track
from mlcore.models import ItemCoOccurrence

logger = logging.getLogger(__name__)

# Baskets smaller than this contribute no pairs.
MIN_BASKET_SIZE = 2

# bulk_create chunk size — keeps memory + transaction size bounded.
WRITE_BATCH_SIZE = 1000


@dataclass
class TrainingResult:
    baskets_processed: int
    baskets_skipped: int
    items_seen: int
    pairs_written: int


def _canonical_pair(a: UUID, b: UUID) -> tuple[UUID, UUID]:
    """Order a pair lexicographically so (a,b) and (b,a) collapse to one key."""
    return (a, b) if str(a) < str(b) else (b, a)


def baskets_from_search_history(resource_type: str = 'track') -> list[list[UUID]]:
    """
    Build baskets from SearchHistoryResource: one basket per search session,
    containing the juke_ids of resources the user engaged with.

    SearchHistoryResource stores integer PKs; this resolves them to juke_ids
    in one bulk query per call.
    """
    # Pull (session_id, resource_pk) pairs for the requested type.
    rows = (
        SearchHistoryResource.objects
        .filter(resource_type=resource_type)
        .values_list('search_history_id', 'resource_id')
    )

    session_to_pks: dict[int, set[int]] = defaultdict(set)
    all_pks: set[int] = set()
    for session_id, pk in rows:
        session_to_pks[session_id].add(pk)
        all_pks.add(pk)

    if not all_pks:
        return []

    # Resolve PK → juke_id in one query. Phase 1 is track-centric.
    if resource_type != 'track':
        raise ValueError(f"resource_type '{resource_type}' not supported in Phase 1")
    pk_to_juke: dict[int, UUID] = dict(
        Track.objects.filter(pk__in=all_pks).values_list('pk', 'juke_id')
    )

    baskets: list[list[UUID]] = []
    for pks in session_to_pks.values():
        juke_ids = [pk_to_juke[pk] for pk in pks if pk in pk_to_juke]
        if len(juke_ids) >= MIN_BASKET_SIZE:
            baskets.append(juke_ids)

    return baskets


def compute_pmi_table(baskets: Iterable[list[UUID]]) -> tuple[dict[tuple[UUID, UUID], tuple[int, float]], TrainingResult]:
    """
    Count pairs and compute smoothed PMI. Returns (pair_table, result_stats)
    where pair_table maps canonical (a,b) -> (co_count, pmi_score).

    Pure function — no DB writes. Makes the math independently testable.
    """
    item_count: Counter[UUID] = Counter()
    pair_count: Counter[tuple[UUID, UUID]] = Counter()
    n_baskets = 0
    skipped = 0

    for basket in baskets:
        unique = set(basket)
        if len(unique) < MIN_BASKET_SIZE:
            skipped += 1
            continue
        n_baskets += 1
        for item in unique:
            item_count[item] += 1
        for a, b in combinations(unique, 2):
            pair_count[_canonical_pair(a, b)] += 1

    table: dict[tuple[UUID, UUID], tuple[int, float]] = {}
    if n_baskets == 0:
        return table, TrainingResult(0, skipped, 0, 0)

    for (a, b), co in pair_count.items():
        p_ab = co / n_baskets
        p_a = item_count[a] / n_baskets
        p_b = item_count[b] / n_baskets
        pmi = math.log2(p_ab / (p_a * p_b))
        table[(a, b)] = (co, pmi)

    result = TrainingResult(
        baskets_processed=n_baskets,
        baskets_skipped=skipped,
        items_seen=len(item_count),
        pairs_written=len(table),
    )
    return table, result


def train_cooccurrence(baskets: Iterable[list[UUID]] | None = None) -> TrainingResult:
    """
    Full pipeline: extract baskets (or use supplied ones), compute PMI,
    persist to mlcore_item_cooccurrence.

    Idempotent: re-running with the same baskets produces identical rows
    (update_conflicts overwrites co_count + pmi_score on collision).
    """
    if baskets is None:
        baskets = baskets_from_search_history()

    table, result = compute_pmi_table(baskets)

    if not table:
        logger.info("train_cooccurrence: no pairs to write (baskets=%d skipped=%d)",
                    result.baskets_processed, result.baskets_skipped)
        return result

    rows = [
        ItemCoOccurrence(item_a_juke_id=a, item_b_juke_id=b, co_count=co, pmi_score=pmi)
        for (a, b), (co, pmi) in table.items()
    ]

    for i in range(0, len(rows), WRITE_BATCH_SIZE):
        batch = rows[i:i + WRITE_BATCH_SIZE]
        ItemCoOccurrence.objects.bulk_create(
            batch,
            update_conflicts=True,
            unique_fields=['item_a_juke_id', 'item_b_juke_id'],
            update_fields=['co_count', 'pmi_score', 'updated_at'],
        )

    logger.info(
        "train_cooccurrence: wrote %d pairs from %d baskets (%d items, %d skipped)",
        result.pairs_written, result.baskets_processed, result.items_seen, result.baskets_skipped,
    )
    return result

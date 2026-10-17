"""Wave expansion of the Spotify hydration queue (round 3, S3).

When a popular item has just been hydrated, its related items are likely to matter next: the items it
co-occurs with in listening sessions (``ItemCoOccurrence``) and its same-album / same-artist siblings in
the catalog. Each wave moves a bounded number of those neighbours up the queue:

* only seeds with a corpus or user priority better than ``WAVE_SEED_MAX_PRIORITY`` expand, so the chain
  fades out after a few hops (each hop adds ``WAVE_STEP``);
* at most ``max_seeds`` seeds per wave, ``fan_out`` co-listening neighbours and ``sibling_fan_out``
  siblings per seed, and ``max_updates`` rows per wave, so one hub item cannot flood the queue;
* a neighbour is only ever moved EARLIER and never ahead of priority 1, so user-referenced boosts
  (priority below 1) always stay in front.
"""
from collections import defaultdict
from dataclasses import dataclass
from itertools import islice
import time

from django.db.models import Q

from catalog.models import Track
from mlcore.models import CanonicalItem, ItemCoOccurrence, ProviderHydrationItem

WAVE_STEP = 8
WAVE_SEED_MAX_PRIORITY = 80
WAVE_MIN_PRIORITY = 1
WAVE_MAX_PRIORITY = 99
MIN_CO_COUNT = 3
CHUNK = 500


@dataclass(frozen=True)
class WaveResult:
    seeds_used: int
    neighbors: int
    rows_updated: int
    remaining_seeds: list


def wave_priority(seed_priority):
    return min(WAVE_MAX_PRIORITY, max(WAVE_MIN_PRIORITY, seed_priority + WAVE_STEP))


def cooccurring_items(canonical_id, limit):
    """Top co-listened neighbours of one item by PMI, then count, from both stored orientations."""
    rows = []
    for own, other in (('item_a_juke_id', 'item_b_juke_id'), ('item_b_juke_id', 'item_a_juke_id')):
        rows.extend(
            ItemCoOccurrence.objects.filter(**{own: canonical_id}, co_count__gte=MIN_CO_COUNT)
            .order_by('-pmi_score', '-co_count')
            .values_list(other, 'pmi_score', 'co_count')[:limit]
        )
    rows.sort(key=lambda row: (-row[1], -row[2]))
    return [other for other, _pmi, _count in rows[:limit]]


def sibling_items(canonical_id, limit):
    """Canonical items of other tracks on the same album, then by the same artists (catalog links only)."""
    track_id = CanonicalItem.objects.filter(pk=canonical_id).values_list('track_id', flat=True).first()
    if track_id is None or limit < 1:
        return []
    track = Track.objects.filter(juke_id=track_id).select_related('album').first()
    if track is None:
        return []
    sibling_ids = list(
        Track.objects.filter(album_id=track.album_id).exclude(pk=track.pk).order_by('track_number')
        .values_list('juke_id', flat=True)[:limit]
    )
    if len(sibling_ids) < limit:
        artist_ids = list(track.album.artists.values_list('pk', flat=True))
        if artist_ids:
            more = (
                Track.objects.filter(album__artists__in=artist_ids)
                .exclude(Q(pk=track.pk) | Q(album_id=track.album_id)).distinct().order_by('pk')
                .values_list('juke_id', flat=True)[: limit - len(sibling_ids)]
            )
            sibling_ids.extend(more)
    return list(CanonicalItem.objects.filter(track_id__in=sibling_ids).values_list('id', flat=True)[:limit])


def expand_wave(
    seeds, *, max_seeds=10, fan_out=10, sibling_fan_out=5, max_updates=500, time_budget_seconds=20.0,
    monotonic=time.monotonic,
):
    """Expand one wave from ``seeds`` = ``[(canonical_item_id, priority), ...]`` of just-hydrated items.

    Seeds that are not popular enough are dropped; seeds beyond ``max_seeds`` are returned for the next
    wave. ``time_budget_seconds`` stops starting new seeds once spent (a hub item's co-occurrence
    lookup measured up to ~19 s cold on Neptune), returning the unexpanded seeds as well.
    Returns a ``WaveResult``.
    """
    eligible = sorted(
        ((canonical_id, priority) for canonical_id, priority in seeds if priority < WAVE_SEED_MAX_PRIORITY),
        key=lambda seed: seed[1],
    )
    candidates, remaining = eligible[:max_seeds], eligible[max_seeds:]
    targets = {}
    used = []
    started = monotonic()
    seed_ids = {canonical_id for canonical_id, _priority in candidates}
    for position, (canonical_id, priority) in enumerate(candidates):
        if used and monotonic() - started >= time_budget_seconds:
            remaining = candidates[position:] + remaining
            break
        used.append((canonical_id, priority))
        wanted = wave_priority(priority)
        for neighbor in [*cooccurring_items(canonical_id, fan_out), *sibling_items(canonical_id, sibling_fan_out)]:
            if neighbor not in seed_ids:
                targets[neighbor] = min(wanted, targets.get(neighbor, wanted))
    if len(targets) > max_updates:
        targets = dict(islice(sorted(targets.items(), key=lambda pair: pair[1]), max_updates))
    by_priority = defaultdict(list)
    for neighbor, priority in targets.items():
        by_priority[priority].append(neighbor)
    updated = 0
    for priority, neighbors in by_priority.items():
        for start in range(0, len(neighbors), CHUNK):
            updated += ProviderHydrationItem.objects.filter(
                provider='spotify', canonical_item_id__in=neighbors[start:start + CHUNK],
                status__in=['pending', 'retry'], priority__gt=priority,
            ).update(priority=priority)
    return WaveResult(seeds_used=len(used), neighbors=len(targets), rows_updated=updated, remaining_seeds=remaining)

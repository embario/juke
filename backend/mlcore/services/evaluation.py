"""
Offline evaluation harness (arch §9 Phase 1).

Computes Recall@K, nDCG@K, catalog coverage, and a cold-start slice over a
leave-one-out dataset built from behavioral baskets. Persists one
ModelEvaluation row per (candidate_label, metric_name, dataset_hash).

Phase 1 data source is SearchHistoryResource only — see
tasks/musicprofile-favorites-resolvable-identity.md for the follow-up to
mix MusicProfile.favorite_tracks in once those become resolvable to juke_ids.

Ranker adapters call the same pure scorers the engine uses
(recommender_engine/app/scorers.py) so offline scores match serving scores
without an HTTP round-trip per trial.
"""
from __future__ import annotations

import hashlib
import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Protocol
from uuid import UUID

from django.db.models import Q

from catalog.models import Track
from mlcore.models import ItemCoOccurrence, ModelEvaluation, TrainingRun
from mlcore.services.cooccurrence import (
    _SPLIT_BUCKET_COUNT,
    baskets_from_search_history,
)
from recommender_engine.app.scorers import (
    extract_seed_feature_ids,
    score_cooccurrence,
    score_metadata,
)

logger = logging.getLogger(__name__)

DEFAULT_K = 10
# A held-out item is "cold" if it appears in at most this many baskets.
DEFAULT_COLD_THRESHOLD = 2

# Metric names as stored in mlcore_model_evaluation.metric_name.
# Stage 5 promotion gates join on these — keep stable.
METRIC_RECALL = 'recall@10'
METRIC_NDCG = 'ndcg@10'
METRIC_COVERAGE = 'coverage'
METRIC_COLD_RECALL = 'cold_start_recall@10'


# --- pure metric math (no DB) ---

def recall_at_k(ranked: list[UUID], relevant: set[UUID], k: int) -> float:
    """Fraction of relevant items that appear in the top-k ranked list."""
    if not relevant:
        return 0.0
    hits = sum(1 for jid in ranked[:k] if jid in relevant)
    return hits / len(relevant)


def ndcg_at_k(ranked: list[UUID], relevant: set[UUID], k: int) -> float:
    """
    Normalized DCG with binary relevance. DCG = sum over relevant hits of
    1/log2(rank+1) where rank is 1-indexed. IDCG places all |relevant| hits
    at the top. For the single-relevant LOO case this reduces to
    1/log2(rank+1) if hit else 0.
    """
    if not relevant:
        return 0.0
    dcg = 0.0
    for i, jid in enumerate(ranked[:k], start=1):
        if jid in relevant:
            dcg += 1.0 / math.log2(i + 1)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def coverage(recommended_ids: Iterable[UUID], catalog_size: int) -> float:
    """Fraction of the catalog that appeared at least once in any recommendation."""
    if catalog_size <= 0:
        return 0.0
    return len(set(recommended_ids)) / catalog_size


# --- dataset construction ---

@dataclass(frozen=True)
class Trial:
    seeds: tuple[UUID, ...]
    held_out: UUID
    is_cold: bool


@dataclass
class Dataset:
    trials: list[Trial]
    dataset_hash: str
    item_frequency: dict[UUID, int] = field(default_factory=dict)


def build_loo_dataset(
    baskets: list[list[UUID]] | None = None,
    cold_threshold: int = DEFAULT_COLD_THRESHOLD,
    split: str = "all",
    split_buckets: int = _SPLIT_BUCKET_COUNT,
) -> Dataset:
    """
    Leave-one-out trials from behavioral baskets. For each basket of size n,
    emit n trials: hold one item out, use the remaining n-1 as seeds.

    The dataset hash is SHA256 over the sorted trial identities, so identical
    basket inputs always produce the same hash regardless of dict iteration
    order inside baskets_from_search_history().

    Phase 1: baskets come from SearchHistoryResource. See module docstring
    for the planned MusicProfile.favorite_tracks follow-up.
    """
    if baskets is None:
        baskets = baskets_from_search_history(split=split, split_buckets=split_buckets)

    # Frequency over baskets (not raw occurrences — baskets are already deduped sets).
    freq: Counter[UUID] = Counter()
    for basket in baskets:
        for jid in set(basket):
            freq[jid] += 1

    trials: list[Trial] = []
    for basket in baskets:
        unique = sorted(set(basket), key=str)  # sorted → deterministic trial order
        if len(unique) < 2:
            continue
        for i, held_out in enumerate(unique):
            seeds = tuple(unique[:i] + unique[i + 1:])
            trials.append(Trial(
                seeds=seeds,
                held_out=held_out,
                is_cold=freq[held_out] <= cold_threshold,
            ))

    hasher = hashlib.sha256()
    # Canonical string per trial: sorted seeds joined + held-out, one line each, whole stream sorted.
    lines = sorted(
        ','.join(sorted(str(s) for s in t.seeds)) + '|' + str(t.held_out)
        for t in trials
    )
    for line in lines:
        hasher.update(line.encode('utf-8'))
        hasher.update(b'\n')
    dataset_hash = hasher.hexdigest()

    return Dataset(trials=trials, dataset_hash=dataset_hash, item_frequency=dict(freq))


# --- ranker adapters ---
#
# ORM equivalents of the engine's _SEED_FEATURES_SQL / _METADATA_CANDIDATES_SQL /
# _COOCCURRENCE_SQL. Row shapes match what scorers.py expects so we reuse the
# exact same scoring code path the engine serves.

class Ranker(Protocol):
    label: str
    def rank(self, seeds: tuple[UUID, ...], exclude: set[UUID], limit: int) -> list[UUID]: ...


def _track_feature_rows(juke_ids: Iterable[UUID]) -> list[dict]:
    """
    Mirror _SEED_FEATURES_SQL: (juke_id, album_id, artist_id, genre_id) rows.
    M2M cross-product is intentional — scorers.score_metadata() unions per track.
    """
    qs = (
        Track.objects
        .filter(juke_id__in=list(juke_ids))
        .values('juke_id', 'album_id', 'album__artists', 'album__artists__genres')
    )
    return [
        {
            'juke_id': r['juke_id'],
            'album_id': r['album_id'],
            'artist_id': r['album__artists'],
            'genre_id': r['album__artists__genres'],
        }
        for r in qs
    ]


def _metadata_candidate_rows(album_ids: list, artist_ids: list, genre_ids: list) -> list[dict]:
    """
    Mirror _METADATA_CANDIDATES_SQL: any track whose album/artist/genre
    overlaps the seed feature sets. Sentinel -1 from extract_seed_feature_ids()
    matches nothing (no FK is ever -1) so the filter stays valid.
    """
    qs = (
        Track.objects
        .filter(
            Q(album_id__in=album_ids)
            | Q(album__artists__in=artist_ids)
            | Q(album__artists__genres__in=genre_ids)
        )
        .values('juke_id', 'album_id', 'album__artists', 'album__artists__genres')
        .distinct()
    )
    return [
        {
            'juke_id': r['juke_id'],
            'album_id': r['album_id'],
            'artist_id': r['album__artists'],
            'genre_id': r['album__artists__genres'],
        }
        for r in qs
    ]


class MetadataRanker:
    label = 'metadata'

    def rank(self, seeds: tuple[UUID, ...], exclude: set[UUID], limit: int) -> list[UUID]:
        seed_rows = _track_feature_rows(seeds)
        if not seed_rows:
            return []
        albums, artists, genres = extract_seed_feature_ids(seed_rows)
        cand_rows = _metadata_candidate_rows(albums, artists, genres)
        scored = score_metadata(seed_rows, cand_rows, exclude, limit)
        return [s.juke_id for s in scored]


class CoOccurrenceRanker:
    label = 'cooccurrence'

    def __init__(self, training_run: TrainingRun | None = None) -> None:
        self.training_run = training_run

    def rank(self, seeds: tuple[UUID, ...], exclude: set[UUID], limit: int) -> list[UUID]:
        seed_list = list(seeds)
        rows_a = (
            ItemCoOccurrence.objects
            .filter(item_a_juke_id__in=seed_list)
            .values('item_b_juke_id', 'pmi_score', 'co_count')
        )
        rows_b = (
            ItemCoOccurrence.objects
            .filter(item_b_juke_id__in=seed_list)
            .values('item_a_juke_id', 'pmi_score', 'co_count')
        )
        neighbour_rows = [
            {'neighbour': r['item_b_juke_id'], 'pmi_score': r['pmi_score'], 'co_count': r['co_count']}
            for r in rows_a
        ] + [
            {'neighbour': r['item_a_juke_id'], 'pmi_score': r['pmi_score'], 'co_count': r['co_count']}
            for r in rows_b
        ]
        scored = score_cooccurrence(neighbour_rows, exclude, limit)
        return [s.juke_id for s in scored]


RANKERS: dict[str, type] = {
    'metadata': MetadataRanker,
    'cooccurrence': CoOccurrenceRanker,
}


# --- evaluation driver ---

@dataclass
class EvaluationResult:
    candidate_label: str
    dataset_hash: str
    n_trials: int
    n_cold_trials: int
    metrics: dict[str, float]
    training_run: TrainingRun | None = None


def evaluate_ranker(
    ranker: Ranker,
    dataset: Dataset,
    k: int = DEFAULT_K,
    catalog_size: int | None = None,
) -> EvaluationResult:
    """Run a ranker over every trial and aggregate metrics."""
    if catalog_size is None:
        catalog_size = Track.objects.count()

    recall_sum = 0.0
    ndcg_sum = 0.0
    cold_recall_sum = 0.0
    n_cold = 0
    all_recommended: set[UUID] = set()

    for trial in dataset.trials:
        exclude = set(trial.seeds)  # never recommend a seed back
        ranked = ranker.rank(trial.seeds, exclude, k)
        all_recommended.update(ranked)
        relevant = {trial.held_out}
        r = recall_at_k(ranked, relevant, k)
        recall_sum += r
        ndcg_sum += ndcg_at_k(ranked, relevant, k)
        if trial.is_cold:
            n_cold += 1
            cold_recall_sum += r

    n = len(dataset.trials)
    metrics = {
        METRIC_RECALL: recall_sum / n if n else 0.0,
        METRIC_NDCG: ndcg_sum / n if n else 0.0,
        METRIC_COVERAGE: coverage(all_recommended, catalog_size),
        METRIC_COLD_RECALL: cold_recall_sum / n_cold if n_cold else 0.0,
    }

    logger.info(
        'evaluate_ranker label=%s trials=%d cold=%d recall@%d=%.4f ndcg@%d=%.4f '
        'coverage=%.4f cold_recall=%.4f dataset=%s',
        ranker.label, n, n_cold, k, metrics[METRIC_RECALL], k, metrics[METRIC_NDCG],
        metrics[METRIC_COVERAGE], metrics[METRIC_COLD_RECALL], dataset.dataset_hash[:12],
    )

    return EvaluationResult(
        candidate_label=ranker.label,
        dataset_hash=dataset.dataset_hash,
        n_trials=n,
        n_cold_trials=n_cold,
        training_run=getattr(ranker, "training_run", None),
        metrics=metrics,
    )


def persist_evaluation(result: EvaluationResult) -> list[ModelEvaluation]:
    """One ModelEvaluation row per metric. model_id stays null for baselines."""
    rows = [
        ModelEvaluation(
            model_id=None,
            candidate_label=result.candidate_label,
            metric_name=name,
            metric_value=value,
            dataset_hash=result.dataset_hash,
            training_run=result.training_run,
        )
        for name, value in result.metrics.items()
    ]
    return ModelEvaluation.objects.bulk_create(rows)


def run_offline_evaluation(
    labels: Iterable[str] | None = None,
    k: int = DEFAULT_K,
    cold_threshold: int = DEFAULT_COLD_THRESHOLD,
    split: str = "all",
    split_buckets: int = _SPLIT_BUCKET_COUNT,
    cooccurrence_training_run: TrainingRun | None = None,
    persist: bool = True,
) -> list[EvaluationResult]:
    """
    Build the LOO dataset once, evaluate each requested ranker against it,
    optionally persist. Returns results in the order labels were given.
    """
    if labels is None:
        labels = list(RANKERS.keys())

    dataset = build_loo_dataset(
        cold_threshold=cold_threshold,
        split=split,
        split_buckets=split_buckets,
    )
    if not dataset.trials:
        logger.warning('run_offline_evaluation: no trials — need SearchHistory sessions with >=2 tracks')
        return []

    catalog_size = Track.objects.count()
    results: list[EvaluationResult] = []
    for label in labels:
        ranker_cls = RANKERS.get(label)
        if ranker_cls is None:
            raise ValueError(f"unknown ranker label '{label}' (known: {sorted(RANKERS)})")
        if label == 'cooccurrence':
            if cooccurrence_training_run is None:
                cooccurrence_training_run = TrainingRun.objects.filter(
                    ranker_label='cooccurrence',
                ).order_by('-created_at').first()
            ranker = cooccurrence_training_run and CoOccurrenceRanker(cooccurrence_training_run) or CoOccurrenceRanker()
        else:
            ranker = ranker_cls()
        result = evaluate_ranker(ranker, dataset, k=k, catalog_size=catalog_size)
        if persist:
            persist_evaluation(result)
        results.append(result)

    return results

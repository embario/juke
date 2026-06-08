"""
Offline evaluation harness (arch §9 Phase 1).

Computes Recall@K, nDCG@K, catalog coverage, and a cold-start slice over a
leave-one-out dataset built from behavioral baskets. Persists one
ModelEvaluation row per (candidate_label, metric_name, dataset_hash).

Phase 1 defaults to blended behavioral sources: SearchHistoryResource plus
compact ListenBrainzSessionTrack behavioral facts. See
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
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Protocol
from uuid import UUID

from django.db import connection
from django.db.models import Q

from catalog.models import Track
from mlcore.models import CanonicalItem, ItemCoOccurrence, ModelEvaluation, TrainingRun
from mlcore.services.canonical_items import bulk_ensure_canonical_items_for_tracks
from mlcore.services.cooccurrence import (
    BEHAVIOR_SOURCE_LISTENBRAINZ,
    BEHAVIOR_SOURCE_SEARCH_HISTORY,
    MIN_BASKET_SIZE,
    _SPLIT_BUCKET_COUNT,
    _sql_split_predicate,
    baskets_from_behavioral_sources,
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
DEFAULT_EVALUATION_BATCH_SIZE = 1000

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
    n_baskets: int = 0


def _sample_listenbrainz_baskets(
    *,
    split: str,
    split_buckets: int,
    max_baskets: int,
) -> list[list[UUID]]:
    split_predicate, split_params = _sql_split_predicate(split, split_buckets)
    sql = f"""
        WITH eligible AS (
            SELECT session_key
            FROM mlcore_listenbrainz_session_track
            WHERE canonical_item_id IS NOT NULL
              AND {split_predicate}
            GROUP BY session_key
            HAVING COUNT(DISTINCT canonical_item_id) >= %s
            ORDER BY session_key
            LIMIT %s
        )
        SELECT e.session_key, st.canonical_item_id
        FROM eligible e
        JOIN mlcore_listenbrainz_session_track st
          ON st.session_key = e.session_key
        WHERE st.canonical_item_id IS NOT NULL
        ORDER BY e.session_key, st.canonical_item_id
    """
    session_to_jukes: dict[bytes, set[UUID]] = {}
    with connection.cursor() as cursor:
        cursor.execute(sql, [*split_params, MIN_BASKET_SIZE, max_baskets])
        for session_key, canonical_item_id in cursor.fetchall():
            normalized_session_key = session_key.tobytes() if isinstance(session_key, memoryview) else bytes(session_key)
            session_to_jukes.setdefault(normalized_session_key, set()).add(canonical_item_id)

    return [
        sorted(juke_ids, key=str)
        for _, juke_ids in sorted(session_to_jukes.items(), key=lambda item: item[0])
        if len(juke_ids) >= MIN_BASKET_SIZE
    ]


def build_loo_dataset(
    baskets: list[list[UUID]] | None = None,
    cold_threshold: int = DEFAULT_COLD_THRESHOLD,
    split: str = "all",
    split_buckets: int = _SPLIT_BUCKET_COUNT,
    sources: Iterable[str] | None = None,
    max_baskets: int | None = None,
    max_basket_items: int | None = None,
) -> Dataset:
    """
    Leave-one-out trials from behavioral baskets. For each basket of size n,
    emit n trials: hold one item out, use the remaining n-1 as seeds.

    The dataset hash is SHA256 over the sorted trial identities, so identical
    basket inputs always produce the same hash regardless of dict iteration
    order inside baskets_from_search_history().

    Phase 1 defaults to blended SearchHistoryResource plus external
    ListenBrainz session-track facts. See module docstring for the planned
    MusicProfile.favorite_tracks follow-up.
    """
    if baskets is None and max_baskets is not None:
        normalized_sources = set(sources or (BEHAVIOR_SOURCE_SEARCH_HISTORY, BEHAVIOR_SOURCE_LISTENBRAINZ))
        if normalized_sources == {BEHAVIOR_SOURCE_LISTENBRAINZ}:
            baskets = _sample_listenbrainz_baskets(
                split=split,
                split_buckets=split_buckets,
                max_baskets=max_baskets,
            )
        else:
            baskets = baskets_from_behavioral_sources(
                split=split,
                split_buckets=split_buckets,
                sources=sources,
            )[:max_baskets]
    elif baskets is None:
        baskets = baskets_from_behavioral_sources(
            split=split,
            split_buckets=split_buckets,
            sources=sources,
        )

    if max_basket_items is not None:
        baskets = [
            basket
            for basket in baskets
            if len(set(basket)) <= max_basket_items
        ]

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

    return Dataset(
        trials=trials,
        dataset_hash=dataset_hash,
        item_frequency=dict(freq),
        n_baskets=len(baskets),
    )


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
    canonical_rows = list(
        CanonicalItem.objects
        .filter(pk__in=list(juke_ids), track__isnull=False)
        .values('id', 'track__album_id', 'track__album__artists', 'track__album__artists__genres')
    )
    if canonical_rows:
        return [
            {
                'juke_id': r['id'],
                'album_id': r['track__album_id'],
                'artist_id': r['track__album__artists'],
                'genre_id': r['track__album__artists__genres'],
            }
            for r in canonical_rows
        ]

    tracks = list(Track.objects.filter(juke_id__in=list(juke_ids)))
    if not tracks:
        return []

    canonical_by_track_id = bulk_ensure_canonical_items_for_tracks(tracks)
    qs = Track.objects.filter(juke_id__in=[track.juke_id for track in tracks]).values(
        'juke_id',
        'album_id',
        'album__artists',
        'album__artists__genres',
    )
    return [
        {
            'juke_id': canonical_by_track_id[r['juke_id']].pk,
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
    tracks = list(
        Track.objects
        .filter(
            Q(album_id__in=album_ids)
            | Q(album__artists__in=artist_ids)
            | Q(album__artists__genres__in=genre_ids)
        )
    )
    if not tracks:
        return []

    canonical_by_track_id = bulk_ensure_canonical_items_for_tracks(tracks)
    qs = (
        Track.objects
        .filter(pk__in=[track.pk for track in tracks])
        .values('juke_id', 'album_id', 'album__artists', 'album__artists__genres')
        .distinct()
    )
    return [
        {
            'juke_id': canonical_by_track_id[r['juke_id']].pk,
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
    n_baskets: int = 0
    training_run: TrainingRun | None = None
    evaluation_started_at: datetime | None = None
    evaluation_elapsed_seconds: float | None = None
    evaluation_trials_per_second: float | None = None


@dataclass
class EvaluationProgress:
    candidate_label: str
    dataset_hash: str
    n_baskets: int
    n_trials: int
    n_cold_trials: int
    trials_scored: int = 0
    cold_trials_scored: int = 0
    recall_sum: float = 0.0
    ndcg_sum: float = 0.0
    cold_recall_sum: float = 0.0
    recommended_count: int = 0
    distinct_recommended_count: int = 0
    training_run_id: str = ""
    wall_started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    started_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    status: str = "running"

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self.updated_at - self.started_at)

    @property
    def trials_per_second(self) -> float:
        if self.elapsed_seconds <= 0:
            return 0.0
        return self.trials_scored / self.elapsed_seconds

    @property
    def eta_seconds(self) -> float:
        rate = self.trials_per_second
        if rate <= 0:
            return 0.0
        return max(0.0, (self.n_trials - self.trials_scored) / rate)


def write_evaluation_metrics(
    progress: EvaluationProgress,
    *,
    metrics_path: str | Path | None,
) -> Path | None:
    if not metrics_path:
        return None

    path = Path(metrics_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + '.tmp')

    def _escape_label(value: str) -> str:
        return value.replace('\\', '\\\\').replace('"', '\\"')

    labels = (
        f'candidate_label="{_escape_label(progress.candidate_label)}",'
        f'dataset_hash="{_escape_label(progress.dataset_hash)}",'
        f'training_run_id="{_escape_label(progress.training_run_id)}",'
        f'status="{_escape_label(progress.status)}"'
    )
    trial_denominator = progress.trials_scored or 1
    cold_denominator = progress.cold_trials_scored or 1
    current_recall = progress.recall_sum / trial_denominator
    current_ndcg = progress.ndcg_sum / trial_denominator
    current_cold_recall = (
        progress.cold_recall_sum / cold_denominator
        if progress.cold_trials_scored
        else 0.0
    )
    generated_at = datetime.now(tz=UTC).isoformat()
    lines = [
        '# HELP mlcore_evaluation_active Whether an offline model evaluation is currently active.',
        '# TYPE mlcore_evaluation_active gauge',
        f'mlcore_evaluation_active{{{labels}}} {1 if progress.status == "running" else 0}',
        '# HELP mlcore_evaluation_info Metadata for the latest offline model evaluation.',
        '# TYPE mlcore_evaluation_info gauge',
        (
            'mlcore_evaluation_info{'
            f'{labels},'
            f'started_at="{_escape_label(progress.wall_started_at.isoformat())}",'
            f'generated_at="{_escape_label(generated_at)}"'
            '} 1'
        ),
        '# HELP mlcore_evaluation_started_at_seconds Unix timestamp when the evaluation started.',
        '# TYPE mlcore_evaluation_started_at_seconds gauge',
        f'mlcore_evaluation_started_at_seconds{{{labels}}} {progress.wall_started_at.timestamp()}',
        '# HELP mlcore_evaluation_trials_total Total leave-one-out trials in the evaluation dataset.',
        '# TYPE mlcore_evaluation_trials_total gauge',
        f'mlcore_evaluation_trials_total{{{labels}}} {progress.n_trials}',
        '# HELP mlcore_evaluation_baskets_total Total baskets in the evaluation dataset.',
        '# TYPE mlcore_evaluation_baskets_total gauge',
        f'mlcore_evaluation_baskets_total{{{labels}}} {progress.n_baskets}',
        '# HELP mlcore_evaluation_trials_scored Leave-one-out trials scored so far.',
        '# TYPE mlcore_evaluation_trials_scored gauge',
        f'mlcore_evaluation_trials_scored{{{labels}}} {progress.trials_scored}',
        '# HELP mlcore_evaluation_cold_trials_total Total cold leave-one-out trials in the evaluation dataset.',
        '# TYPE mlcore_evaluation_cold_trials_total gauge',
        f'mlcore_evaluation_cold_trials_total{{{labels}}} {progress.n_cold_trials}',
        '# HELP mlcore_evaluation_cold_trials_scored Cold leave-one-out trials scored so far.',
        '# TYPE mlcore_evaluation_cold_trials_scored gauge',
        f'mlcore_evaluation_cold_trials_scored{{{labels}}} {progress.cold_trials_scored}',
        '# HELP mlcore_evaluation_progress_fraction Fraction of evaluation trials scored.',
        '# TYPE mlcore_evaluation_progress_fraction gauge',
        f'mlcore_evaluation_progress_fraction{{{labels}}} {progress.trials_scored / progress.n_trials if progress.n_trials else 0.0}',
        '# HELP mlcore_evaluation_elapsed_seconds Evaluation wall-clock seconds elapsed.',
        '# TYPE mlcore_evaluation_elapsed_seconds gauge',
        f'mlcore_evaluation_elapsed_seconds{{{labels}}} {progress.elapsed_seconds}',
        '# HELP mlcore_evaluation_eta_seconds Estimated seconds until evaluation completion.',
        '# TYPE mlcore_evaluation_eta_seconds gauge',
        f'mlcore_evaluation_eta_seconds{{{labels}}} {progress.eta_seconds}',
        '# HELP mlcore_evaluation_trials_per_second Current evaluation scoring throughput.',
        '# TYPE mlcore_evaluation_trials_per_second gauge',
        f'mlcore_evaluation_trials_per_second{{{labels}}} {progress.trials_per_second}',
        '# HELP mlcore_evaluation_current_metric Latest in-progress metric values.',
        '# TYPE mlcore_evaluation_current_metric gauge',
        f'mlcore_evaluation_current_metric{{{labels},metric="recall@10"}} {current_recall}',
        f'mlcore_evaluation_current_metric{{{labels},metric="ndcg@10"}} {current_ndcg}',
        f'mlcore_evaluation_current_metric{{{labels},metric="cold_start_recall@10"}} {current_cold_recall}',
        '# HELP mlcore_evaluation_distinct_recommendations Distinct recommended items observed so far.',
        '# TYPE mlcore_evaluation_distinct_recommendations gauge',
        f'mlcore_evaluation_distinct_recommendations{{{labels}}} {progress.distinct_recommended_count}',
        '',
    ]
    temp_path.write_text('\n'.join(lines), encoding='utf-8')
    temp_path.replace(path)
    return path


def _score_trials_with_ranker(
    ranker: Ranker,
    trials: list[Trial],
    *,
    k: int,
    batch_size: int,
    progress: EvaluationProgress | None = None,
    metrics_path: str | Path | None = None,
) -> tuple[float, float, float, int, set[UUID]]:
    recall_sum = 0.0
    ndcg_sum = 0.0
    cold_recall_sum = 0.0
    n_cold = 0
    all_recommended: set[UUID] = set()

    for start in range(0, len(trials), batch_size):
        batch = trials[start:start + batch_size]
        for trial in batch:
            exclude = set(trial.seeds)
            ranked = ranker.rank(trial.seeds, exclude, k)
            all_recommended.update(ranked)
            relevant = {trial.held_out}
            r = recall_at_k(ranked, relevant, k)
            recall_sum += r
            ndcg_sum += ndcg_at_k(ranked, relevant, k)
            if trial.is_cold:
                n_cold += 1
                cold_recall_sum += r

        if progress is not None:
            progress.trials_scored += len(batch)
            progress.cold_trials_scored = n_cold
            progress.recall_sum = recall_sum
            progress.ndcg_sum = ndcg_sum
            progress.cold_recall_sum = cold_recall_sum
            progress.recommended_count += len(all_recommended)
            progress.distinct_recommended_count = len(all_recommended)
            progress.updated_at = time.monotonic()
            write_evaluation_metrics(progress, metrics_path=metrics_path)

    return recall_sum, ndcg_sum, cold_recall_sum, n_cold, all_recommended


def _score_trials_with_cooccurrence_batches(
    ranker: CoOccurrenceRanker,
    trials: list[Trial],
    *,
    k: int,
    batch_size: int,
    progress: EvaluationProgress | None = None,
    metrics_path: str | Path | None = None,
) -> tuple[float, float, float, int, set[UUID]]:
    recall_sum = 0.0
    ndcg_sum = 0.0
    cold_recall_sum = 0.0
    n_cold = 0
    all_recommended: set[UUID] = set()

    for start in range(0, len(trials), batch_size):
        batch = trials[start:start + batch_size]
        seed_ids = sorted({seed for trial in batch for seed in trial.seeds}, key=str)
        neighbours_by_seed: dict[UUID, list[dict]] = {seed: [] for seed in seed_ids}
        if seed_ids:
            rows_a = (
                ItemCoOccurrence.objects
                .filter(item_a_juke_id__in=seed_ids)
                .values('item_a_juke_id', 'item_b_juke_id', 'pmi_score', 'co_count')
                .iterator(chunk_size=10000)
            )
            for row in rows_a:
                neighbours_by_seed[row['item_a_juke_id']].append({
                    'neighbour': row['item_b_juke_id'],
                    'pmi_score': row['pmi_score'],
                    'co_count': row['co_count'],
                })

            rows_b = (
                ItemCoOccurrence.objects
                .filter(item_b_juke_id__in=seed_ids)
                .values('item_a_juke_id', 'item_b_juke_id', 'pmi_score', 'co_count')
                .iterator(chunk_size=10000)
            )
            for row in rows_b:
                neighbours_by_seed[row['item_b_juke_id']].append({
                    'neighbour': row['item_a_juke_id'],
                    'pmi_score': row['pmi_score'],
                    'co_count': row['co_count'],
                })

        for trial in batch:
            exclude = set(trial.seeds)
            neighbour_rows = [
                neighbour
                for seed in trial.seeds
                for neighbour in neighbours_by_seed.get(seed, [])
            ]
            ranked = [s.juke_id for s in score_cooccurrence(neighbour_rows, exclude, k)]
            all_recommended.update(ranked)
            relevant = {trial.held_out}
            r = recall_at_k(ranked, relevant, k)
            recall_sum += r
            ndcg_sum += ndcg_at_k(ranked, relevant, k)
            if trial.is_cold:
                n_cold += 1
                cold_recall_sum += r

        if progress is not None:
            progress.trials_scored += len(batch)
            progress.cold_trials_scored = n_cold
            progress.recall_sum = recall_sum
            progress.ndcg_sum = ndcg_sum
            progress.cold_recall_sum = cold_recall_sum
            progress.distinct_recommended_count = len(all_recommended)
            progress.updated_at = time.monotonic()
            write_evaluation_metrics(progress, metrics_path=metrics_path)

    return recall_sum, ndcg_sum, cold_recall_sum, n_cold, all_recommended


def evaluate_ranker(
    ranker: Ranker,
    dataset: Dataset,
    k: int = DEFAULT_K,
    catalog_size: int | None = None,
    batch_size: int = DEFAULT_EVALUATION_BATCH_SIZE,
    metrics_path: str | Path | None = None,
) -> EvaluationResult:
    """Run a ranker over every trial and aggregate metrics."""
    if catalog_size is None:
        catalog_size = Track.objects.count()

    n = len(dataset.trials)
    progress = EvaluationProgress(
        candidate_label=ranker.label,
        dataset_hash=dataset.dataset_hash,
        n_baskets=dataset.n_baskets,
        n_trials=n,
        n_cold_trials=sum(1 for trial in dataset.trials if trial.is_cold),
        training_run_id=str(getattr(ranker, "training_run", None).pk) if getattr(ranker, "training_run", None) else "",
    ) if metrics_path else None
    if progress is not None:
        write_evaluation_metrics(progress, metrics_path=metrics_path)

    if isinstance(ranker, CoOccurrenceRanker):
        recall_sum, ndcg_sum, cold_recall_sum, n_cold, all_recommended = _score_trials_with_cooccurrence_batches(
            ranker,
            dataset.trials,
            k=k,
            batch_size=batch_size,
            progress=progress,
            metrics_path=metrics_path,
        )
    else:
        recall_sum, ndcg_sum, cold_recall_sum, n_cold, all_recommended = _score_trials_with_ranker(
            ranker,
            dataset.trials,
            k=k,
            batch_size=batch_size,
            progress=progress,
            metrics_path=metrics_path,
        )

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

    if progress is not None:
        progress.status = "complete"
        progress.trials_scored = n
        progress.cold_trials_scored = n_cold
        progress.recall_sum = recall_sum
        progress.ndcg_sum = ndcg_sum
        progress.cold_recall_sum = cold_recall_sum
        progress.distinct_recommended_count = len(all_recommended)
        progress.updated_at = time.monotonic()
        write_evaluation_metrics(progress, metrics_path=metrics_path)

    return EvaluationResult(
        candidate_label=ranker.label,
        dataset_hash=dataset.dataset_hash,
        n_baskets=dataset.n_baskets,
        n_trials=n,
        n_cold_trials=n_cold,
        training_run=getattr(ranker, "training_run", None),
        evaluation_started_at=progress.wall_started_at if progress is not None else None,
        evaluation_elapsed_seconds=progress.elapsed_seconds if progress is not None else None,
        evaluation_trials_per_second=progress.trials_per_second if progress is not None else None,
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
            n_baskets=result.n_baskets,
            n_trials=result.n_trials,
            n_cold_trials=result.n_cold_trials,
            evaluation_started_at=result.evaluation_started_at,
            evaluation_elapsed_seconds=result.evaluation_elapsed_seconds,
            evaluation_trials_per_second=result.evaluation_trials_per_second,
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
    sources: Iterable[str] | None = None,
    cooccurrence_training_run: TrainingRun | None = None,
    max_baskets: int | None = None,
    max_basket_items: int | None = None,
    batch_size: int = DEFAULT_EVALUATION_BATCH_SIZE,
    metrics_path: str | Path | None = None,
    persist: bool = True,
) -> list[EvaluationResult]:
    """
    Build the LOO dataset once, evaluate each requested ranker against it,
    optionally persist. Returns results in the order labels were given.
    """
    if labels is None:
        labels = list(RANKERS.keys())

    dataset_kwargs = {
        'cold_threshold': cold_threshold,
        'split': split,
        'split_buckets': split_buckets,
    }
    if sources is not None:
        dataset_kwargs['sources'] = sources
    if max_baskets is not None:
        dataset_kwargs['max_baskets'] = max_baskets
    if max_basket_items is not None:
        dataset_kwargs['max_basket_items'] = max_basket_items

    dataset = build_loo_dataset(**dataset_kwargs)
    if not dataset.trials:
        logger.warning('run_offline_evaluation: no trials — need behavioral sessions with >=2 tracks')
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
        result = evaluate_ranker(
            ranker,
            dataset,
            k=k,
            catalog_size=catalog_size,
            batch_size=batch_size,
            metrics_path=metrics_path,
        )
        if persist:
            persist_evaluation(result)
        results.append(result)

    return results

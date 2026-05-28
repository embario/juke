from __future__ import annotations

from uuid import UUID

from django.utils import timezone

from mlcore.models import CoOccurrenceTrainingBucket, TrainingRun


def ensure_cooccurrence_bucket_rows(
    *,
    training_run: TrainingRun,
    source: str,
    algorithm_version: str,
    bucket_count: int,
) -> None:
    rows = [
        CoOccurrenceTrainingBucket(
            training_run=training_run,
            source=source,
            algorithm_version=algorithm_version,
            bucket_count=bucket_count,
            bucket_index=bucket_index,
            status='pending',
        )
        for bucket_index in range(bucket_count)
    ]
    CoOccurrenceTrainingBucket.objects.bulk_create(rows, ignore_conflicts=True)


def mark_prior_buckets_assumed_succeeded(
    *,
    training_run: TrainingRun,
    start_bucket: int,
    bucket_count: int,
    reason: str,
) -> None:
    if start_bucket <= 0:
        return
    now = timezone.now()
    (
        CoOccurrenceTrainingBucket.objects
        .filter(
            training_run=training_run,
            bucket_count=bucket_count,
            bucket_index__lt=start_bucket,
        )
        .exclude(status='succeeded')
        .update(
            status='assumed_succeeded',
            completed_at=now,
            metadata={'resume_assumption': reason},
        )
    )


def pending_bucket_indices(
    *,
    training_run: TrainingRun,
    bucket_count: int,
    start_bucket: int = 0,
    resume: bool = False,
) -> list[int]:
    query = CoOccurrenceTrainingBucket.objects.filter(
        training_run=training_run,
        bucket_count=bucket_count,
        bucket_index__gte=start_bucket,
    )
    if resume:
        query = query.exclude(status__in=['succeeded', 'assumed_succeeded'])
    return list(query.order_by('bucket_index').values_list('bucket_index', flat=True))


def mark_bucket_running(
    *,
    training_run_id: UUID,
    bucket_count: int,
    bucket_index: int,
) -> None:
    CoOccurrenceTrainingBucket.objects.filter(
        training_run_id=training_run_id,
        bucket_count=bucket_count,
        bucket_index=bucket_index,
    ).update(
        status='running',
        started_at=timezone.now(),
        completed_at=None,
        last_error='',
    )


def mark_bucket_succeeded(
    *,
    training_run_id: UUID,
    bucket_count: int,
    bucket_index: int,
    rows_written: int,
) -> None:
    CoOccurrenceTrainingBucket.objects.filter(
        training_run_id=training_run_id,
        bucket_count=bucket_count,
        bucket_index=bucket_index,
    ).update(
        status='succeeded',
        rows_written=rows_written,
        completed_at=timezone.now(),
        last_error='',
    )


def mark_bucket_failed(
    *,
    training_run_id: UUID,
    bucket_count: int,
    bucket_index: int,
    error: Exception,
) -> None:
    CoOccurrenceTrainingBucket.objects.filter(
        training_run_id=training_run_id,
        bucket_count=bucket_count,
        bucket_index=bucket_index,
    ).update(
        status='failed',
        completed_at=timezone.now(),
        last_error=str(error),
    )

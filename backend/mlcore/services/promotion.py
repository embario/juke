"""
Promotion gate enforcement + manual approval workflow (arch §9 Phase 1).

A candidate ranker may be promoted over a baseline only if it clears all four
gates AND a staff user explicitly approves. Gates read from ModelEvaluation;
decisions are recorded in ModelPromotion with full gate-result provenance.

Gate thresholds live in settings (JUKE_PROMOTION_GATE_*) so they can be tuned
per environment without code changes.

Lifecycle:
  request_promotion()  → creates ModelPromotion (status=pending or blocked)
  approve_promotion()  → pending → approved   (staff only, re-checks gates)
  reject_promotion()   → pending → rejected   (staff only)

blocked is terminal: a promotion blocked by gates must be re-requested after
new evaluation rows land — we never mutate gate_results on an existing row.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Callable

from django.conf import settings
from django.utils import timezone

from mlcore.models import ModelEvaluation, ModelPromotion
from mlcore.services.evaluation import (
    METRIC_COLD_RECALL,
    METRIC_COVERAGE,
    METRIC_NDCG,
    METRIC_RECALL,
)

logger = logging.getLogger(__name__)


class PromotionError(Exception):
    """Raised when a promotion transition is refused."""


@dataclass
class GateCheck:
    name: str
    passed: bool
    candidate_value: float | None
    baseline_value: float | None
    threshold: float
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


# --- metric fetching ---

def _latest_metric(label: str, metric_name: str, dataset_hash: str) -> float | None:
    """Most recent ModelEvaluation.metric_value for this (label, metric, dataset)."""
    row = (
        ModelEvaluation.objects
        .filter(candidate_label=label, metric_name=metric_name, dataset_hash=dataset_hash)
        .order_by('-created_at')
        .first()
    )
    return row.metric_value if row else None


def _latest_shared_dataset_hash(candidate_label: str, baseline_label: str) -> str | None:
    """
    Most recent dataset_hash that BOTH labels have been evaluated on.
    Comparing across different eval sets is meaningless.
    """
    cand_hashes = set(
        ModelEvaluation.objects
        .filter(candidate_label=candidate_label)
        .values_list('dataset_hash', flat=True)
    )
    if not cand_hashes:
        return None
    shared = (
        ModelEvaluation.objects
        .filter(candidate_label=baseline_label, dataset_hash__in=cand_hashes)
        .order_by('-created_at')
        .values_list('dataset_hash', flat=True)
        .first()
    )
    return shared


# --- gate primitives ---
#
# Each returns a GateCheck. They never raise — a missing metric is a failed gate
# with an explanatory message, not an exception.

def _check_relative_lift(
    name: str, metric: str, cand_label: str, base_label: str,
    dataset_hash: str, min_lift: float,
) -> GateCheck:
    cand = _latest_metric(cand_label, metric, dataset_hash)
    base = _latest_metric(base_label, metric, dataset_hash)
    if cand is None or base is None:
        missing = cand_label if cand is None else base_label
        return GateCheck(name, False, cand, base, min_lift,
                         f"no {metric} recorded for '{missing}' on dataset {dataset_hash[:12]}")
    if base == 0.0:
        # Relative lift undefined. Policy: any positive candidate clears; zero-vs-zero fails.
        passed = cand > 0.0
        lift_s = 'inf' if passed else '0.0'
    else:
        lift = (cand - base) / base
        passed = lift >= min_lift
        lift_s = f"{lift:+.4f}"
    msg = f"{metric}: cand={cand:.4f} base={base:.4f} lift={lift_s} (need >= {min_lift:+.4f})"
    return GateCheck(name, passed, cand, base, min_lift, msg)


def _check_max_regression(
    name: str, metric: str, cand_label: str, base_label: str,
    dataset_hash: str, max_regression: float,
) -> GateCheck:
    cand = _latest_metric(cand_label, metric, dataset_hash)
    base = _latest_metric(base_label, metric, dataset_hash)
    if cand is None or base is None:
        missing = cand_label if cand is None else base_label
        return GateCheck(name, False, cand, base, max_regression,
                         f"no {metric} recorded for '{missing}' on dataset {dataset_hash[:12]}")
    regression = base - cand  # positive = candidate got worse
    passed = regression <= max_regression
    msg = f"{metric}: cand={cand:.4f} base={base:.4f} regression={regression:+.4f} (max {max_regression:.4f})"
    return GateCheck(name, passed, cand, base, max_regression, msg)


def _check_absolute_floor(
    name: str, metric: str, cand_label: str,
    dataset_hash: str, floor: float,
) -> GateCheck:
    cand = _latest_metric(cand_label, metric, dataset_hash)
    if cand is None:
        return GateCheck(name, False, None, None, floor,
                         f"no {metric} recorded for '{cand_label}' on dataset {dataset_hash[:12]}")
    passed = cand >= floor
    msg = f"{metric}: cand={cand:.4f} (need >= {floor:.4f})"
    return GateCheck(name, passed, cand, None, floor, msg)


# Gate registry — declarative so Phase 2+ can add rows without touching the driver.
_GATES: list[tuple[str, Callable[[str, str, str], GateCheck]]] = [
    ('ndcg_lift', lambda c, b, h: _check_relative_lift(
        'ndcg_lift', METRIC_NDCG, c, b, h, settings.JUKE_PROMOTION_GATE_NDCG_MIN_LIFT)),
    ('recall_lift', lambda c, b, h: _check_relative_lift(
        'recall_lift', METRIC_RECALL, c, b, h, settings.JUKE_PROMOTION_GATE_RECALL_MIN_LIFT)),
    ('cold_start_regression', lambda c, b, h: _check_max_regression(
        'cold_start_regression', METRIC_COLD_RECALL, c, b, h,
        settings.JUKE_PROMOTION_GATE_COLDSTART_MAX_REGRESSION)),
    ('coverage_floor', lambda c, b, h: _check_absolute_floor(
        'coverage_floor', METRIC_COVERAGE, c, h, settings.JUKE_PROMOTION_GATE_COVERAGE_MIN)),
]


def check_promotion_gates(candidate_label: str, baseline_label: str, dataset_hash: str) -> list[GateCheck]:
    """Run all four gates. Returns every result — callers decide what to do with failures."""
    return [fn(candidate_label, baseline_label, dataset_hash) for _, fn in _GATES]


def gates_passed(checks: list[GateCheck]) -> bool:
    return all(c.passed for c in checks)


# --- workflow transitions ---

def request_promotion(
    candidate_label: str,
    baseline_label: str,
    dataset_hash: str | None = None,
) -> ModelPromotion:
    """
    Open a promotion request. Runs gates immediately and records results.

    If dataset_hash is omitted, uses the most recent hash both labels share.
    Resulting status is 'pending' if all gates pass, 'blocked' otherwise.
    """
    if dataset_hash is None:
        dataset_hash = _latest_shared_dataset_hash(candidate_label, baseline_label)
        if dataset_hash is None:
            raise PromotionError(
                f"no shared evaluation dataset for '{candidate_label}' and '{baseline_label}' — "
                f"run evaluate_recommenders on both first"
            )

    checks = check_promotion_gates(candidate_label, baseline_label, dataset_hash)
    passed = gates_passed(checks)
    failed_names = [c.name for c in checks if not c.passed]

    promo = ModelPromotion.objects.create(
        candidate_label=candidate_label,
        baseline_label=baseline_label,
        dataset_hash=dataset_hash,
        status='pending' if passed else 'blocked',
        gate_results={c.name: c.to_dict() for c in checks},
        block_reason='' if passed else f"gates failed: {', '.join(failed_names)}",
    )

    logger.info(
        'request_promotion candidate=%s baseline=%s dataset=%s status=%s failed=%s',
        candidate_label, baseline_label, dataset_hash[:12], promo.status, failed_names or 'none',
    )
    return promo


def approve_promotion(promotion: ModelPromotion, approver) -> ModelPromotion:
    """
    Transition pending → approved. Refuses unless:
      - approver.is_staff
      - status == 'pending'
      - gates still pass (re-checked — ModelEvaluation rows may have changed
        since request_promotion() ran)
    """
    if not getattr(approver, 'is_staff', False):
        raise PromotionError(f"approver '{approver}' is not staff")
    if promotion.status != 'pending':
        raise PromotionError(
            f"cannot approve promotion in status '{promotion.status}' (need 'pending')"
        )

    # Re-run gates against current ModelEvaluation state. If a newer eval row
    # landed and regressed a metric, the stored gate_results are stale.
    checks = check_promotion_gates(
        promotion.candidate_label, promotion.baseline_label, promotion.dataset_hash,
    )
    if not gates_passed(checks):
        failed = [c.name for c in checks if not c.passed]
        promotion.status = 'blocked'
        promotion.gate_results = {c.name: c.to_dict() for c in checks}
        promotion.block_reason = f"gates failed at approval time: {', '.join(failed)}"
        promotion.save(update_fields=['status', 'gate_results', 'block_reason'])
        raise PromotionError(promotion.block_reason)

    promotion.status = 'approved'
    promotion.approved_by = approver
    promotion.approved_at = timezone.now()
    promotion.gate_results = {c.name: c.to_dict() for c in checks}
    promotion.save(update_fields=['status', 'approved_by', 'approved_at', 'gate_results'])

    logger.info(
        'approve_promotion id=%s candidate=%s approver=%s',
        promotion.id, promotion.candidate_label, approver,
    )
    return promotion


def reject_promotion(promotion: ModelPromotion, approver, reason: str) -> ModelPromotion:
    """Transition pending → rejected. Staff only. Records reason in block_reason."""
    if not getattr(approver, 'is_staff', False):
        raise PromotionError(f"approver '{approver}' is not staff")
    if promotion.status != 'pending':
        raise PromotionError(
            f"cannot reject promotion in status '{promotion.status}' (need 'pending')"
        )

    promotion.status = 'rejected'
    promotion.approved_by = approver  # records who made the decision
    promotion.approved_at = timezone.now()
    promotion.block_reason = reason
    promotion.save(update_fields=['status', 'approved_by', 'approved_at', 'block_reason'])

    logger.info('reject_promotion id=%s reason=%s', promotion.id, reason)
    return promotion

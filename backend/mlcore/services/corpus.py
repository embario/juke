"""
Fail-closed corpus governance (arch §3.2 + §6).

Production mode admits only manifest rows whose source is classified
`production_approved` AND whose `allowed_envs` includes production.
Unknown sources and missing license metadata are rejected.
"""
import logging
from dataclasses import dataclass

from django.conf import settings
from django.db.models import QuerySet

from mlcore.models import CorpusManifest

logger = logging.getLogger(__name__)

# Source classification registry.
# Initial policy: MusicBrainz-only for production (per task spec).
SOURCE_CLASSIFICATION: dict[str, str] = {
    'musicbrainz': 'production_approved',
}


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    classification: str


def _approved_sources() -> list[str]:
    return [s for s, c in SOURCE_CLASSIFICATION.items() if c == 'production_approved']


class LicensePolicy:

    def __init__(self, allowed_licenses: str | None = None, fail_closed: bool | None = None):
        self.allowed_licenses = allowed_licenses or settings.JUKE_ALLOWED_LICENSES
        self.fail_closed = fail_closed if fail_closed is not None else settings.JUKE_LICENSE_FAIL_CLOSED

    def classify_source(self, source: str) -> str:
        return SOURCE_CLASSIFICATION.get(source, 'blocked' if self.fail_closed else 'research_only')

    def evaluate(self, row: CorpusManifest) -> PolicyDecision:
        # Fail-closed: missing/unknown metadata → reject.
        if not row.license:
            return PolicyDecision(False, 'missing license metadata', 'blocked')
        if not row.allowed_envs:
            return PolicyDecision(False, 'missing allowed_envs', 'blocked')

        classification = self.classify_source(row.source)
        if classification == 'blocked':
            return PolicyDecision(False, f"source '{row.source}' not approved", classification)

        if self.allowed_licenses == 'production':
            if classification != 'production_approved':
                return PolicyDecision(False, f"source '{row.source}' not production_approved", classification)
            if row.allowed_envs not in ('production', 'both'):
                return PolicyDecision(False, f"row env '{row.allowed_envs}' excludes production", classification)
        elif self.allowed_licenses == 'research':
            if row.allowed_envs not in ('research', 'both'):
                return PolicyDecision(False, f"row env '{row.allowed_envs}' excludes research", classification)

        return PolicyDecision(True, 'compliant', classification)

    def eligible_queryset(self) -> QuerySet[CorpusManifest]:
        """Manifest rows that pass policy for the current license mode."""
        qs = CorpusManifest.objects.exclude(license='').exclude(license__isnull=True)
        if self.allowed_licenses == 'production':
            qs = qs.filter(source__in=_approved_sources(), allowed_envs__in=['production', 'both'])
        elif self.allowed_licenses == 'research':
            qs = qs.filter(allowed_envs__in=['research', 'both'])
            if self.fail_closed:
                # fail-closed still excludes unknown sources entirely
                qs = qs.filter(source__in=list(SOURCE_CLASSIFICATION.keys()))
        # 'both' mode admits all rows with valid license metadata
        return qs

    def is_model_promotable(self, training_corpus_rows: QuerySet[CorpusManifest]) -> tuple[bool, str]:
        """
        Promotion guard: models trained with any non-production_approved or
        research-only row cannot be activated in production.
        """
        approved = _approved_sources()
        bad_source = training_corpus_rows.exclude(source__in=approved)
        if bad_source.exists():
            reason = f"training corpus includes {bad_source.count()} non-production_approved row(s)"
            logger.warning("Promotion blocked: %s", reason)
            return False, reason

        bad_env = training_corpus_rows.exclude(allowed_envs__in=['production', 'both'])
        if bad_env.exists():
            reason = f"training corpus includes {bad_env.count()} research-only row(s)"
            logger.warning("Promotion blocked: %s", reason)
            return False, reason

        return True, "all training rows production-compliant"

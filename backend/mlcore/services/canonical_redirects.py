from __future__ import annotations

from uuid import UUID

from django.db import transaction, connection

from mlcore.services.identity_safety import stage_holds

from mlcore.models import CanonicalItemRedirect

MAX_REDIRECT_DEPTH = 8


def resolve_canonical_item_id(item_id: UUID, *, max_depth: int = MAX_REDIRECT_DEPTH) -> UUID:
    current = UUID(str(item_id))
    visited = {current}
    for _ in range(max_depth):
        redirect = CanonicalItemRedirect.objects.filter(
            from_canonical_item_id=current,
            status='active',
        ).only('to_canonical_item_id').first()
        if redirect is None:
            return current
        target = redirect.to_canonical_item_id
        if target in visited:
            raise ValueError(f'Canonical redirect cycle detected at {target}')
        visited.add(target)
        current = target
    raise ValueError(f'Canonical redirect depth exceeds {max_depth}')


@transaction.atomic
def upsert_canonical_redirect(
    *,
    from_item_id: UUID,
    to_item_id: UUID,
    source: str,
    source_version: str,
    confidence: float = 1.0,
    evidence: dict | None = None,
) -> CanonicalItemRedirect:
    source_id = UUID(str(from_item_id))
    target_id = UUID(str(to_item_id))
    if source_id == target_id:
        raise ValueError('Canonical item cannot redirect to itself')
    resolved_target = resolve_canonical_item_id(target_id)
    if resolved_target == source_id:
        raise ValueError('Canonical redirect would create a cycle')

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext('mlcore-canonical-alias-materialization'))")
    stage_holds(subjects=True)
    with connection.cursor() as cursor:
        cursor.execute('''SELECT EXISTS(SELECT 1 FROM tmp_identity_held_subject
            WHERE item_id IN (%s, %s) OR final_id = %s)''', [source_id, target_id, source_id])
        if cursor.fetchone()[0]:
            raise ValueError('Canonical redirect uses quarantined identity evidence')

    redirect = CanonicalItemRedirect.objects.select_for_update().filter(
        from_canonical_item_id=source_id,
    ).first()
    if redirect is None:
        return CanonicalItemRedirect.objects.create(
            from_canonical_item_id=source_id,
            to_canonical_item_id=target_id,
            source=source,
            source_version=source_version,
            confidence=confidence,
            status='active',
            evidence=evidence or {},
        )
    if redirect.status != 'active':
        return redirect
    if redirect.to_canonical_item_id != target_id:
        redirect.status = 'conflict'
        redirect.evidence = {
            **redirect.evidence,
            'conflicting_target_id': str(target_id),
            'conflicting_source': source,
            'conflicting_source_version': source_version,
        }
        redirect.save(update_fields=['status', 'evidence', 'updated_at'])
        return redirect

    redirect.status = 'active'
    redirect.source = source
    redirect.source_version = source_version
    redirect.confidence = confidence
    redirect.evidence = evidence or {}
    redirect.save(update_fields=[
        'status',
        'source',
        'source_version',
        'confidence',
        'evidence',
        'updated_at',
    ])
    return redirect

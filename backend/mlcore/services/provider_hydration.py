import base64
import math
import random
import socket
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import requests
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from mlcore.models import (
    CanonicalItemAlias,
    ListenBrainzSessionTrack,
    ProviderHydrationItem,
    ProviderHydrationRun,
)


SPOTIFY_TOKEN_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_SEARCH_URL = 'https://api.spotify.com/v1/search'
SPOTIFY_WORKER_LOCK_ID = 0x4A554B4553504F54
TERMINAL_STATUSES = {'matched', 'no_match', 'ambiguous', 'dead'}


class ProviderHydrationError(Exception):
    def __init__(self, message, *, http_status=None, retry_after=None, retryable=True, reason=''):
        super().__init__(message)
        self.http_status = http_status
        self.retry_after = retry_after
        self.retryable = retryable
        self.reason = reason


@dataclass(frozen=True)
class SpotifyCandidate:
    track_id: str
    uri: str
    isrc: str
    name: str
    artists: tuple[str, ...]
    duration_ms: int | None
    popularity: int | None

    def evidence(self):
        return {
            'track_id': self.track_id,
            'uri': self.uri,
            'isrc': self.isrc,
            'name': self.name,
            'artists': list(self.artists),
            'duration_ms': self.duration_ms,
            'popularity': self.popularity,
        }


@dataclass(frozen=True)
class IncrementalSeedResult:
    scanned: int
    created: int
    next_cursor: str
    pass_complete: bool


@dataclass(frozen=True)
class PriorityRescoreResult:
    scanned: int
    updated: int
    next_cursor: int
    pass_complete: bool


@dataclass(frozen=True)
class ReconciliationResult:
    stale_runs: int
    reclaimed_items: int


def normalize_isrc(value):
    return ''.join(character for character in str(value or '').upper() if character.isalnum())


class SpotifyClient:
    def __init__(self, client_id, client_secret, *, session=None, timeout=None):
        if not client_id or not client_secret:
            raise ValueError('Spotify client credentials are required.')
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = session or requests.Session()
        self.timeout = timeout or settings.SPOTIFY_HYDRATION_REQUEST_TIMEOUT_SECONDS
        self._token = None
        self._token_expires_at = 0.0

    def _access_token(self, *, force=False):
        if not force and self._token and time.monotonic() < self._token_expires_at - 60:
            return self._token
        credentials = base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode()).decode()
        try:
            response = self.session.post(
                SPOTIFY_TOKEN_URL,
                headers={'Authorization': f'Basic {credentials}'},
                data={'grant_type': 'client_credentials'},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ProviderHydrationError(f'Spotify token request failed: {exc}') from exc
        if response.status_code >= 400:
            retry_after = (
                _retry_after_seconds(response.headers.get('Retry-After'))
                if response.status_code == 429
                else None
            )
            raise ProviderHydrationError(
                f'Spotify token request returned HTTP {response.status_code}',
                http_status=response.status_code,
                retry_after=retry_after,
                retryable=response.status_code >= 500 or response.status_code == 429,
                reason=_spotify_error_reason(response),
            )
        payload = response.json()
        self._token = payload['access_token']
        self._token_expires_at = time.monotonic() + int(payload.get('expires_in') or 3600)
        return self._token

    def search_isrc(self, isrc):
        normalized = normalize_isrc(isrc)
        response = self._search(normalized)
        if response.status_code == 401:
            response = self._search(normalized, force_token=True)
        if response.status_code == 429:
            retry_after = _retry_after_seconds(response.headers.get('Retry-After'))
            reason = _spotify_error_reason(response)
            raise ProviderHydrationError(
                f'Spotify rate limit reached{f": {reason}" if reason else "."}',
                http_status=429,
                retry_after=retry_after,
                reason=reason,
            )
        if response.status_code >= 500:
            raise ProviderHydrationError(
                f'Spotify search returned HTTP {response.status_code}',
                http_status=response.status_code,
            )
        if response.status_code >= 400:
            raise ProviderHydrationError(
                f'Spotify search returned HTTP {response.status_code}',
                http_status=response.status_code,
                retryable=False,
            )
        items = response.json().get('tracks', {}).get('items', [])
        return [candidate for item in items if (candidate := _candidate_from_item(item, normalized))]

    def _search(self, isrc, *, force_token=False):
        try:
            return self.session.get(
                SPOTIFY_SEARCH_URL,
                headers={'Authorization': f'Bearer {self._access_token(force=force_token)}'},
                params={'q': f'isrc:{isrc}', 'type': 'track', 'limit': 10},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ProviderHydrationError(f'Spotify search failed: {exc}') from exc


class RequestPacer:
    """Single-worker global pacing with additive recovery and multiplicative decrease."""

    def __init__(self, rps, *, sleep=time.sleep, monotonic=time.monotonic, jitter=random.uniform, recover=True):
        if rps <= 0:
            raise ValueError('rps must be greater than zero')
        self.recover = recover
        self.configured_rps = float(rps)
        self.current_rps = float(rps)
        self.sleep = sleep
        self.monotonic = monotonic
        self.jitter = jitter
        self._next_request_at = 0.0
        self._successes_since_limit = 0

    def wait(self):
        now = self.monotonic()
        if self._next_request_at > now:
            self.sleep(self._next_request_at - now)
        self._next_request_at = self.monotonic() + (1.0 / self.current_rps)

    def success(self):
        self._successes_since_limit += 1
        if self.recover and self._successes_since_limit >= 300 and self.current_rps < self.configured_rps:
            self.current_rps = min(self.configured_rps, self.current_rps + 0.1)
            self._successes_since_limit = 0

    def set_rate(self, rps):
        """Adopt a rate chosen by ``AdaptiveRateController``; the next gap uses it."""
        self.current_rps = max(0.001, float(rps))

    def rate_limited(self, retry_after):
        self.current_rps = max(0.001, self.current_rps / 2.0)
        self._successes_since_limit = 0
        delay = max(1.0, float(retry_after or 30)) + self.jitter(0.25, 1.25)
        self._next_request_at = self.monotonic() + delay


class AdaptiveRateController:
    """Learns a safe sustained request rate for the dedicated hydration app.

    Additive increase after a quiet period without 429/5xx, multiplicative decrease on a 429 or a
    streak of 5xx. The learned rate is kept in run metadata so a restart resumes from it. It only
    ramps when an operator sets ``SPOTIFY_HYDRATION_MAX_RPS``; otherwise ``adaptive`` is False and the
    rate stays whatever ``RequestPacer`` does today. The budget cap stays the hard ceiling.
    """

    metadata_key = 'spotify_hydration_rate'

    def __init__(
        self,
        *,
        floor_rps,
        ceiling_rps,
        start_rps,
        adaptive,
        step_rps=0.01,
        ramp_interval_seconds=600.0,
        decrease_factor=0.5,
        server_error_streak=5,
        server_error_decrease_factor=0.75,
        now=time.time,
    ):
        self.adaptive = bool(adaptive)
        self.ceiling_rps = max(0.001, float(ceiling_rps))
        self.floor_rps = min(max(0.001, float(floor_rps)), self.ceiling_rps)
        self.start_rps = min(max(float(start_rps), self.floor_rps), self.ceiling_rps)
        self.step_rps = max(0.0, float(step_rps))
        self.ramp_interval_seconds = max(1.0, float(ramp_interval_seconds))
        self.decrease_factor = min(max(float(decrease_factor), 0.05), 1.0)
        self.server_error_streak = max(1, int(server_error_streak))
        self.server_error_decrease_factor = min(max(float(server_error_decrease_factor), 0.05), 1.0)
        self.now = now

    @classmethod
    def from_settings(cls, quota_guard, requested_rps, *, now=time.time):
        today = quota_guard.effective_rps(requested_rps)
        max_rps = float(settings.SPOTIFY_HYDRATION_MAX_RPS)
        adaptive = max_rps > 0
        ceiling = today
        if adaptive:
            ceiling = min(max_rps, quota_guard.request_budget / quota_guard.window_seconds) \
                if quota_guard.request_budget > 0 else max_rps
        return cls(
            floor_rps=settings.SPOTIFY_HYDRATION_MIN_RPS or 0.001,
            ceiling_rps=ceiling,
            start_rps=today,
            adaptive=adaptive,
            step_rps=settings.SPOTIFY_HYDRATION_RAMP_STEP_RPS,
            ramp_interval_seconds=settings.SPOTIFY_HYDRATION_RAMP_INTERVAL_SECONDS,
            server_error_streak=settings.SPOTIFY_HYDRATION_SERVER_ERROR_STREAK,
            now=now,
        )

    def initial_state(self, previous_metadata=None):
        previous = (previous_metadata or {}).get(self.metadata_key) or {}
        learned = _safe_float(previous.get('learned_rps'), self.start_rps) if self.adaptive else self.start_rps
        now = self.now()
        return {
            'learned_rps': min(max(learned, self.floor_rps), self.ceiling_rps),
            'floor_rps': self.floor_rps,
            'ceiling_rps': self.ceiling_rps,
            'adaptive': self.adaptive,
            'last_change_at': now,
            'consecutive_server_errors': 0,
            'rate_limited_total': 0,
            'server_error_total': 0,
        }

    def rps(self, run):
        return self._state(run)['learned_rps']

    def success(self, run):
        state = self._state(run)
        state['consecutive_server_errors'] = 0
        if not self.adaptive or state['learned_rps'] >= self.ceiling_rps:
            return False
        now = self.now()
        if now - state['last_change_at'] < self.ramp_interval_seconds:
            return False
        state['learned_rps'] = min(self.ceiling_rps, state['learned_rps'] + self.step_rps)
        state['last_change_at'] = now
        self._persist(run, state)
        return True

    def rate_limited(self, run):
        state = self._state(run)
        state['rate_limited_total'] += 1
        state['consecutive_server_errors'] = 0
        self._decrease(state, self.decrease_factor)
        self._persist(run, state)

    def server_error(self, run):
        state = self._state(run)
        state['server_error_total'] += 1
        state['consecutive_server_errors'] += 1
        if state['consecutive_server_errors'] >= self.server_error_streak:
            state['consecutive_server_errors'] = 0
            self._decrease(state, self.server_error_decrease_factor)
        self._persist(run, state)

    def _decrease(self, state, factor):
        if self.adaptive:
            state['learned_rps'] = max(self.floor_rps, state['learned_rps'] * factor)
        state['last_change_at'] = self.now()

    def _state(self, run):
        state = run.metadata.get(self.metadata_key)
        if state is None:
            state = self.initial_state()
            run.metadata = {**run.metadata, self.metadata_key: state}
        return state

    def _persist(self, run, state):
        run.metadata = {**run.metadata, self.metadata_key: state}
        run.save(update_fields=['metadata', 'updated_at'])


class SpotifyHydrationQuotaGuard:
    """Persistent bulk-request budget and provider-directed cooldown state."""

    metadata_key = 'spotify_hydration_quota'

    def __init__(self, request_budget, window_seconds, *, now=time.time):
        self.request_budget = max(0, int(request_budget))
        self.window_seconds = max(1.0, float(window_seconds))
        self.now = now

    def effective_rps(self, requested_rps):
        if self.request_budget <= 0:
            return float(requested_rps)
        return min(float(requested_rps), self.request_budget / self.window_seconds)

    def initial_state(self, previous_metadata=None):
        now = self.now()
        previous = (previous_metadata or {}).get(self.metadata_key) or {}
        window_started_at = _safe_float(previous.get('window_started_at'), now)
        used = max(0.0, _safe_float(previous.get('requests_used'), 0.0))
        if now >= window_started_at + self.window_seconds:
            window_started_at = now
            used = 0
        return {
            'window_started_at': window_started_at,
            'requests_used': used,
            'request_budget': self.request_budget,
            'window_seconds': self.window_seconds,
            'cooldown_until': max(0.0, _safe_float(previous.get('cooldown_until'), 0.0)),
            'last_limit_reason': str(previous.get('last_limit_reason') or ''),
        }

    def delay_seconds(self, run):
        state = self._state(run)
        now = self.now()
        changed = False
        if now >= state['window_started_at'] + self.window_seconds:
            state['window_started_at'] = now
            state['requests_used'] = 0
            changed = True
        cooldown_delay = max(0.0, state['cooldown_until'] - now)
        budget_delay = 0.0
        if self.request_budget > 0 and state['requests_used'] >= self.request_budget:
            budget_delay = max(0.0, state['window_started_at'] + self.window_seconds - now)
        if changed:
            self._persist(run, state)
        return max(cooldown_delay, budget_delay)

    def record_request(self, run):
        state = self._state(run)
        state['requests_used'] += 1
        self._persist(run, state)

    def refund_request(self, run, *, charged_weight):
        """Give back the unused part of a request's charge (provider 5xx are charged at a reduced weight)."""
        state = self._state(run)
        state['requests_used'] = max(0.0, state['requests_used'] - max(0.0, 1.0 - float(charged_weight)))
        self._persist(run, state)

    def rate_limited(self, run, *, retry_after, reason=''):
        state = self._state(run)
        state['cooldown_until'] = max(
            state['cooldown_until'],
            self.now() + max(1.0, float(retry_after or 30)),
        )
        state['last_limit_reason'] = str(reason or '')
        self._persist(run, state)

    def _state(self, run):
        state = run.metadata.get(self.metadata_key)
        if state is None:
            state = self.initial_state()
            run.metadata = {**run.metadata, self.metadata_key: state}
        return state

    def _persist(self, run, state):
        run.metadata = {**run.metadata, self.metadata_key: state}
        run.save(update_fields=['metadata', 'updated_at'])


# Queue order is ``ORDER BY priority, id`` (lower claims first). Unscored items keep the model default of 100;
# items with listen evidence are placed in 1..99 so they always claim first, most-listened lowest.
UNSCORED_PRIORITY = 100
PRIORITY_SCALE = 12.0


def priority_for_popularity(popularity):
    """Map a damped listen score (>= 0) to a queue priority in 1..100; 0 means no evidence."""
    if popularity <= 0:
        return UNSCORED_PRIORITY
    bucket = min(UNSCORED_PRIORITY - 2, int(round(PRIORITY_SCALE * math.log1p(popularity))))
    return UNSCORED_PRIORITY - 1 - bucket


def listen_popularity(canonical_item_ids):
    """Listen score per canonical item: the number of distinct listening sessions that played it.

    Counting sessions, not plays, damps one listener's binge (it stays inside a session or two).
    ``play_count`` is deliberately not read: on the live corpus (~1.4B rows) that forces a heap fetch
    per row and made the same lookup about 8x slower (read-only measurement on Neptune), while the
    session count alone is an index-only scan on ``canonical_item_id``. Items without evidence are
    absent from the result.
    """
    ids = list(canonical_item_ids)
    if not ids:
        return {}
    rows = (
        ListenBrainzSessionTrack.objects.filter(canonical_item_id__in=ids)
        .order_by()
        .values('canonical_item_id')
        .annotate(sessions=Count('id'))
    )
    return {row['canonical_item_id']: float(row['sessions']) for row in rows}


def rescore_pending_priorities(*, after_id=0, batch_size=2_000, boosts=None):
    """Re-score one bounded slice of pending/retry items and move the cursor.

    Touches only rows whose priority actually changes, in one short transaction of at most
    ``batch_size`` rows. It never locks the table, and ``claim_hydration_item`` uses
    ``SKIP LOCKED`` so it passes over any row this pass is holding. Running, matched and
    terminal rows are left alone. At the end of a pass the cursor resets to 0. ``boosts`` maps
    canonical item ids to a fixed priority (items users reference, see ``hydration_boosts``) that
    replaces the listen-score priority, so a re-score never undoes a boost.
    """
    if batch_size < 1:
        raise ValueError('batch_size must be greater than zero')
    rows = list(
        ProviderHydrationItem.objects.filter(provider='spotify', status__in=['pending', 'retry'], id__gt=after_id)
        .order_by('id')
        .values_list('id', 'canonical_item_id', 'priority')[:batch_size]
    )
    popularity = listen_popularity({canonical_item_id for _id, canonical_item_id, _priority in rows})
    changes = {}
    for item_id, canonical_item_id, current in rows:
        wanted = (boosts or {}).get(canonical_item_id)
        if wanted is None:
            wanted = priority_for_popularity(popularity.get(canonical_item_id, 0.0))
        if wanted != current:
            changes[item_id] = wanted
    updated = 0
    if changes:
        with transaction.atomic():
            items = list(
                ProviderHydrationItem.objects.select_for_update(skip_locked=True)
                .filter(id__in=changes, status__in=['pending', 'retry'])
                .only('id', 'priority')
            )
            for item in items:
                item.priority = changes[item.id]
            ProviderHydrationItem.objects.bulk_update(items, ['priority'])
            updated = len(items)
    pass_complete = len(rows) < batch_size
    return PriorityRescoreResult(
        scanned=len(rows),
        updated=updated,
        next_cursor=0 if pass_complete else rows[-1][0],
        pass_complete=pass_complete,
    )


def seed_spotify_hydration_queue(*, batch_size=10_000, limit=None):
    spotify_on_item = CanonicalItemAlias.objects.filter(
        canonical_item_id=OuterRef('canonical_item_id'),
        source='spotify',
        resource_type='track',
        status='active',
    )
    queryset = (
        CanonicalItemAlias.objects.filter(source='isrc', resource_type='recording', status='active')
        .annotate(has_spotify=Exists(spotify_on_item))
        .filter(has_spotify=False)
        .order_by('source_id')
        .values_list('canonical_item_id', 'source_id', 'source_version')
    )
    if limit is not None:
        queryset = queryset[:limit]
    created = 0
    rows = []
    for canonical_item_id, isrc, source_version in queryset.iterator(chunk_size=batch_size):
        rows.append((canonical_item_id, isrc, source_version))
        if len(rows) >= batch_size:
            created += _create_spotify_hydration_items(rows)
            rows = []
    if rows:
        created += _create_spotify_hydration_items(rows)
    return created


def seed_spotify_hydration_queue_incrementally(*, after_source_id='', scan_limit=10_000):
    """Scan one bounded, resumable slice of active ISRC aliases.

    The cursor is the source ID from the last scanned alias, not the last inserted
    queue row. This lets each pass move across aliases that were already queued
    without repeatedly performing a full-corpus anti-join. At the end of a pass the
    cursor resets, so aliases inserted behind the cursor are picked up next time.
    """
    if scan_limit < 1:
        raise ValueError('scan_limit must be greater than zero')
    spotify_on_item = CanonicalItemAlias.objects.filter(
        canonical_item_id=OuterRef('canonical_item_id'),
        source='spotify',
        resource_type='track',
        status='active',
    )
    aliases = list(
        CanonicalItemAlias.objects.filter(
            source='isrc',
            resource_type='recording',
            status='active',
            source_id__gt=after_source_id,
        )
        .annotate(has_spotify=Exists(spotify_on_item))
        .filter(has_spotify=False)
        .order_by('source_id')
        .values_list('canonical_item_id', 'source_id', 'source_version')[:scan_limit]
    )
    created = _create_spotify_hydration_items(aliases)
    pass_complete = len(aliases) < scan_limit
    return IncrementalSeedResult(
        scanned=len(aliases),
        created=created,
        next_cursor='' if pass_complete else aliases[-1][1],
        pass_complete=pass_complete,
    )


def reconcile_stale_hydration_state(*, provider, reconciled_by):
    """Fail orphaned runs and reclaim queue leases while holding the provider lock.

    The caller must own the provider's singleton advisory lock. That proves there is
    no live worker for this provider, so every remaining ``running`` row is stale,
    including leases whose expiry is still a few seconds in the future.
    """
    now = timezone.now()
    stale_runs = list(ProviderHydrationRun.objects.filter(provider=provider, status='running'))
    reclaimed_items = ProviderHydrationItem.objects.filter(
        provider=provider,
        status='running',
    ).update(
        status='pending',
        leased_by='',
        lease_expires_at=None,
        next_attempt_at=None,
        last_error='Reclaimed after the previous hydration worker stopped.',
        updated_at=now,
    )
    for stale_run in stale_runs:
        stale_run.status = 'failed'
        stale_run.completed_at = now
        stale_run.last_error = 'Reconciled as stale: no hydration worker held the provider lease.'
        stale_run.metadata = {
            **stale_run.metadata,
            'reconciled_at': now.isoformat(),
            'reconciled_by': reconciled_by,
        }
        stale_run.save(update_fields=['status', 'completed_at', 'last_error', 'metadata', 'updated_at'])
    return ReconciliationResult(stale_runs=len(stale_runs), reclaimed_items=reclaimed_items)


def _create_spotify_hydration_items(alias_rows):
    candidates = {}
    for canonical_item_id, isrc, source_version in alias_rows:
        identifier = normalize_isrc(isrc)
        if identifier:
            candidates.setdefault(identifier, (canonical_item_id, source_version))
    if not candidates:
        return 0
    existing = set(
        ProviderHydrationItem.objects.filter(
            provider='spotify',
            identifier_type='isrc',
            identifier__in=candidates,
        ).values_list('identifier', flat=True)
    )
    new_candidates = {
        identifier: values for identifier, values in candidates.items() if identifier not in existing
    }
    popularity = listen_popularity({canonical_item_id for canonical_item_id, _version in new_candidates.values()})
    rows = [
        ProviderHydrationItem(
            canonical_item_id=canonical_item_id,
            provider='spotify',
            identifier_type='isrc',
            identifier=identifier,
            source_version=source_version,
            priority=priority_for_popularity(popularity.get(canonical_item_id, 0.0)),
        )
        for identifier, (canonical_item_id, source_version) in new_candidates.items()
    ]
    ProviderHydrationItem.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


def claim_hydration_item(*, run, worker_id, lease_seconds=120):
    now = timezone.now()
    with transaction.atomic():
        item = (
            ProviderHydrationItem.objects.select_for_update(skip_locked=True)
            .filter(provider=run.provider)
            .filter(Q(status__in=['pending', 'retry']) | Q(status='running', lease_expires_at__lt=now))
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .order_by('priority', 'id')
            .first()
        )
        if item is None:
            return None
        item.status = 'running'
        item.leased_by = worker_id
        item.lease_expires_at = now + timedelta(seconds=lease_seconds)
        item.last_run = run
        item.save(update_fields=['status', 'leased_by', 'lease_expires_at', 'last_run', 'updated_at'])
        return item


def hydrate_spotify_item(item, *, run, client):
    item.attempt_count += 1
    run.attempted_count += 1
    run.request_count += 1
    try:
        candidates = client.search_isrc(item.identifier)
        evidence = {'query_isrc': item.identifier, 'candidates': [candidate.evidence() for candidate in candidates]}
        if not candidates:
            _finish_item(item, status='no_match', evidence=evidence)
            run.no_match_count += 1
            return 'no_match'
        if len(candidates) != 1:
            _finish_item(item, status='ambiguous', evidence=evidence)
            run.ambiguous_count += 1
            return 'ambiguous'
        candidate = candidates[0]
        existing = CanonicalItemAlias.objects.filter(
            source='spotify', resource_type='track', source_id=candidate.track_id,
        ).first()
        if existing is not None and existing.canonical_item_id != item.canonical_item_id:
            evidence['conflict_canonical_item_id'] = str(existing.canonical_item_id)
            _finish_item(item, status='ambiguous', evidence=evidence)
            run.ambiguous_count += 1
            return 'ambiguous'
        CanonicalItemAlias.objects.update_or_create(
            source='spotify',
            resource_type='track',
            source_id=candidate.track_id,
            defaults={
                'canonical_item_id': item.canonical_item_id,
                'confidence': 1.0,
                'source_version': 'spotify-search-v1',
                'status': 'active',
                'metadata': {
                    'spotify_uri': candidate.uri,
                    'match_source': 'isrc',
                    'match_isrc': item.identifier,
                    'evidence': candidate.evidence(),
                },
            },
        )
        _finish_item(item, status='matched', evidence=evidence)
        run.matched_count += 1
        return 'matched'
    except ProviderHydrationError as exc:
        item.last_http_status = exc.http_status
        item.last_error = str(exc)
        item.evidence = {**item.evidence, 'retry_after_seconds': exc.retry_after}
        if exc.http_status == 429:
            run.rate_limited_count += 1
        if exc.retryable and item.attempt_count < settings.SPOTIFY_HYDRATION_MAX_ATTEMPTS:
            item.status = 'retry'
            delay = max(float(exc.retry_after or 0), min(3600, 2 ** item.attempt_count))
            item.next_attempt_at = timezone.now() + timedelta(seconds=delay + random.uniform(0, delay * 0.25))
            run.retry_count += 1
        else:
            item.status = 'dead'
            item.next_attempt_at = None
            run.dead_count += 1
        item.leased_by = ''
        item.lease_expires_at = None
        item.save()
        raise
    finally:
        run.save()


def spotify_worker_lock():
    return _PostgresAdvisoryLock(SPOTIFY_WORKER_LOCK_ID)


class _PostgresAdvisoryLock:
    def __init__(self, lock_id):
        self.lock_id = lock_id
        self.acquired = False

    def __enter__(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s)', [self.lock_id])
            self.acquired = bool(cursor.fetchone()[0])
        return self.acquired

    def __exit__(self, exc_type, exc, traceback):
        if self.acquired:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_unlock(%s)', [self.lock_id])


def write_hydration_metrics(run, *, path, backlog=None):
    elapsed = max((timezone.now() - run.started_at).total_seconds(), 0.001)
    throughput = run.attempted_count / elapsed
    backlog = backlog if backlog is not None else ProviderHydrationItem.objects.filter(
        provider=run.provider, status__in=['pending', 'retry', 'running'],
    ).count()
    eta = backlog / throughput if throughput > 0 else 0
    labels = f'provider="{run.provider}",run_id="{run.id}"'
    lines = [
        f'mlcore_provider_hydration_backlog{{{labels}}} {backlog}',
        f'mlcore_provider_hydration_attempted_total{{{labels}}} {run.attempted_count}',
        f'mlcore_provider_hydration_matched_total{{{labels}}} {run.matched_count}',
        f'mlcore_provider_hydration_no_match_total{{{labels}}} {run.no_match_count}',
        f'mlcore_provider_hydration_ambiguous_total{{{labels}}} {run.ambiguous_count}',
        f'mlcore_provider_hydration_rate_limited_total{{{labels}}} {run.rate_limited_count}',
        f'mlcore_provider_hydration_throughput_per_second{{{labels}}} {throughput:.8f}',
        f'mlcore_provider_hydration_eta_seconds{{{labels}}} {eta:.3f}',
    ]
    rate = run.metadata.get(AdaptiveRateController.metadata_key) or {}
    quota = run.metadata.get(SpotifyHydrationQuotaGuard.metadata_key) or {}
    lines += [
        f'mlcore_provider_hydration_learned_rps{{{labels}}} {_safe_float(rate.get("learned_rps"), 0.0):.6f}',
        f'mlcore_provider_hydration_rate_ceiling_rps{{{labels}}} {_safe_float(rate.get("ceiling_rps"), 0.0):.6f}',
        f'mlcore_provider_hydration_adaptive{{{labels}}} {int(bool(rate.get("adaptive")))}',
        f'mlcore_provider_hydration_server_error_total{{{labels}}} {_safe_int(rate.get("server_error_total"), 0)}',
        f'mlcore_provider_hydration_budget_used{{{labels}}} {_safe_float(quota.get("requests_used"), 0.0):.3f}',
        f'mlcore_provider_hydration_budget_limit{{{labels}}} {_safe_int(quota.get("request_budget"), 0)}',
    ]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_text('\n'.join(lines) + '\n', encoding='ascii')
    temporary.replace(target)


def _candidate_from_item(item, expected_isrc):
    actual_isrc = normalize_isrc((item.get('external_ids') or {}).get('isrc'))
    track_id = str(item.get('id') or '').strip()
    if actual_isrc != expected_isrc or not track_id:
        return None
    return SpotifyCandidate(
        track_id=track_id,
        uri=str(item.get('uri') or f'spotify:track:{track_id}'),
        isrc=actual_isrc,
        name=str(item.get('name') or ''),
        artists=tuple(str(artist.get('name') or '') for artist in item.get('artists') or []),
        duration_ms=item.get('duration_ms'),
        popularity=item.get('popularity'),
    )


def _retry_after_seconds(value):
    try:
        return max(1.0, float(value))
    except (TypeError, ValueError):
        return 30.0


def _spotify_error_reason(response):
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return ''
    error = payload.get('error') if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get('reason') or '')
    return str(payload.get('reason') or '') if isinstance(payload, dict) else ''


def _safe_float(value, fallback):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)


def _safe_int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def _finish_item(item, *, status, evidence):
    item.status = status
    item.evidence = evidence
    item.last_error = ''
    item.last_http_status = 200
    item.next_attempt_at = None
    item.leased_by = ''
    item.lease_expires_at = None
    item.save()


def worker_identity():
    return f'{socket.gethostname()}:{time.time_ns()}'

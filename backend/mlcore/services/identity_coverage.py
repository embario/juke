"""Play-weighted identity coverage (MBID / ISRC / Spotify) for the node_exporter textfile collector.

Headline metric of identity-graph saturation: of the plays in ``mlcore_listenbrainz_session_track``,
what share lands on an item that, after following redirects to its final target, is an MBID item or
has an ISRC / Spotify alias. Whole-catalogue counts already live in ``scripts/mlcore_identity_metrics.sh``.

Set-based throughout (the pool does ~65 random index lookups/s, and the per-sampled-row version timed
out at 40 minutes): play counts are summed per item in one scan of the session table, resolved to
final targets by :func:`mlcore.services.redirect_writes.follow_redirects` (one hash-join pass over the
redirect table per hop), then joined in one pass each to the item and alias tables with hash joins
forced. Ratios do not need the whole table: ``sample_percent`` scans a ``TABLESAMPLE SYSTEM`` page
sample, which keeps every ratio unbiased while cutting the scan.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from django.db import connection

from mlcore.models import ListenBrainzSessionTrack
from mlcore.services.canonical_items import ITEM_TYPE_RECORDING_MBID
from mlcore.services.redirect_writes import MAX_REDIRECT_DEPTH, follow_redirects, run_bulk

DEFAULT_METRICS_PATH = '/srv/monitoring/node-exporter/textfile/mlcore_identity_coverage.prom'
PLAYS_TABLE = 'mlcore_identity_coverage_plays'
FINAL_TABLE = 'mlcore_identity_coverage_final'
FLAGS_TABLE = 'mlcore_identity_coverage_flags'
SCHEMES = ('mbid', 'isrc', 'spotify')
IDENTIFIER_RE = r'^[A-Za-z_][A-Za-z0-9_]{0,62}$'


@dataclass
class IdentityCoverage:
    sample_percent: float
    total_plays: int = 0
    total_items: int = 0
    unresolved_plays: int = 0
    covered_plays: dict[str, int] = field(default_factory=dict)
    covered_items: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def play_ratio(self, scheme: str) -> float:
        return self.covered_plays.get(scheme, 0) / self.total_plays if self.total_plays else 0.0

    def item_ratio(self, scheme: str) -> float:
        return self.covered_items.get(scheme, 0) / self.total_items if self.total_items else 0.0


def sum_plays_sql(sample_percent: float) -> str:
    sample = '' if sample_percent >= 100 else f' TABLESAMPLE SYSTEM ({float(sample_percent)!r})'
    return f'''
        INSERT INTO {PLAYS_TABLE} (item_id, final_id, depth, plays)
        SELECT st.canonical_item_id, st.canonical_item_id, 0, SUM(st.play_count)
        FROM {ListenBrainzSessionTrack._meta.db_table} st{sample}
        GROUP BY st.canonical_item_id
    '''


GROUP_FINAL_SQL = f'''
    INSERT INTO {FINAL_TABLE} (final_id, plays, resolved)
    SELECT final_id, SUM(plays), BOOL_AND(depth < %s)
    FROM {PLAYS_TABLE}
    GROUP BY final_id
'''

# Alias scan: only aliases of staged final targets, one hash-join pass over the alias table.
FLAGS_SQL = f'''
    INSERT INTO {FLAGS_TABLE} (final_id, has_isrc, has_spotify)
    SELECT a.canonical_item_id,
           BOOL_OR(a.source = 'isrc'),
           BOOL_OR(a.source = 'spotify')
    FROM mlcore_canonical_item_alias a
    JOIN {FINAL_TABLE} f ON f.final_id = a.canonical_item_id
    WHERE a.status = 'active'
      AND ((a.source = 'isrc' AND a.resource_type = 'recording')
        OR (a.source = 'spotify' AND a.resource_type = 'track'))
    GROUP BY a.canonical_item_id
'''

MBID_SQL = f'''
    UPDATE {FINAL_TABLE} f
    SET is_mbid = TRUE
    FROM mlcore_canonical_item item
    WHERE item.id = f.final_id AND item.item_type = %s
'''

FLAGS_APPLY_SQL = f'''
    UPDATE {FINAL_TABLE} f
    SET has_isrc = flags.has_isrc, has_spotify = flags.has_spotify
    FROM {FLAGS_TABLE} flags
    WHERE flags.final_id = f.final_id
'''

TOTALS_SQL = f'''
    SELECT
        COALESCE(SUM(plays), 0),
        COUNT(*) FILTER (WHERE resolved),
        COALESCE(SUM(plays) FILTER (WHERE NOT resolved), 0),
        COALESCE(SUM(plays) FILTER (WHERE resolved AND is_mbid), 0),
        COALESCE(SUM(plays) FILTER (WHERE resolved AND has_isrc), 0),
        COALESCE(SUM(plays) FILTER (WHERE resolved AND has_spotify), 0),
        COUNT(*) FILTER (WHERE resolved AND is_mbid),
        COUNT(*) FILTER (WHERE resolved AND has_isrc),
        COUNT(*) FILTER (WHERE resolved AND has_spotify)
    FROM {FINAL_TABLE}
'''


def compute_play_weighted_coverage(
    *,
    sample_percent: float = 100.0,
    staging_tablespace: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> IdentityCoverage:
    if not 0 < sample_percent <= 100:
        raise ValueError('sample_percent must be in (0, 100]')
    if staging_tablespace is not None and not re.match(IDENTIFIER_RE, staging_tablespace):
        raise ValueError(f'Invalid tablespace name: {staging_tablespace!r}')
    started = time.monotonic()
    say = progress_callback or (lambda _message: None)
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        if staging_tablespace:
            cursor.execute(f'SET temp_tablespaces = {quote(staging_tablespace)}')
        for table in (PLAYS_TABLE, FINAL_TABLE, FLAGS_TABLE):
            cursor.execute(f'DROP TABLE IF EXISTS {table}')
        cursor.execute(f'''
            CREATE TEMP TABLE {PLAYS_TABLE} (
                item_id uuid PRIMARY KEY, final_id uuid NOT NULL, depth integer NOT NULL, plays bigint NOT NULL
            )
        ''')
        cursor.execute(f'''
            CREATE TEMP TABLE {FINAL_TABLE} (
                final_id uuid PRIMARY KEY, plays bigint NOT NULL, resolved boolean NOT NULL,
                is_mbid boolean NOT NULL DEFAULT FALSE, has_isrc boolean NOT NULL DEFAULT FALSE,
                has_spotify boolean NOT NULL DEFAULT FALSE
            )
        ''')
        cursor.execute(f'''
            CREATE TEMP TABLE {FLAGS_TABLE} (final_id uuid PRIMARY KEY, has_isrc boolean NOT NULL, has_spotify boolean NOT NULL)
        ''')
    try:
        say(f'summing plays per item (sample_percent={sample_percent})')
        with connection.cursor() as cursor:
            cursor.execute(sum_plays_sql(sample_percent))
            say(f'played items={max(cursor.rowcount, 0)}')
            cursor.execute(f'ANALYZE {PLAYS_TABLE}')
        follow_redirects(PLAYS_TABLE, progress=say)
        run_bulk(GROUP_FINAL_SQL, [MAX_REDIRECT_DEPTH])
        with connection.cursor() as cursor:
            cursor.execute(f'ANALYZE {FINAL_TABLE}')
        say('flagging MBID items')
        run_bulk(MBID_SQL, [ITEM_TYPE_RECORDING_MBID])
        say('flagging ISRC and Spotify aliases')
        run_bulk(FLAGS_SQL)
        run_bulk(FLAGS_APPLY_SQL)
        with connection.cursor() as cursor:
            cursor.execute(TOTALS_SQL)
            row = [int(value) for value in cursor.fetchone()]
    finally:
        with connection.cursor() as cursor:
            for table in (PLAYS_TABLE, FINAL_TABLE, FLAGS_TABLE):
                cursor.execute(f'DROP TABLE IF EXISTS {table}')
            if staging_tablespace:
                cursor.execute('RESET temp_tablespaces')
    plays, items, unresolved, mbid_plays, isrc_plays, spotify_plays, mbid_items, isrc_items, spotify_items = row
    return IdentityCoverage(
        sample_percent=float(sample_percent),
        total_plays=plays,
        total_items=items,
        unresolved_plays=unresolved,
        covered_plays={'mbid': mbid_plays, 'isrc': isrc_plays, 'spotify': spotify_plays},
        covered_items={'mbid': mbid_items, 'isrc': isrc_items, 'spotify': spotify_items},
        elapsed_seconds=time.monotonic() - started,
    )


def render_coverage_metrics(coverage: IdentityCoverage, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    labels = f'sample_percent="{coverage.sample_percent:g}"'
    lines = [
        '# HELP mlcore_identity_play_coverage_ratio Share of plays on items that, after redirects, are an MBID item '
        'or have an ISRC / Spotify alias.',
        '# TYPE mlcore_identity_play_coverage_ratio gauge',
    ]
    lines += [f'mlcore_identity_play_coverage_ratio{{scheme="{s}",{labels}}} {coverage.play_ratio(s):.8f}' for s in SCHEMES]
    lines += [
        '# HELP mlcore_identity_item_coverage_ratio Share of distinct final-target played items with the identifier.',
        '# TYPE mlcore_identity_item_coverage_ratio gauge',
    ]
    lines += [f'mlcore_identity_item_coverage_ratio{{scheme="{s}",{labels}}} {coverage.item_ratio(s):.8f}' for s in SCHEMES]
    lines += [
        '# HELP mlcore_identity_coverage_plays Plays covered, and total plays, in the (sampled) scan.',
        '# TYPE mlcore_identity_coverage_plays gauge',
    ]
    lines += [f'mlcore_identity_coverage_plays{{scheme="{s}",{labels}}} {coverage.covered_plays.get(s, 0)}' for s in SCHEMES]
    lines += [
        f'mlcore_identity_coverage_plays{{scheme="all",{labels}}} {coverage.total_plays}',
        f'mlcore_identity_coverage_plays{{scheme="unresolved_redirect_depth",{labels}}} {coverage.unresolved_plays}',
        '# HELP mlcore_identity_coverage_items Distinct final-target items in the (sampled) scan.',
        '# TYPE mlcore_identity_coverage_items gauge',
        f'mlcore_identity_coverage_items{{{labels}}} {coverage.total_items}',
        '# HELP mlcore_identity_coverage_duration_seconds Wall time of the last coverage computation.',
        '# TYPE mlcore_identity_coverage_duration_seconds gauge',
        f'mlcore_identity_coverage_duration_seconds {coverage.elapsed_seconds:.3f}',
        '# HELP mlcore_identity_coverage_last_success_timestamp_seconds Unix time of the last successful computation.',
        '# TYPE mlcore_identity_coverage_last_success_timestamp_seconds gauge',
        f'mlcore_identity_coverage_last_success_timestamp_seconds {int(now.timestamp())}',
    ]
    return '\n'.join(lines) + '\n'


def write_coverage_metrics(coverage: IdentityCoverage, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_text(render_coverage_metrics(coverage), encoding='ascii')
    temporary.replace(target)
    return target

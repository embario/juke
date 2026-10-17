"""MusicBrainz ISRC bridge: MSIDs (or clusters) without an MBID -> MBID (identity graph saturation B7).

A subject with ISRC evidence (``mlcore_identity_evidence``, scheme ``isrc``) is redirected to a
MusicBrainz recording when every ISRC it carries that is unambiguous in MusicBrainz (maps to exactly
one recording MBID in ``mlcore_musicbrainz_recording_isrc``, latest source version) points at the
same MBID. Subjects already redirected to a non-MBID cluster root (for example a ``spotify_track``
item from B6) move as a cluster: the root gets the redirect and its inbound edges are repointed.

A root moves only when the unambiguous ISRC evidence of *every* member agrees on one MBID: a member
that is individually ineligible (several MBIDs, or an MBID without a usable canonical target) still
vetoes its root. ``--sample-percent`` samples whole roots after that check, so a sample never
activates a root the full run would reject.

All reads are single hash-join passes over TEMP staging tables; writes go through
:mod:`mlcore.services.redirect_writes` in bounded, idempotent, resumable batches.
"""
from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from django.db import connection

from mlcore.models import SourceIngestionRun
from mlcore.services.canonical_items import (
    ITEM_TYPE_RECORDING_MBID,
    ITEM_TYPE_RECORDING_MSID,
    ITEM_TYPE_SPOTIFY_TRACK,
    canonical_item_uuid,
)
from mlcore.services.musicbrainz_bridge import BRIDGE_SOURCE_ID
from mlcore.services.redirect_writes import (
    MAX_REDIRECT_DEPTH,
    RedirectBatchResult,
    create_inbound_table,
    explain,
    follow_redirects,
    insert_flat_redirects,
    run_bulk,
    stage_inbound_redirects,
)

ALGORITHM_VERSION = 'musicbrainz-isrc-bridge-v2'
REDIRECT_SOURCE = 'musicbrainz-isrc-bridge'
TARGET_CHUNK_SIZE = 50_000
INBOUND_TABLE = 'tmp_ib_inbound'
FULL_SAMPLE_BASIS_POINTS = 10_000
# Owner decision #7: writes above the 1% audit slice need --full-run-approved.
AUDIT_SAMPLE_BASIS_POINTS = 100
AUDIT_MEMBERS_PER_ROOT = 10

STATUS_NEW = 'new'
STATUS_NOT_SAMPLED = 'not_sampled'
SUBJECT_STATUSES = (
    'candidate', 'subject_missing', 'not_msid', 'redirect_depth', 'already_same_mbid',
    'already_other_mbid', 'multiple_mbids', 'target_missing', 'target_not_mbid',
)

TEMP_TABLES_SQL = (
    'DROP TABLE IF EXISTS tmp_ib_isrc, tmp_ib_subject, tmp_ib_target, tmp_ib_items, tmp_ib_root',
    'CREATE TEMP TABLE tmp_ib_isrc (isrc text PRIMARY KEY, mbid uuid NOT NULL)',
    '''CREATE TEMP TABLE tmp_ib_subject (
        subject_id uuid PRIMARY KEY, mbid_count integer NOT NULL, mbid uuid NOT NULL,
        isrc_count integer NOT NULL, observation_count bigint NOT NULL, isrcs text[] NOT NULL,
        status text, root_id uuid, target_id uuid)''',
    'CREATE TEMP TABLE tmp_ib_target (mbid uuid PRIMARY KEY, target_id uuid)',
    '''CREATE TEMP TABLE tmp_ib_items (
        item_id uuid PRIMARY KEY, final_id uuid NOT NULL, depth integer NOT NULL DEFAULT 0, item_type text)''',
    '''CREATE TEMP TABLE tmp_ib_root (
        root_id uuid PRIMARY KEY, root_type text, target_id uuid, mbid uuid, mbid_count integer NOT NULL,
        subject_count integer NOT NULL, observation_count bigint NOT NULL, isrcs text[] NOT NULL,
        status text NOT NULL)''',
)

# ISRCs that MusicBrainz maps to exactly one recording.
STAGE_ISRCS_SQL = '''
    INSERT INTO tmp_ib_isrc (isrc, mbid)
    SELECT isrc, MIN(recording_mbid::text)::uuid
    FROM mlcore_musicbrainz_recording_isrc
    WHERE source_version = %s
    GROUP BY isrc
    HAVING COUNT(DISTINCT recording_mbid) = 1
'''

# One pass over all ISRC evidence. Sampling happens later, per root, so clusters are judged whole.
STAGE_SUBJECTS_SQL = '''
    INSERT INTO tmp_ib_subject (subject_id, mbid_count, mbid, isrc_count, observation_count, isrcs)
    SELECT
        evidence.subject_canonical_item_id,
        COUNT(DISTINCT isrc.mbid),
        MIN(isrc.mbid::text)::uuid,
        COUNT(DISTINCT evidence.value),
        SUM(evidence.observation_count),
        (ARRAY_AGG(DISTINCT evidence.value ORDER BY evidence.value))[1:5]
    FROM mlcore_identity_evidence evidence
    JOIN tmp_ib_isrc isrc ON isrc.isrc = evidence.value
    WHERE evidence.scheme = 'isrc'
    GROUP BY evidence.subject_canonical_item_id
'''

# Item types for every staged id, in one hash-join scan of the canonical item table (by primary key).
STAGE_ITEM_TYPES_SQL = '''
    UPDATE tmp_ib_items t
    SET item_type = item.item_type
    FROM mlcore_canonical_item item
    WHERE item.id = t.item_id
'''

CLASSIFY_SUBJECTS_SQL = f'''
    UPDATE tmp_ib_subject s
    SET status = CASE
            WHEN si.item_type IS NULL THEN 'subject_missing'
            WHEN si.item_type NOT IN ('{ITEM_TYPE_RECORDING_MSID}', '{ITEM_TYPE_SPOTIFY_TRACK}') THEN 'not_msid'
            WHEN si.depth >= %s THEN 'redirect_depth'
            WHEN sf.item_type = '{ITEM_TYPE_RECORDING_MBID}' AND s.mbid_count = 1 AND sf.item_id = tf.item_id
                THEN 'already_same_mbid'
            WHEN sf.item_type = '{ITEM_TYPE_RECORDING_MBID}' THEN 'already_other_mbid'
            WHEN sf.item_type IS NULL
              OR sf.item_type NOT IN ('{ITEM_TYPE_RECORDING_MSID}', '{ITEM_TYPE_SPOTIFY_TRACK}') THEN 'not_msid'
            WHEN s.mbid_count > 1 THEN 'multiple_mbids'
            WHEN ti.item_type IS NULL THEN 'target_missing'
            WHEN ti.depth >= %s OR tf.item_type IS DISTINCT FROM '{ITEM_TYPE_RECORDING_MBID}' THEN 'target_not_mbid'
            ELSE 'candidate'
        END,
        root_id = si.final_id,
        target_id = tf.item_id
    FROM tmp_ib_subject s2
    LEFT JOIN tmp_ib_items si ON si.item_id = s2.subject_id
    LEFT JOIN tmp_ib_items sf ON sf.item_id = si.final_id
    LEFT JOIN tmp_ib_target tt ON tt.mbid = s2.mbid
    LEFT JOIN tmp_ib_items ti ON ti.item_id = tt.target_id
    LEFT JOIN tmp_ib_items tf ON tf.item_id = ti.final_id
    WHERE s.subject_id = s2.subject_id
'''

# Subjects whose root is a movable MSID/cluster item. Each votes with its unambiguous MBIDs, including
# subjects that are ineligible on their own, so they veto the whole root instead of being repointed.
ROOT_MEMBER_STATUSES = "('candidate', 'multiple_mbids', 'target_missing', 'target_not_mbid')"

# A root moves only when all of its members agree on one MBID with a usable target. Totals are taken
# per subject before the ISRC arrays are expanded, so a multi-ISRC subject is counted once.
BUILD_ROOTS_SQL = f'''
    INSERT INTO tmp_ib_root (
        root_id, root_type, target_id, mbid, mbid_count, subject_count, observation_count, isrcs, status
    )
    SELECT
        agg.root_id,
        r.item_type,
        agg.target_id,
        agg.mbid,
        agg.mbid_count,
        agg.subject_count,
        agg.observation_count,
        COALESCE(root_isrcs.isrcs, '{{}}'),
        CASE
            WHEN agg.any_multiple OR agg.mbid_count > 1 THEN
                CASE WHEN agg.subject_count > 1 THEN 'cluster_conflict' ELSE 'multiple_mbids' END
            WHEN agg.member_status = 'candidate' THEN '{STATUS_NEW}'
            ELSE agg.member_status
        END
    FROM (
        SELECT
            root_id,
            BOOL_OR(mbid_count > 1) AS any_multiple,
            COUNT(DISTINCT mbid) AS mbid_count,
            MIN(mbid::text)::uuid AS mbid,
            MIN(target_id::text)::uuid AS target_id,
            COUNT(*) AS subject_count,
            SUM(observation_count) AS observation_count,
            -- With one MBID and no multi-MBID member, every member shares the target's status.
            MIN(status) AS member_status
        FROM tmp_ib_subject
        WHERE status IN {ROOT_MEMBER_STATUSES}
        GROUP BY root_id
    ) agg
    JOIN tmp_ib_items r ON r.item_id = agg.root_id
    LEFT JOIN (
        SELECT s.root_id, (ARRAY_AGG(DISTINCT isrc ORDER BY isrc))[1:5] AS isrcs
        FROM tmp_ib_subject s
        CROSS JOIN LATERAL unnest(s.isrcs) AS isrc
        WHERE s.status IN {ROOT_MEMBER_STATUSES}
        GROUP BY s.root_id
    ) root_isrcs ON root_isrcs.root_id = agg.root_id
'''

# Deterministic sample bucket in [0, 10000); bigint first, since abs(int4 minimum) overflows.
SAMPLE_BUCKET_SQL = 'mod(abs(hashtext({column}::text)::bigint), 10000)'

SAMPLE_ROOTS_SQL = f'''
    UPDATE tmp_ib_root
    SET status = '{STATUS_NOT_SAMPLED}'
    WHERE status = '{STATUS_NEW}'
      AND {SAMPLE_BUCKET_SQL.format(column='root_id')} >= %s
'''

REDIRECT_BATCH_SQL = '''
    SELECT
        root_id AS from_id,
        target_id AS to_id,
        1.0::double precision AS confidence,
        jsonb_build_object(
            'recording_mbid', mbid::text,
            'isrcs', to_jsonb(isrcs),
            'subject_count', subject_count,
            'observation_count', observation_count,
            'root_type', root_type,
            'musicbrainz_source_version', %s,
            'algorithm_version', %s
        ) AS evidence,
        root_id::text AS batch_key
    FROM tmp_ib_root
    WHERE status = 'new'
      AND (%s::uuid IS NULL OR root_id > %s::uuid)
    ORDER BY root_id
    LIMIT %s
'''


@dataclass
class BridgeWorkspace:
    source_version: str
    sample_percent: float
    unambiguous_isrcs: int = 0
    subjects: int = 0
    subject_status: dict[str, int] = field(default_factory=dict)
    root_status: dict[str, int] = field(default_factory=dict)
    inbound_redirects: int = 0
    explains: dict[str, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            'source_version': self.source_version,
            'sample_percent': self.sample_percent,
            'unambiguous_isrcs': self.unambiguous_isrcs,
            'subjects': self.subjects,
            'subject_status': dict(self.subject_status),
            'root_status': dict(self.root_status),
            'inbound_redirects': self.inbound_redirects,
        }


def latest_musicbrainz_isrc_source_version() -> str:
    source_version = (
        SourceIngestionRun.objects.filter(source=BRIDGE_SOURCE_ID, status='succeeded')
        .order_by('-completed_at', '-started_at')
        .values_list('source_version', flat=True)
        .first()
    )
    if not source_version:
        raise ValueError('No successful MusicBrainz identity bridge run is available.')
    return str(source_version)


def sample_basis_points(sample_percent: float) -> int:
    """The effective sample threshold: roots whose bucket is below it are in the sample."""
    if not math.isfinite(sample_percent):
        raise ValueError('sample_percent must be a finite number')
    basis_points = int(round(sample_percent * 100))
    if not 1 <= basis_points <= FULL_SAMPLE_BASIS_POINTS:
        raise ValueError('sample_percent must round to between 0.01 and 100')
    return basis_points


def build_workspace(
    source_version: str,
    *,
    sample_percent: float = 100.0,
    explain_plans: bool = False,
    progress: Callable[[str], None] | None = None,
) -> BridgeWorkspace:
    report = progress or (lambda _message: None)
    basis_points = sample_basis_points(sample_percent)
    workspace = BridgeWorkspace(source_version=source_version, sample_percent=basis_points / 100)
    started = time.monotonic()

    def step(message: str) -> None:
        report(f'{message} elapsed={time.monotonic() - started:.0f}s')

    with connection.cursor() as cursor:
        for statement in TEMP_TABLES_SQL:
            cursor.execute(statement)

    if explain_plans:
        workspace.explains['stage_isrcs'] = explain(STAGE_ISRCS_SQL, [source_version])
    workspace.unambiguous_isrcs = run_bulk(STAGE_ISRCS_SQL, [source_version])
    _analyze('tmp_ib_isrc')
    step(f'stage isrcs unambiguous={workspace.unambiguous_isrcs}')

    if explain_plans:
        workspace.explains['stage_subjects'] = explain(STAGE_SUBJECTS_SQL)
    workspace.subjects = run_bulk(STAGE_SUBJECTS_SQL)
    _analyze('tmp_ib_subject')
    step(f'stage subjects={workspace.subjects}')

    _stage_targets()
    with connection.cursor() as cursor:
        cursor.execute('''
            INSERT INTO tmp_ib_items (item_id, final_id)
            SELECT subject_id, subject_id FROM tmp_ib_subject
            UNION
            SELECT target_id, target_id FROM tmp_ib_target
        ''')
    _analyze('tmp_ib_items')
    if explain_plans:
        workspace.explains['redirect_hop'] = explain(
            'UPDATE tmp_ib_items t SET final_id = redirect.to_canonical_item_id, depth = t.depth + 1 '
            'FROM mlcore_canonical_item_redirect redirect WHERE redirect.from_canonical_item_id = t.final_id '
            "AND redirect.status = 'active' AND t.depth < 8"
        )
    follow_redirects('tmp_ib_items', progress=step)
    with connection.cursor() as cursor:
        # Final targets need their type too; they are finals, so they resolve to themselves.
        cursor.execute('''
            INSERT INTO tmp_ib_items (item_id, final_id)
            SELECT DISTINCT final_id, final_id FROM tmp_ib_items
            ON CONFLICT (item_id) DO NOTHING
        ''')
    _analyze('tmp_ib_items')
    if explain_plans:
        workspace.explains['item_types'] = explain(STAGE_ITEM_TYPES_SQL)
    run_bulk(STAGE_ITEM_TYPES_SQL)
    step('item types staged')

    with connection.cursor() as cursor:
        cursor.execute(CLASSIFY_SUBJECTS_SQL, [MAX_REDIRECT_DEPTH, MAX_REDIRECT_DEPTH])
        cursor.execute(BUILD_ROOTS_SQL)
        if basis_points < FULL_SAMPLE_BASIS_POINTS:
            cursor.execute(SAMPLE_ROOTS_SQL, [basis_points])
        cursor.execute('ANALYZE tmp_ib_root')
        cursor.execute('SELECT status, COUNT(*) FROM tmp_ib_subject GROUP BY status')
        workspace.subject_status = {status: int(count) for status, count in cursor.fetchall()}
        cursor.execute('SELECT status, COUNT(*) FROM tmp_ib_root GROUP BY status')
        workspace.root_status = {status: int(count) for status, count in cursor.fetchall()}

    create_inbound_table(INBOUND_TABLE)
    if explain_plans:
        workspace.explains['stage_inbound'] = explain(
            f'INSERT INTO {INBOUND_TABLE} (from_id, root_id) SELECT redirect.from_canonical_item_id, '
            'redirect.to_canonical_item_id FROM mlcore_canonical_item_redirect redirect '
            "JOIN tmp_ib_root roots ON roots.root_id = redirect.to_canonical_item_id WHERE redirect.status = 'active'"
        )
    workspace.inbound_redirects = stage_inbound_redirects(
        roots_table=f"(SELECT root_id FROM tmp_ib_root WHERE status = '{STATUS_NEW}')",
        root_column='root_id',
        inbound_table=INBOUND_TABLE,
    )
    step(f'classified subjects={workspace.subject_status} roots={workspace.root_status} '
         f'inbound={workspace.inbound_redirects}')
    return workspace


def _analyze(table: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f'ANALYZE {table}')


def _stage_targets() -> None:
    """MBID -> deterministic canonical item id (uuid5, as ``canonical_item_uuid``), in keyset chunks."""
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO tmp_ib_target (mbid) SELECT DISTINCT mbid FROM tmp_ib_subject")
    last = None
    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT mbid::text FROM tmp_ib_target WHERE (%s::uuid IS NULL OR mbid > %s::uuid) '
                'ORDER BY mbid LIMIT %s',
                [last, last, TARGET_CHUNK_SIZE],
            )
            mbids = [row[0] for row in cursor.fetchall()]
            if not mbids:
                break
            ids = [str(canonical_item_uuid(item_type=ITEM_TYPE_RECORDING_MBID, key_value=mbid)) for mbid in mbids]
            cursor.execute(
                'UPDATE tmp_ib_target t SET target_id = v.target_id '
                'FROM unnest(%s::uuid[], %s::uuid[]) AS v(mbid, target_id) WHERE t.mbid = v.mbid',
                [mbids, ids],
            )
        last = mbids[-1]
    _analyze('tmp_ib_target')


def apply_redirect_batch(
    *,
    source_version: str,
    last_root: str | None,
    batch_size: int,
    write: bool,
) -> RedirectBatchResult:
    if batch_size < 1:
        raise ValueError('batch_size must be greater than zero')
    return insert_flat_redirects(
        batch_sql=REDIRECT_BATCH_SQL,
        batch_params=_batch_params(source_version, last_root, batch_size),
        source=REDIRECT_SOURCE,
        source_version=source_version,
        inbound_table=INBOUND_TABLE,
        write=write,
    )


def _batch_params(source_version: str, last_root: str | None, batch_size: int) -> list[Any]:
    return [source_version, ALGORITHM_VERSION, last_root, last_root, batch_size]


AUDIT_COLUMNS = (
    'root_id', 'root_type', 'root_canonical_key', 'target_id', 'recording_mbid', 'musicbrainz_url',
    'isrcs', 'subject_count', 'observation_count', 'inbound_redirects', 'member_msids',
    'listenbrainz_mapped_mbids', 'musicbrainz_isrcs', 'musicbrainz_spotify_urls', 'redirect_written',
)

AUDIT_ROOTS_SQL = f'''
    WITH audit AS MATERIALIZED (
        SELECT * FROM tmp_ib_root WHERE status = '{STATUS_NEW}' ORDER BY md5(root_id::text) LIMIT %s
    )
    SELECT root.root_id::text, root.root_type, item.canonical_key, root.target_id::text, root.mbid::text,
           array_to_string(root.isrcs, ' '), root.subject_count, root.observation_count,
           (SELECT COUNT(*) FROM {INBOUND_TABLE} inbound WHERE inbound.root_id = root.root_id),
           (SELECT string_agg(DISTINCT mbi.isrc, ' ') FROM mlcore_musicbrainz_recording_isrc mbi
             WHERE mbi.recording_mbid = root.mbid),
           (SELECT string_agg(DISTINCT mbu.url, ' ') FROM mlcore_musicbrainz_recording_url mbu
             WHERE mbu.recording_mbid = root.mbid AND mbu.provider = 'spotify')
    FROM audit root
    LEFT JOIN mlcore_canonical_item item ON item.id = root.root_id
'''

# The contributing subjects of the audited roots (from the staged subject -> root relation, capped per
# root) with their MSIDs and ListenBrainz MSID -> MBID mapping rows.
AUDIT_MEMBERS_SQL = f'''
    WITH members AS MATERIALIZED (
        SELECT root_id, subject_id FROM (
            SELECT s.root_id, s.subject_id,
                   row_number() OVER (PARTITION BY s.root_id ORDER BY s.subject_id) AS member_rank
            FROM tmp_ib_subject s
            WHERE s.root_id = ANY(%s::uuid[]) AND s.status IN {ROOT_MEMBER_STATUSES}
        ) ranked
        WHERE member_rank <= %s
    ),
    keyed AS MATERIALIZED (
        SELECT m.root_id, substring(item.canonical_key from {len(ITEM_TYPE_RECORDING_MSID) + 2})::uuid AS msid
        FROM members m
        JOIN mlcore_canonical_item item ON item.id = m.subject_id
        WHERE item.canonical_key LIKE '{ITEM_TYPE_RECORDING_MSID}:%%'
    )
    SELECT keyed.root_id::text, keyed.msid::text,
           string_agg(DISTINCT mapping.recording_mbid::text || ':' || mapping.status, ' ')
    FROM keyed
    LEFT JOIN mlcore_listenbrainz_msid_mbid_mapping mapping ON mapping.recording_msid = keyed.msid
    GROUP BY keyed.root_id, keyed.msid
    ORDER BY keyed.root_id, keyed.msid
'''

LIVE_REDIRECTS_SQL = '''
    SELECT from_canonical_item_id::text, to_canonical_item_id::text, source
    FROM mlcore_canonical_item_redirect
    WHERE from_canonical_item_id = ANY(%s::uuid[])
'''


def collect_audit_rows(*, limit: int = 200) -> list[dict[str, Any]]:
    """A deterministic sample of the planned merges with MusicBrainz/ListenBrainz provenance.

    Call it right after :func:`build_workspace`, before any batch is written; a write run stores the
    result so that a paused or crashed run still audits every merge it selected. Only ``limit`` roots
    (and at most ``AUDIT_MEMBERS_PER_ROOT`` members each) are enriched, so the indexed lookups stay at a
    few thousand in total.
    """
    if limit <= 0:
        return []
    with connection.cursor() as cursor:
        cursor.execute(AUDIT_ROOTS_SQL, [limit])
        roots = cursor.fetchall()
        cursor.execute(AUDIT_MEMBERS_SQL, [[row[0] for row in roots], AUDIT_MEMBERS_PER_ROOT])
        members = cursor.fetchall()
    msids: dict[str, list[str]] = {}
    mappings: dict[str, list[str]] = {}
    for root_id, msid, mapped in members:
        msids.setdefault(root_id, []).append(msid)
        if mapped:
            mappings.setdefault(root_id, []).append(f'{msid}={mapped}')
    rows = []
    for (root_id, root_type, key, target_id, mbid, isrcs, subjects, observations, inbound, mb_isrcs,
         mb_urls) in sorted(roots, key=lambda row: row[0]):
        rows.append({
            'root_id': root_id,
            'root_type': root_type,
            'root_canonical_key': key or '',
            'target_id': target_id,
            'recording_mbid': mbid,
            'musicbrainz_url': f'https://musicbrainz.org/recording/{mbid}',
            'isrcs': isrcs,
            'subject_count': int(subjects),
            'observation_count': int(observations),
            'inbound_redirects': int(inbound),
            'member_msids': ' '.join(msids.get(root_id, [])),
            'listenbrainz_mapped_mbids': ' '.join(mappings.get(root_id, [])),
            'musicbrainz_isrcs': mb_isrcs or '',
            'musicbrainz_spotify_urls': mb_urls or '',
        })
    return rows


def write_audit_export(path: str, rows: list[dict[str, Any]]) -> int:
    """Write audit rows as CSV with the live state of each root's redirect.

    ``redirect_written`` is ``yes`` (this bridge wrote root -> target), ``no`` (no outgoing redirect
    yet) or ``other`` (another outgoing redirect exists and was left alone).
    """
    with connection.cursor() as cursor:
        cursor.execute(LIVE_REDIRECTS_SQL, [[row['root_id'] for row in rows]])
        existing = {from_id: (to_id, source) for from_id, to_id, source in cursor.fetchall()}
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_COLUMNS)
        writer.writeheader()
        for row in rows:
            redirect = existing.get(row['root_id'])
            if redirect is None:
                written = 'no'
            elif redirect == (row['target_id'], REDIRECT_SOURCE):
                written = 'yes'
            else:
                written = 'other'
            writer.writerow({**row, 'redirect_written': written})
    return len(rows)

"""MusicBrainz ISRC bridge: MSIDs (or clusters) without an MBID -> MBID (identity graph saturation B7).

A subject with ISRC evidence (``mlcore_identity_evidence``, scheme ``isrc``) is redirected to a
MusicBrainz recording when every ISRC it carries that is unambiguous in MusicBrainz (maps to exactly
one recording MBID in ``mlcore_musicbrainz_recording_isrc``, latest source version) points at the
same MBID. Subjects already redirected to a non-MBID cluster root (for example a ``spotify_track``
item from B6) move as a cluster: the root gets the redirect and its inbound edges are repointed.

All reads are single hash-join passes over TEMP staging tables; writes go through
:mod:`mlcore.services.redirect_writes` in bounded, idempotent, resumable batches.
"""
from __future__ import annotations

import csv
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

ALGORITHM_VERSION = 'musicbrainz-isrc-bridge-v1'
REDIRECT_SOURCE = 'musicbrainz-isrc-bridge'
TARGET_CHUNK_SIZE = 50_000
INBOUND_TABLE = 'tmp_ib_inbound'

STATUS_NEW = 'new'
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
        root_id uuid PRIMARY KEY, root_type text, target_id uuid, mbid uuid, target_count integer NOT NULL,
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

# One pass over the ISRC evidence; ``%s`` is the sample threshold in basis points (10000 = all).
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
      AND (%s >= 10000 OR mod(abs(hashtext(evidence.subject_canonical_item_id::text)), 10000) < %s)
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

# A root moves only when all of its candidate subjects agree on one target.
BUILD_ROOTS_SQL = '''
    INSERT INTO tmp_ib_root (
        root_id, root_type, target_id, mbid, target_count, subject_count, observation_count, isrcs, status
    )
    SELECT
        s.root_id,
        MIN(r.item_type),
        MIN(s.target_id::text)::uuid,
        MIN(s.mbid::text)::uuid,
        COUNT(DISTINCT s.target_id),
        COUNT(*),
        SUM(s.observation_count),
        (ARRAY_AGG(DISTINCT isrc ORDER BY isrc))[1:5],
        CASE WHEN COUNT(DISTINCT s.target_id) = 1 THEN 'new' ELSE 'cluster_conflict' END
    FROM tmp_ib_subject s
    JOIN tmp_ib_items r ON r.item_id = s.root_id
    CROSS JOIN LATERAL unnest(s.isrcs) AS isrc
    WHERE s.status = 'candidate'
    GROUP BY s.root_id
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
    if not 0 < sample_percent <= 100:
        raise ValueError('sample_percent must be in (0, 100]')
    return int(round(sample_percent * 100))


def build_workspace(
    source_version: str,
    *,
    sample_percent: float = 100.0,
    explain_plans: bool = False,
    progress: Callable[[str], None] | None = None,
) -> BridgeWorkspace:
    report = progress or (lambda _message: None)
    basis_points = sample_basis_points(sample_percent)
    workspace = BridgeWorkspace(source_version=source_version, sample_percent=sample_percent)
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
        workspace.explains['stage_subjects'] = explain(STAGE_SUBJECTS_SQL, [basis_points, basis_points])
    workspace.subjects = run_bulk(STAGE_SUBJECTS_SQL, [basis_points, basis_points])
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
        roots_table="(SELECT root_id FROM tmp_ib_root WHERE status = 'new')",
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
        batch_params=[source_version, ALGORITHM_VERSION, last_root, last_root, batch_size],
        source=REDIRECT_SOURCE,
        source_version=source_version,
        inbound_table=INBOUND_TABLE,
        write=write,
    )


AUDIT_COLUMNS = (
    'root_id', 'root_type', 'root_canonical_key', 'target_id', 'recording_mbid', 'musicbrainz_url',
    'isrcs', 'subject_count', 'observation_count', 'musicbrainz_isrcs', 'musicbrainz_spotify_urls',
    'listenbrainz_mapped_mbids', 'listenbrainz_msid', 'redirect_written',
)


def write_audit_export(path: str, *, limit: int = 200) -> int:
    """Write a deterministic sample of planned merges with MusicBrainz/ListenBrainz context as CSV.

    Only ``limit`` rows are enriched, so the per-row lookups (indexed, by primary key or MBID/MSID)
    stay at a few hundred in total.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            '''
            SELECT root.root_id::text, root.root_type, item.canonical_key, root.target_id::text, root.mbid::text,
                   array_to_string(root.isrcs, ' '), root.subject_count, root.observation_count,
                   (SELECT string_agg(DISTINCT mbi.isrc, ' ') FROM mlcore_musicbrainz_recording_isrc mbi
                     WHERE mbi.recording_mbid = root.mbid),
                   (SELECT string_agg(DISTINCT mbu.url, ' ') FROM mlcore_musicbrainz_recording_url mbu
                     WHERE mbu.recording_mbid = root.mbid AND mbu.provider = 'spotify'),
                   (SELECT string_agg(DISTINCT mapping.recording_mbid::text || ':' || mapping.status, ' ')
                     FROM mlcore_listenbrainz_msid_mbid_mapping mapping
                     WHERE item.canonical_key LIKE 'recording_msid:%%'
                       AND mapping.recording_msid = substring(item.canonical_key from 16)::uuid),
                   EXISTS (SELECT 1 FROM mlcore_canonical_item_redirect redirect
                           WHERE redirect.from_canonical_item_id = root.root_id
                             AND redirect.to_canonical_item_id = root.target_id
                             AND redirect.source = %s)
            FROM (
                SELECT * FROM tmp_ib_root WHERE status = 'new' ORDER BY md5(root_id::text) LIMIT %s
            ) root
            LEFT JOIN mlcore_canonical_item item ON item.id = root.root_id
            ORDER BY md5(root.root_id::text)
            ''',
            [REDIRECT_SOURCE, limit],
        )
        rows = cursor.fetchall()
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(AUDIT_COLUMNS)
        for (root_id, root_type, key, target_id, mbid, isrcs, subjects, observations, mb_isrcs, mb_urls,
             lb_mbids, written) in rows:
            msid = key.split(':', 1)[1] if key and key.startswith(f'{ITEM_TYPE_RECORDING_MSID}:') else ''
            writer.writerow([
                root_id, root_type, key or '', target_id, mbid, f'https://musicbrainz.org/recording/{mbid}',
                isrcs, subjects, observations, mb_isrcs or '', mb_urls or '', lb_mbids or '', msid,
                'yes' if written else 'no',
            ])
    return len(rows)

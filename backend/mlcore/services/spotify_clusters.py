"""B6: deterministic, set-based Spotify clusters; no provider API access.

Staging is rebuilt on resume (freeze evidence/bridge imports while running). Only bounded
COPY buffers cross Python; all identity resolution and ownership checks are hash joins.
The B7 writer owns redirect insertion and inbound repointing.
"""
from __future__ import annotations

import io
import json
import time
from pathlib import Path

from django.db import connection, transaction

from mlcore.services.canonical_items import canonical_item_uuid
from mlcore.services.redirect_writes import (
    MAX_REDIRECT_DEPTH, bulk_join_mode, create_inbound_table, explain,
    follow_redirects, insert_flat_redirects, run_bulk, stage_inbound_redirects,
)

SOURCE = 'listenbrainz-spotify-cluster'
ALGORITHM = 'spotify-cluster-v1'

# SUM across all loaded versions: B4 keeps cumulative observations, not version snapshots.
DOMINANT_SQL = '''
    CREATE TEMP TABLE tmp_sp_member AS
    WITH pairs AS (
        SELECT subject_canonical_item_id AS item_id, value AS spotify_id,
               SUM(observation_count) AS observations
        FROM mlcore_identity_evidence
        WHERE scheme = 'spotify_track' AND source = 'listenbrainz'
          AND value ~ '^[A-Za-z0-9]{22}$'
        GROUP BY subject_canonical_item_id, value
    ), totals AS (
        SELECT *, SUM(observations) OVER (PARTITION BY item_id) AS total
        FROM pairs
    )
    SELECT t.*, t.item_id AS final_id, 0::integer AS depth, i.canonical_key AS member_key
    FROM totals t JOIN mlcore_canonical_item i ON i.id = t.item_id
    WHERE observations >= 2 AND observations * 10 >= total * 9
      AND i.item_type = 'recording_msid'
      AND (('x' || substr(md5(spotify_id), 1, 8))::bit(32)::bigint %% 1000000) < %s
'''

GROUP_SQL = '''
    CREATE TEMP TABLE tmp_sp_group AS
    SELECT m.spotify_id, COUNT(*)::integer AS size,
           CASE WHEN COUNT(*) > 200 THEN 'oversize'
                WHEN MAX(m.depth) >= %s THEN 'redirect_depth' ELSE 'ready' END::text AS status,
           NULL::uuid AS target_id, NULL::text AS target_key, NULL::text AS target_type,
           NULL::text AS target_reason
    FROM tmp_sp_member m GROUP BY m.spotify_id
'''

# Candidate MBIDs from resolved members, B5 aliases and the group's dominant ISRC.
# Contradictory MBID evidence at any level is a conflict, never a precedence tie-break.
CANDIDATES_SQL = '''
    CREATE TEMP TABLE tmp_sp_candidate AS
    SELECT m.spotify_id, i.canonical_key AS target_key, 1 AS priority
    FROM tmp_sp_member m JOIN mlcore_canonical_item i ON i.id = m.final_id
    WHERE i.item_type = 'recording_mbid'
    UNION ALL
    SELECT a.source_id, i.canonical_key, 2
    FROM mlcore_canonical_item_alias a
    JOIN tmp_sp_group g ON g.spotify_id = a.source_id
    JOIN mlcore_canonical_item i ON i.id = a.canonical_item_id
    WHERE a.source = 'spotify' AND a.resource_type = 'track' AND a.status = 'active'
      AND a.metadata->>'match_source' = 'musicbrainz_url' AND i.item_type = 'recording_mbid'
    UNION ALL
    SELECT d.spotify_id, 'recording_mbid:' || MIN(b.recording_mbid::text), 3
    FROM tmp_sp_isrc_dominant d
    JOIN mlcore_musicbrainz_recording_isrc b ON b.isrc = d.isrc AND b.source_version = %s
    GROUP BY d.spotify_id HAVING COUNT(DISTINCT b.recording_mbid) = 1
'''

ISRC_SQL = '''
    CREATE TEMP TABLE tmp_sp_isrc_dominant AS
    WITH pairs AS (
        SELECT m.spotify_id, e.value AS isrc, SUM(e.observation_count) AS n
        FROM mlcore_identity_evidence e JOIN tmp_sp_member m
          ON m.item_id = e.subject_canonical_item_id
        WHERE e.scheme = 'isrc' AND e.source = 'listenbrainz'
        GROUP BY m.spotify_id, e.value
    ), totals AS (
        SELECT *, SUM(n) OVER (PARTITION BY spotify_id) AS total FROM pairs
    )
    SELECT spotify_id, isrc FROM totals WHERE n >= 2 AND n * 10 >= total * 9
'''

TARGET_SQL = '''
    UPDATE tmp_sp_group g SET target_key = c.target_key,
        target_type = 'recording_mbid', target_reason = c.reason,
        status = CASE WHEN c.n > 1 THEN 'mbid_conflict' ELSE g.status END
    FROM (
        SELECT spotify_id, MIN(target_key) AS target_key, COUNT(DISTINCT target_key) AS n,
               CASE MIN(priority) WHEN 1 THEN 'resolved_mbid' WHEN 2 THEN 'musicbrainz_url'
                    ELSE 'unique_isrc' END AS reason
        FROM tmp_sp_candidate GROUP BY spotify_id
    ) c WHERE c.spotify_id = g.spotify_id
'''

OWNERSHIP_SQL = '''
    UPDATE tmp_sp_group g SET status = 'alias_conflict'
    FROM mlcore_canonical_item_alias a
    LEFT JOIN mlcore_canonical_item owner ON owner.id = a.canonical_item_id
    WHERE a.source = 'spotify' AND a.resource_type = 'track' AND a.source_id = g.spotify_id
      AND (a.status <> 'active' OR (a.canonical_item_id <> g.target_id
           AND NOT (owner.canonical_key = 'spotify_track:' || g.spotify_id
                    AND g.target_type = 'recording_mbid'))) AND g.status = 'ready'
'''

# Existing active edges may only differ when their root is this group's spotify_track item,
# which can be promoted by inserting its own edge + repointing inbound with the shared writer.
REDIRECT_CONFLICT_SQL = '''
    UPDATE tmp_sp_group g SET status = 'redirect_conflict'
    FROM tmp_sp_member m LEFT JOIN mlcore_canonical_item root ON root.id = m.final_id
    WHERE m.spotify_id = g.spotify_id AND g.status = 'ready'
      AND m.final_id <> m.item_id AND m.final_id <> g.target_id
      AND root.canonical_key IS DISTINCT FROM 'spotify_track:' || g.spotify_id
'''

ACTIONS_SQL = '''
    CREATE TEMP TABLE tmp_sp_action AS
    SELECT m.spotify_id || ':' || m.item_id::text AS batch_key, m.spotify_id,
           m.item_id AS from_id, g.target_id AS to_id, g.target_key, g.target_type,
           m.final_id, m.member_key, m.observations, m.total, g.target_reason
    FROM tmp_sp_member m JOIN tmp_sp_group g USING (spotify_id) WHERE g.status = 'ready'
    UNION
    SELECT g.spotify_id || ':' || root.id::text, g.spotify_id, root.id, g.target_id,
           g.target_key, g.target_type, root.id, root.canonical_key,
           0::numeric, 0::numeric, g.target_reason
    FROM tmp_sp_group g JOIN mlcore_canonical_item root
      ON root.canonical_key = 'spotify_track:' || g.spotify_id
    WHERE g.status = 'ready' AND g.target_type = 'recording_mbid'
'''

# Export bounds apply before metadata joins. Each large table is scanned once for this sample.
AUDIT_SQL = '''
    WITH sample AS MATERIALIZED (
        SELECT * FROM tmp_sp_action WHERE from_id <> to_id AND final_id <> to_id
        ORDER BY md5(batch_key), batch_key LIMIT %s
    ), evidence AS (
        SELECT e.subject_canonical_item_id AS item_id,
               jsonb_agg(jsonb_build_object('scheme', e.scheme, 'value', e.value,
                  'observations', e.observation_count, 'shards', e.shard_count,
                  'source_version', e.source_version, 'first_seen', e.first_seen,
                  'last_seen', e.last_seen) ORDER BY e.scheme, e.value) AS details
        FROM mlcore_identity_evidence e JOIN sample s ON s.from_id = e.subject_canonical_item_id
        GROUP BY e.subject_canonical_item_id
    ), mb AS (
        SELECT s.batch_key, jsonb_agg(jsonb_build_object('isrc', b.isrc,
                  'source_version', b.source_version) ORDER BY b.isrc) AS isrcs
        FROM mlcore_musicbrainz_recording_isrc b JOIN sample s
          ON s.target_key = 'recording_mbid:' || b.recording_mbid::text
        GROUP BY s.batch_key
    ), urls AS (
        SELECT s.batch_key, jsonb_agg(jsonb_build_object('url', b.url,
                  'source_version', b.source_version) ORDER BY b.url) AS links
        FROM mlcore_musicbrainz_recording_url b JOIN sample s
          ON s.target_key = 'recording_mbid:' || b.recording_mbid::text
        GROUP BY s.batch_key
    ), lb AS (
        SELECT DISTINCT ON (r.recording_msid) r.recording_msid, r.track_name AS title,
               r.artist_name AS artist, r.release_name AS release
        FROM mlcore_listenbrainz_raw_listen r JOIN sample s
          ON s.member_key = 'recording_msid:' || r.recording_msid
        ORDER BY r.recording_msid, r.track_name, r.artist_name, r.release_name
    )
    SELECT s.*, e.details AS evidence, mb.isrcs AS musicbrainz_isrcs, urls.links AS musicbrainz_links, lb.title AS listenbrainz_title,
           lb.artist AS listenbrainz_artist, lb.release AS listenbrainz_release,
           t.name AS catalog_title
    FROM sample s LEFT JOIN evidence e ON e.item_id = s.from_id
    LEFT JOIN mb ON mb.batch_key = s.batch_key LEFT JOIN urls ON urls.batch_key = s.batch_key
    LEFT JOIN lb ON s.member_key = 'recording_msid:' || lb.recording_msid
    LEFT JOIN mlcore_canonical_item i ON i.id = s.to_id
    LEFT JOIN catalog_track t ON t.juke_id = i.track_id
    ORDER BY s.batch_key
'''


def _bulk(sql, params=None):
    return run_bulk(sql, params)


def _analyze(*tables):
    with connection.cursor() as cursor:
        for table in tables:  # one statement per staging relation, never one per identity
            cursor.execute(f'ANALYZE {table}')


def _copy_target_ids():
    """CPU-only UUID5 calculation, bounded COPY; never a per-item database query."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute('CREATE TEMP TABLE tmp_sp_target (target_key text PRIMARY KEY, item_id uuid)')
        with connection.connection.cursor(name='spotify_target_ids') as reader:
            reader.execute('SELECT DISTINCT target_key, target_type FROM tmp_sp_group ORDER BY target_key')
            while rows := reader.fetchmany(50_000):
                buf = io.StringIO()
                for key, typ in rows:
                    item_id = canonical_item_uuid(item_type=typ, key_value=key.split(':', 1)[1])
                    buf.write(f'{key}\t{item_id}\n')
                buf.seek(0)
                cursor.copy_expert('COPY tmp_sp_target (target_key, item_id) FROM STDIN', buf)
    _analyze('tmp_sp_target')
    _bulk('''UPDATE tmp_sp_group g SET target_id = t.item_id
             FROM tmp_sp_target t WHERE t.target_key = g.target_key''')
    # Resolve existing target redirects too; an MBID can have been superseded.
    _bulk('''CREATE TEMP TABLE tmp_sp_target_root AS
             SELECT t.item_id, t.item_id AS final_id, 0::integer AS depth FROM tmp_sp_target t''')
    _analyze('tmp_sp_target_root')
    follow_redirects('tmp_sp_target_root')
    _bulk('''UPDATE tmp_sp_group g SET status = 'redirect_depth'
             FROM tmp_sp_target_root r WHERE r.item_id = g.target_id AND r.depth >= %s''', [MAX_REDIRECT_DEPTH])
    _bulk('''UPDATE tmp_sp_group g SET target_id = r.final_id, target_key = i.canonical_key,
                 target_type = i.item_type
             FROM tmp_sp_target_root r JOIN mlcore_canonical_item i ON i.id = r.final_id
             WHERE g.target_id = r.item_id AND r.depth < %s''', [MAX_REDIRECT_DEPTH])


def build_workspace(*, sample_percent=1, musicbrainz_version, progress=print, plans=None):
    """All staging is TEMP. Nothing writes persistent tables."""
    if not 0 < sample_percent <= 100:
        raise ValueError('sample_percent must be > 0 and <= 100')
    for name in ('action', 'candidate', 'isrc_dominant', 'member', 'group', 'target', 'target_root', 'inbound', 'isrc_alias'):
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS tmp_sp_{name}')
    if plans is not None:
        plans['dominance'] = explain(DOMINANT_SQL, [sample_percent * 10000])
    progress('staging dominant Spotify evidence (sequential/hash scan)')
    _bulk(DOMINANT_SQL, [sample_percent * 10000])
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX ON tmp_sp_member (item_id)')
        cursor.execute('ANALYZE tmp_sp_member')
    follow_redirects('tmp_sp_member', progress=progress)
    _bulk(GROUP_SQL, [MAX_REDIRECT_DEPTH])
    _analyze('tmp_sp_group')
    progress('staging group ISRC dominance (evidence hash scan)')
    _bulk(ISRC_SQL)
    _analyze('tmp_sp_isrc_dominant')
    progress('staging MBID targets (resolved roots, B5 aliases, MusicBrainz ISRC hash scans)')
    if plans is not None:
        plans['target_candidates'] = explain(CANDIDATES_SQL, [musicbrainz_version])
    _bulk(CANDIDATES_SQL, [musicbrainz_version])
    _analyze('tmp_sp_candidate')
    _bulk(TARGET_SQL)
    _bulk('''UPDATE tmp_sp_group SET target_key = 'spotify_track:' || spotify_id,
             target_type = 'spotify_track', target_reason = 'new_spotify' WHERE target_key IS NULL''')
    progress('resolving target roots and checking redirect/alias ownership')
    _copy_target_ids()
    if plans is not None:
        plans['redirect_conflicts'] = explain(REDIRECT_CONFLICT_SQL)
        plans['alias_ownership'] = explain(OWNERSHIP_SQL)
    _bulk(REDIRECT_CONFLICT_SQL)
    _bulk(OWNERSHIP_SQL)
    if plans is not None:
        plans['actions'] = explain(ACTIONS_SQL)
    _bulk(ACTIONS_SQL)
    _analyze('tmp_sp_action')
    progress('staging globally unambiguous ISRC aliases (evidence hash scan)')
    _bulk('''CREATE TEMP TABLE tmp_sp_isrc_alias AS
        SELECT e.value AS isrc, MIN(a.to_id::text)::uuid AS to_id,
               MIN(a.batch_key) AS batch_key
        FROM mlcore_identity_evidence e
        LEFT JOIN tmp_sp_action a ON a.from_id = e.subject_canonical_item_id
        WHERE e.scheme = 'isrc' AND e.value ~ '^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'
        GROUP BY e.value HAVING COUNT(a.from_id) > 0
          AND COUNT(DISTINCT COALESCE(a.to_id, e.subject_canonical_item_id)) = 1''')
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX ON tmp_sp_action (batch_key)')
        cursor.execute('ANALYZE tmp_sp_action')
    _analyze('tmp_sp_isrc_alias')
    progress('staging inbound redirects for flat promotion (redirect hash scan)')
    create_inbound_table('tmp_sp_inbound')
    stage_inbound_redirects(roots_table='tmp_sp_action', root_column='from_id', inbound_table='tmp_sp_inbound')
    with connection.cursor() as cursor:
        cursor.execute('SELECT status, COUNT(*) FROM tmp_sp_group GROUP BY status ORDER BY status')
        counts = dict(cursor.fetchall())
    progress(f'staged groups: {counts}')
    return counts


BATCH_SQL = '''
    SELECT from_id, to_id, 0.9::float AS confidence,
           jsonb_build_object('algorithm', 'spotify-cluster-v1', 'spotify_id', spotify_id) AS evidence,
           batch_key
    FROM tmp_sp_action WHERE batch_key > %s ORDER BY batch_key LIMIT %s
'''

ITEM_BATCH_SQL = '''
    INSERT INTO mlcore_canonical_item (id, item_type, canonical_key, created_at, updated_at)
    SELECT DISTINCT to_id, target_type, target_key, NOW(), NOW()
    FROM tmp_sp_action WHERE batch_key > %s AND batch_key <= %s
    ON CONFLICT DO NOTHING
'''

ALIAS_BATCH_SQL = '''
    INSERT INTO mlcore_canonical_item_alias
        (id, canonical_item_id, source, resource_type, source_id, confidence,
         source_version, status, metadata, created_at, updated_at)
    SELECT DISTINCT md5('spotify:track:' || spotify_id)::uuid, to_id, 'spotify', 'track',
           spotify_id, 0.9, %s, 'active', '{"match_source":"listenbrainz_spotify_cluster"}'::jsonb, NOW(), NOW()
    FROM tmp_sp_action WHERE batch_key > %s AND batch_key <= %s
    ON CONFLICT (source, resource_type, source_id) DO NOTHING
'''


ISRC_ALIAS_BATCH_SQL = '''
    INSERT INTO mlcore_canonical_item_alias
        (id, canonical_item_id, source, resource_type, source_id, confidence,
         source_version, status, metadata, created_at, updated_at)
    SELECT md5('isrc:recording:' || isrc)::uuid, to_id, 'isrc', 'recording',
           isrc, 0.9, %s, 'active', '{"match_source":"listenbrainz_spotify_cluster"}'::jsonb, NOW(), NOW()
    FROM tmp_sp_isrc_alias WHERE batch_key > %s AND batch_key <= %s
    ON CONFLICT (source, resource_type, source_id) DO NOTHING
'''


def apply_workspace(*, write=False, source_version, batch_size=50_000, after_key='',
                    checkpoint=None, progress=print, max_batches=None):
    if not 10_000 <= batch_size <= 100_000:
        raise ValueError('batch_size must be 10000..100000')
    started = time.monotonic()
    processed = inserted = repointed = aliases = 0
    batches = 0
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM tmp_sp_action WHERE batch_key > %s', [after_key])
        total = cursor.fetchone()[0]
    while max_batches is None or batches < max_batches:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('SELECT MAX(batch_key) FROM (SELECT batch_key FROM tmp_sp_action '
                           'WHERE batch_key > %s ORDER BY batch_key LIMIT %s) b', [after_key, batch_size])
            upper = cursor.fetchone()[0]
            if upper is None:
                break
            if write:
                cursor.execute(ITEM_BATCH_SQL, [after_key, upper])
            result = insert_flat_redirects(
                batch_sql=BATCH_SQL, batch_params=[after_key, batch_size], source=SOURCE,
                source_version=source_version, inbound_table='tmp_sp_inbound', write=write,
            )
            if write:
                cursor.execute(ALIAS_BATCH_SQL, [source_version, after_key, upper])
                aliases += cursor.rowcount
                cursor.execute(ISRC_ALIAS_BATCH_SQL, [source_version, after_key, upper])
                aliases += cursor.rowcount
        # Checkpoint after commit. A crash before this repeats an idempotent batch.
        after_key = upper
        if write and checkpoint:
            checkpoint(after_key)
        processed += result.processed
        inserted += result.inserted
        repointed += result.repointed
        batches += 1
        rate = processed / max(time.monotonic() - started, .001)
        progress(f'processed={processed}/{total} rows_per_second={rate:.1f} '
                 f'eta_seconds={(total - processed) / rate:.1f} after_key={after_key}')
    return dict(processed=processed, redirects=inserted, repointed=repointed, aliases=aliases,
                after_key=after_key, write=write)


def export_audit(path, *, limit=200, metadata_path=None):
    # Optional small, offline metadata supplement from the operator's local MB/LB dumps.
    # Keys are canonical keys; preserve provenance alongside titles/artists in the export.
    metadata = {}
    if metadata_path:
        with Path(metadata_path).open() as supplement:
            for line in supplement:
                entry = json.loads(line)
                metadata[entry['canonical_key']] = entry

    with transaction.atomic(), connection.cursor() as cursor:
        bulk_join_mode(cursor)
        cursor.execute(AUDIT_SQL, [limit])
        names = [c[0] for c in cursor.description]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    with Path(path).open('w') as output:
        for row in rows:
            for field in ('evidence', 'musicbrainz_isrcs', 'musicbrainz_links'):
                if isinstance(row[field], str):
                    row[field] = json.loads(row[field])
            key = row['target_key']
            row['musicbrainz_url'] = ('https://musicbrainz.org/recording/' + key.split(':', 1)[1]
                                       if key.startswith('recording_mbid:') else None)
            row['listenbrainz_url'] = 'https://listenbrainz.org/player/?recording_msid=' + row['member_key'].split(':', 1)[1]
            row['listenbrainz_metadata'] = metadata.get(row['member_key'])
            row['musicbrainz_metadata'] = metadata.get(key)
            row['metadata_missing'] = not (
                (row['listenbrainz_title'] or row['listenbrainz_metadata']) and row['musicbrainz_metadata'])
            output.write(json.dumps(row, default=str, sort_keys=True) + '\n')
    return len(rows)


def export_review(path):
    with connection.cursor() as cursor, Path(path).open('w') as output:
        cursor.execute("SELECT spotify_id, size, status FROM tmp_sp_group WHERE status <> 'ready' ORDER BY spotify_id")
        while rows := cursor.fetchmany(10_000):
            for sid, size, status in rows:
                output.write(json.dumps(dict(spotify_id=sid, size=size, status=status)) + '\n')

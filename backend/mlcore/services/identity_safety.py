"""Shared identity hold policy. Source facts remain immutable; holds veto whole groups."""

from django.db import connection
from django.db.models import Q

from mlcore.models import CanonicalItemAlias, ProviderHydrationItem
from mlcore.services.redirect_writes import FOLLOW_REDIRECT_HOP_SQL, MAX_REDIRECT_DEPTH

HOLD_KEY = 'identity_reference_quarantine'
HELD_IDENTIFIER_SQL = """
    SELECT DISTINCT CASE source WHEN 'isrc' THEN 'isrc' WHEN 'spotify' THEN 'spotify_track'
                    WHEN 'musicbrainz' THEN 'mbid' WHEN 'listenbrainz' THEN 'msid' END AS scheme, source_id AS value
    FROM mlcore_canonical_item_alias
    WHERE (status <> 'active' OR metadata ? 'identity_reference_quarantine')
      AND ((source = 'isrc' AND resource_type = 'recording')
        OR (source = 'spotify' AND resource_type = 'track')
        OR (source IN ('musicbrainz','listenbrainz') AND resource_type = 'recording'))
    UNION
    SELECT 'isrc', identifier FROM mlcore_provider_hydration_item
    WHERE provider = 'spotify' AND identifier_type = 'isrc'
      AND evidence ? 'identity_reference_quarantine'
"""


def held_aliases():
    return CanonicalItemAlias.objects.filter(~Q(status='active') | Q(metadata__has_key=HOLD_KEY))


def identifier_held(source, resource_type, value):
    return held_aliases().filter(source=source, resource_type=resource_type, source_id=value).exists() or (
        source == 'isrc'
        and ProviderHydrationItem.objects.filter(
            provider='spotify', identifier_type='isrc', identifier=value, evidence__has_key=HOLD_KEY
        ).exists()
    )


def stage_holds(*, subjects=False):
    with connection.cursor() as c:
        c.execute('DROP TABLE IF EXISTS tmp_identity_hold, tmp_identity_held_subject')
        c.execute('CREATE TEMP TABLE tmp_identity_hold AS ' + HELD_IDENTIFIER_SQL)
        c.execute('CREATE UNIQUE INDEX ON tmp_identity_hold (scheme, value)')
        c.execute('ANALYZE tmp_identity_hold')
    if subjects:
        # The hold set is usually tiny: let PostgreSQL use (scheme,value) and redirect-key indexes.
        # Avoid forcing full corpus reads when only a few identifiers are held.
        with connection.cursor() as c:
            c.execute("""CREATE TEMP TABLE tmp_identity_held_subject AS
            SELECT DISTINCT e.subject_canonical_item_id AS item_id,
                   e.subject_canonical_item_id AS final_id, 0::integer AS depth
            FROM mlcore_identity_evidence e JOIN tmp_identity_hold h
              ON h.scheme = e.scheme AND h.value = e.value""")
        with connection.cursor() as c:
            c.execute('CREATE UNIQUE INDEX ON tmp_identity_held_subject (item_id)')
            # Native IDs need only a handful of indexed canonical-key probes, not a forced full scan.
            c.execute("""INSERT INTO tmp_identity_held_subject (item_id, final_id, depth)
                SELECT i.id, i.id, 0 FROM tmp_identity_hold h JOIN mlcore_canonical_item i
                  ON i.canonical_key = CASE h.scheme WHEN 'mbid' THEN 'recording_mbid:'
                       WHEN 'msid' THEN 'recording_msid:' WHEN 'spotify_track' THEN 'spotify_track:' END || h.value
                ON CONFLICT (item_id) DO NOTHING""")
            c.execute('ANALYZE tmp_identity_held_subject')
        with connection.cursor() as c:
            for _ in range(MAX_REDIRECT_DEPTH):
                c.execute(FOLLOW_REDIRECT_HOP_SQL.format(table='tmp_identity_held_subject'), [MAX_REDIRECT_DEPTH])
                if not c.rowcount:
                    break


def assert_hold_snapshot():
    """Inside the write transaction, lock against operator quarantine and reject stale staging."""
    with connection.cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtext('mlcore-canonical-alias-materialization'))")
        c.execute(
            """WITH current_holds AS ("""
            + HELD_IDENTIFIER_SQL
            + """), changes AS (
            (SELECT * FROM current_holds EXCEPT SELECT * FROM tmp_identity_hold)
            UNION ALL (SELECT * FROM tmp_identity_hold EXCEPT SELECT * FROM current_holds)
        ) SELECT EXISTS(SELECT 1 FROM changes)"""
        )
        if c.fetchone()[0]:
            raise ValueError('Identity holds changed since staging; rebuild the workspace before writing.')

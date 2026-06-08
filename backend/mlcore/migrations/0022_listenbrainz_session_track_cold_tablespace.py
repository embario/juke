from django.db import migrations


COLD_TABLESPACE_NAME = 'juke_mlcore_cold'
HOT_TABLESPACE_NAME = 'juke_mlcore_hot'
TABLE_NAME = 'mlcore_listenbrainz_session_track'


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_name = %s
        """,
        [table_name],
    )
    return cursor.fetchone() is not None


def _tablespace_exists(cursor, tablespace_name):
    cursor.execute("SELECT 1 FROM pg_tablespace WHERE spcname = %s", [tablespace_name])
    return cursor.fetchone() is not None


def _index_names_for_table(cursor, table_name):
    cursor.execute(
        """
        SELECT index_class.relname
        FROM pg_class table_class
        JOIN pg_namespace table_ns ON table_ns.oid = table_class.relnamespace
        JOIN pg_index table_index ON table_index.indrelid = table_class.oid
        JOIN pg_class index_class ON index_class.oid = table_index.indexrelid
        WHERE table_ns.nspname = current_schema()
          AND table_class.relname = %s
        ORDER BY index_class.relname
        """,
        [table_name],
    )
    return [row[0] for row in cursor.fetchall()]


def _move_table_and_indexes(schema_editor, cursor, *, tablespace_name):
    if not _table_exists(cursor, TABLE_NAME):
        return

    quoted_table = schema_editor.quote_name(TABLE_NAME)
    quoted_tablespace = schema_editor.quote_name(tablespace_name)
    schema_editor.execute(f'ALTER TABLE {quoted_table} SET TABLESPACE {quoted_tablespace}')

    for index_name in _index_names_for_table(cursor, TABLE_NAME):
        quoted_index = schema_editor.quote_name(index_name)
        schema_editor.execute(f'ALTER INDEX {quoted_index} SET TABLESPACE {quoted_tablespace}')


def move_session_track_to_cold(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        if not _tablespace_exists(cursor, COLD_TABLESPACE_NAME):
            raise RuntimeError(f'{COLD_TABLESPACE_NAME} tablespace must exist before moving {TABLE_NAME}.')
        _move_table_and_indexes(schema_editor, cursor, tablespace_name=COLD_TABLESPACE_NAME)


def move_session_track_to_hot(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        if not _tablespace_exists(cursor, HOT_TABLESPACE_NAME):
            raise RuntimeError(f'{HOT_TABLESPACE_NAME} tablespace must exist before moving {TABLE_NAME}.')
        _move_table_and_indexes(schema_editor, cursor, tablespace_name=HOT_TABLESPACE_NAME)


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('mlcore', '0021_training_run_bigint_counters'),
    ]

    operations = [
        migrations.RunPython(move_session_track_to_cold, move_session_track_to_hot),
    ]

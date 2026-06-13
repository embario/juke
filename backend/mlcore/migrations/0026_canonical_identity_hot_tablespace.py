from django.db import migrations


HOT_TABLESPACE_NAME = 'juke_mlcore_hot'
CANONICAL_IDENTITY_TABLES = (
    'mlcore_canonical_item',
    'mlcore_canonical_item_alias',
)


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


def _move_table_and_indexes(schema_editor, cursor, *, table_name, tablespace_name):
    if not _table_exists(cursor, table_name):
        return

    quoted_table = schema_editor.quote_name(table_name)
    quoted_tablespace = schema_editor.quote_name(tablespace_name)
    schema_editor.execute(f'ALTER TABLE {quoted_table} SET TABLESPACE {quoted_tablespace}')

    for index_name in _index_names_for_table(cursor, table_name):
        quoted_index = schema_editor.quote_name(index_name)
        schema_editor.execute(f'ALTER INDEX {quoted_index} SET TABLESPACE {quoted_tablespace}')


def move_canonical_identity_to_hot(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        if not _tablespace_exists(cursor, HOT_TABLESPACE_NAME):
            raise RuntimeError(f'{HOT_TABLESPACE_NAME} tablespace must exist before moving canonical identity tables.')

        for table_name in CANONICAL_IDENTITY_TABLES:
            _move_table_and_indexes(
                schema_editor,
                cursor,
                table_name=table_name,
                tablespace_name=HOT_TABLESPACE_NAME,
            )


def move_canonical_identity_to_default(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        for table_name in CANONICAL_IDENTITY_TABLES:
            _move_table_and_indexes(
                schema_editor,
                cursor,
                table_name=table_name,
                tablespace_name='pg_default',
            )


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('mlcore', '0025_model_evaluation_basket_count'),
    ]

    operations = [
        migrations.RunPython(move_canonical_identity_to_hot, move_canonical_identity_to_default),
    ]

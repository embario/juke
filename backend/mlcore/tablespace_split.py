import os

HOT_TABLESPACE_NAME = 'juke_mlcore_hot'
COLD_TABLESPACE_NAME = 'juke_mlcore_cold'
HOT_TABLESPACE_HOST_PATH_ENV = 'MLCORE_PG_HOT_TABLESPACE_HOST_PATH'
COLD_TABLESPACE_HOST_PATH_ENV = 'MLCORE_PG_COLD_TABLESPACE_HOST_PATH'
HOT_TABLESPACE_PATH = '/var/lib/postgresql/tablespaces/juke_mlcore_hot'
COLD_TABLESPACE_PATH = '/var/lib/postgresql/tablespaces/juke_mlcore_cold'

HOT_TABLES = (
    'mlcore_source_ingestion_run',
    'mlcore_dataset_orchestration_run',
    'mlcore_dataset_shard_ingestion_run',
    'mlcore_listenbrainz_session_track',
    'mlcore_training_run',
    'mlcore_item_cooccurrence',
    'mlcore_model_evaluation',
    'mlcore_model_promotion',
)

COLD_TABLES = (
    'mlcore_listenbrainz_event_ledger',
    'mlcore_listenbrainz_raw_listen',
    'mlcore_normalized_interaction',
)


def _table_exists(cursor, table_name):
    cursor.execute(
        "select 1 from information_schema.tables where table_schema = current_schema() and table_name = %s",
        [table_name],
    )
    return cursor.fetchone() is not None


def _index_names_for_table(cursor, table_name):
    cursor.execute(
        """
        select index_class.relname
        from pg_class table_class
        join pg_namespace table_ns on table_ns.oid = table_class.relnamespace
        join pg_index table_index on table_index.indrelid = table_class.oid
        join pg_class index_class on index_class.oid = table_index.indexrelid
        where table_ns.nspname = current_schema()
          and table_class.relname = %s
        order by index_class.relname
        """,
        [table_name],
    )
    return [row[0] for row in cursor.fetchall()]


def _normalize_tablespace_host_path(path_value, env_name):
    path_value = (path_value or '').strip()
    if not path_value:
        raise RuntimeError(
            f'{env_name} must be set to an absolute filesystem path before applying the MLCore tablespace split.'
        )

    normalized = os.path.normpath(path_value)
    if not os.path.isabs(normalized):
        raise RuntimeError(
            f'{env_name}={path_value!r} is not an absolute filesystem path.'
        )
    return normalized


def _tablespace_location(cursor, tablespace_name):
    cursor.execute(
        "select pg_tablespace_location(oid) from pg_tablespace where spcname = %s",
        [tablespace_name],
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return os.path.normpath(row[0])


def _quote_literal(value):
    return "'" + value.replace("'", "''") + "'"


def _ensure_tablespace(cursor, schema_editor, *, tablespace_name, tablespace_path, env_name):
    existing_location = _tablespace_location(cursor, tablespace_name)
    if existing_location is None:
        quoted_tablespace = schema_editor.quote_name(tablespace_name)
        quoted_location = _quote_literal(tablespace_path)
        cursor.execute(f'CREATE TABLESPACE {quoted_tablespace} LOCATION {quoted_location}')
        return

    if existing_location != tablespace_path:
        raise RuntimeError(
            f'{tablespace_name} already exists at {existing_location!r}, '
            f'but {env_name} points to {tablespace_path!r}.'
        )


def _move_table_and_indexes(schema_editor, cursor, *, table_name, tablespace_name):
    if not _table_exists(cursor, table_name):
        return

    quoted_table = schema_editor.quote_name(table_name)
    quoted_tablespace = schema_editor.quote_name(tablespace_name)
    schema_editor.execute(f'ALTER TABLE {quoted_table} SET TABLESPACE {quoted_tablespace}')
    for index_name in _index_names_for_table(cursor, table_name):
        quoted_index = schema_editor.quote_name(index_name)
        schema_editor.execute(f'ALTER INDEX {quoted_index} SET TABLESPACE {quoted_tablespace}')


def apply_tablespace_split(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    _normalize_tablespace_host_path(
        os.environ.get(HOT_TABLESPACE_HOST_PATH_ENV),
        HOT_TABLESPACE_HOST_PATH_ENV,
    )
    _normalize_tablespace_host_path(
        os.environ.get(COLD_TABLESPACE_HOST_PATH_ENV),
        COLD_TABLESPACE_HOST_PATH_ENV,
    )

    with schema_editor.connection.cursor() as cursor:
        _ensure_tablespace(
            cursor,
            schema_editor,
            tablespace_name=HOT_TABLESPACE_NAME,
            tablespace_path=HOT_TABLESPACE_PATH,
            env_name=HOT_TABLESPACE_HOST_PATH_ENV,
        )
        _ensure_tablespace(
            cursor,
            schema_editor,
            tablespace_name=COLD_TABLESPACE_NAME,
            tablespace_path=COLD_TABLESPACE_PATH,
            env_name=COLD_TABLESPACE_HOST_PATH_ENV,
        )

        for table_name in HOT_TABLES:
            _move_table_and_indexes(
                schema_editor,
                cursor,
                table_name=table_name,
                tablespace_name=HOT_TABLESPACE_NAME,
            )

        for table_name in COLD_TABLES:
            _move_table_and_indexes(
                schema_editor,
                cursor,
                table_name=table_name,
                tablespace_name=COLD_TABLESPACE_NAME,
            )


def revert_tablespace_split(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        for table_name in HOT_TABLES + COLD_TABLES:
            _move_table_and_indexes(
                schema_editor,
                cursor,
                table_name=table_name,
                tablespace_name='pg_default',
            )

from django.db import migrations


INDEX_NAME = 'mlcore_lst_pair_bucket_128_idx'
INDEX_EXPR = (
    "mod(abs(hashtextextended(encode(session_key, 'hex'), 0)), 128), "
    "session_key, "
    "canonical_item_id"
)


def create_pair_bucket_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(
        f"""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME}
        ON mlcore_listenbrainz_session_track ({INDEX_EXPR})
        """
    )


def drop_pair_bucket_index(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    schema_editor.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}')


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ('mlcore', '0012_canonical_items_and_listenbrainz_hot_keys'),
    ]

    operations = [
        migrations.RunPython(create_pair_bucket_index, drop_pair_bucket_index),
    ]

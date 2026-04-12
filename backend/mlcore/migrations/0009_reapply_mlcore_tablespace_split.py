from django.db import migrations

from mlcore.tablespace_split import apply_tablespace_split, revert_tablespace_split


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('mlcore', '0008_mlcore_tablespace_split'),
    ]

    operations = [
        migrations.RunPython(apply_tablespace_split, revert_tablespace_split),
    ]

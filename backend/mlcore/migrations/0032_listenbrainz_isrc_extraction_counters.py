from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlcore', '0031_listenbrainzmsidmbidconflictresolution'),
    ]

    operations = [
        migrations.AddField(
            model_name='listenbrainzidentityshard',
            name='extraction_schema_version',
            field=models.IntegerField(default=1),
        ),
        migrations.AddField(
            model_name='listenbrainzidentityshard',
            name='isrc_observation_count',
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='listenbrainzidentityshard',
            name='unique_isrc_pair_count',
            field=models.BigIntegerField(default=0),
        ),
    ]

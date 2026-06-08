from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlcore', '0020_cooccurrence_cold_tablespace'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trainingrun',
            name='baskets_processed',
            field=models.BigIntegerField(),
        ),
        migrations.AlterField(
            model_name='trainingrun',
            name='items_seen',
            field=models.BigIntegerField(),
        ),
        migrations.AlterField(
            model_name='trainingrun',
            name='pairs_written',
            field=models.BigIntegerField(),
        ),
        migrations.AlterField(
            model_name='trainingrun',
            name='source_row_count',
            field=models.BigIntegerField(),
        ),
    ]

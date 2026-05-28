import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlcore', '0014_cooccurrence_training_bucket'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql='DROP INDEX IF EXISTS mlcore_item_item_a__bfbfe3_idx',
                    reverse_sql=(
                        'CREATE INDEX IF NOT EXISTS mlcore_item_item_a__bfbfe3_idx '
                        'ON mlcore_item_cooccurrence (item_a_juke_id)'
                    ),
                ),
                migrations.RunSQL(
                    sql='DROP INDEX IF EXISTS mlcore_item_item_b__baff90_idx',
                    reverse_sql=(
                        'CREATE INDEX IF NOT EXISTS mlcore_item_item_b__baff90_idx '
                        'ON mlcore_item_cooccurrence (item_b_juke_id)'
                    ),
                ),
                migrations.RunSQL(
                    sql='DROP INDEX IF EXISTS mlcore_item_trainin_32edd1_idx',
                    reverse_sql=(
                        'CREATE INDEX IF NOT EXISTS mlcore_item_trainin_32edd1_idx '
                        'ON mlcore_item_cooccurrence (training_run_id)'
                    ),
                ),
                migrations.RunSQL(
                    sql='DROP INDEX IF EXISTS mlcore_item_cooccurrence_training_run_id_c8e027dc',
                    reverse_sql=(
                        'CREATE INDEX IF NOT EXISTS mlcore_item_cooccurrence_training_run_id_c8e027dc '
                        'ON mlcore_item_cooccurrence (training_run_id)'
                    ),
                ),
            ],
            state_operations=[
                migrations.RemoveIndex(
                    model_name='itemcooccurrence',
                    name='mlcore_item_item_a__bfbfe3_idx',
                ),
                migrations.RemoveIndex(
                    model_name='itemcooccurrence',
                    name='mlcore_item_item_b__baff90_idx',
                ),
                migrations.RemoveIndex(
                    model_name='itemcooccurrence',
                    name='mlcore_item_trainin_32edd1_idx',
                ),
                migrations.AlterField(
                    model_name='itemcooccurrence',
                    name='training_run',
                    field=models.ForeignKey(
                        blank=True,
                        db_index=False,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='cooccurrence_rows',
                        to='mlcore.trainingrun',
                    ),
                ),
            ],
        ),
    ]

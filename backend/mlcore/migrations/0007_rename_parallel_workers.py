from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('mlcore', '0006_dataset_orchestration_runs'),
    ]

    operations = [
        migrations.RenameField(
            model_name='datasetorchestrationrun',
            old_name='parallel_workers',
            new_name='shard_parallelism',
        ),
    ]

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlcore', '0013_listenbrainz_pair_bucket_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='CoOccurrenceTrainingBucket',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('source', models.CharField(max_length=64)),
                ('algorithm_version', models.CharField(max_length=64)),
                ('bucket_count', models.IntegerField()),
                ('bucket_index', models.IntegerField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('running', 'Running'), ('succeeded', 'Succeeded'), ('failed', 'Failed'), ('assumed_succeeded', 'Assumed succeeded')], default='pending', max_length=24)),
                ('rows_written', models.IntegerField(default=0)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True, default='')),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('training_run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cooccurrence_buckets', to='mlcore.trainingrun')),
            ],
            options={
                'db_table': 'mlcore_cooccurrence_training_bucket',
                'ordering': ['training_run', 'bucket_index'],
                'unique_together': {('training_run', 'bucket_count', 'bucket_index')},
            },
        ),
        migrations.AddIndex(
            model_name='cooccurrencetrainingbucket',
            index=models.Index(fields=['training_run', 'status'], name='mlcore_ctb_run_stat_idx'),
        ),
        migrations.AddIndex(
            model_name='cooccurrencetrainingbucket',
            index=models.Index(fields=['source', 'algorithm_version'], name='mlcore_ctb_src_alg_idx'),
        ),
        migrations.AddIndex(
            model_name='cooccurrencetrainingbucket',
            index=models.Index(fields=['bucket_count', 'bucket_index'], name='mlcore_ctb_bucket_idx'),
        ),
    ]

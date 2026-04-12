import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_albumexternalidentifier_artistexternalidentifier_and_more'),
        ('mlcore', '0006_dataset_orchestration_runs'),
    ]

    operations = [
        migrations.RenameField(
            model_name='datasetorchestrationrun',
            old_name='parallel_workers',
            new_name='shard_parallelism',
        ),
        migrations.CreateModel(
            name='ListenBrainzEventLedger',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('event_signature', models.BinaryField(max_length=32, unique=True)),
                ('played_at', models.DateTimeField(db_index=True)),
                ('session_key', models.BinaryField(db_index=True, max_length=32)),
                ('resolution_state', models.PositiveSmallIntegerField(choices=[(0, 'Unresolved'), (1, 'Resolved')], default=0)),
                ('cold_ref', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('import_run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='listenbrainz_event_ledgers', to='mlcore.sourceingestionrun')),
                ('track', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='listenbrainz_event_ledgers', to='catalog.track', to_field='juke_id')),
            ],
            options={
                'db_table': 'mlcore_listenbrainz_event_ledger',
                'ordering': ['played_at', 'id'],
                'indexes': [
                    models.Index(fields=['import_run'], name='mlcore_lbe_import__e9179a_idx'),
                    models.Index(fields=['track'], name='mlcore_lbe_track_i_4c8647_idx'),
                    models.Index(fields=['resolution_state'], name='mlcore_lbe_resolut_8e2ae0_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='ListenBrainzSessionTrack',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('session_key', models.BinaryField(db_index=True, max_length=32)),
                ('first_played_at', models.DateTimeField()),
                ('last_played_at', models.DateTimeField()),
                ('play_count', models.IntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('import_run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='listenbrainz_session_tracks', to='mlcore.sourceingestionrun')),
                ('track', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='listenbrainz_session_tracks', to='catalog.track', to_field='juke_id')),
            ],
            options={
                'db_table': 'mlcore_listenbrainz_session_track',
                'ordering': ['first_played_at', 'id'],
                'indexes': [
                    models.Index(fields=['track'], name='mlcore_lst_track_i_5d5e20_idx'),
                    models.Index(fields=['import_run'], name='mlcore_lst_import__6d7bf6_idx'),
                    models.Index(fields=['last_played_at'], name='mlcore_lst_last_pl_4a4ec9_idx'),
                ],
                'unique_together': {('session_key', 'track')},
            },
        ),
    ]

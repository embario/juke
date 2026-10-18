from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('mlcore', '0034_identity_evidence')]
    operations = [
        migrations.CreateModel(
            name='MusicBrainzRecordingMetadata',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recording_mbid', models.UUIDField()),
                ('source_version', models.CharField(max_length=64)),
                ('source_checksum', models.CharField(max_length=64)),
                ('title', models.TextField()),
                ('artist_credit', models.TextField()),
                ('duration_ms', models.IntegerField(null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'mlcore_musicbrainz_recording_metadata',
                'db_tablespace': 'juke_mlcore_cold',
                'unique_together': {('recording_mbid', 'source_version')},
            },
        ),
        migrations.AddIndex(
            model_name='canonicalitemalias',
            index=models.Index(
                fields=['source', 'resource_type', 'source_id'],
                name='mlcore_cia_held_idx',
                condition=~models.Q(status='active') | models.Q(metadata__has_key='identity_reference_quarantine'),
            ),
        ),
        migrations.AddIndex(
            model_name='providerhydrationitem',
            index=models.Index(
                fields=['identifier'],
                name='mlcore_phi_held_idx',
                condition=models.Q(provider='spotify', identifier_type='isrc', evidence__has_key='identity_reference_quarantine'),
            ),
        ),
    ]

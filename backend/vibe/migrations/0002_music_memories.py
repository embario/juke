import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('vibe', '0001_initial'), ('juke_auth', '0008_spotifyconnectticket')]

    operations = [
        migrations.CreateModel(
            name='MusicMemory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(blank=True, max_length=200)),
                ('body', models.TextField(blank=True)),
                ('occurred_at', models.DateTimeField(db_index=True)),
                ('place', models.CharField(blank=True, max_length=200)),
                ('people', models.JSONField(default=list)),
                ('songs', models.JSONField(default=list)),
                ('tags', models.JSONField(default=list)),
                ('generated_tags', models.JSONField(default=list)),
                ('excluded_tags', models.JSONField(default=list)),
                ('classification', models.JSONField(default=dict)),
                ('recommendation_signals', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='music_memories', to='juke_auth.musicprofile')),
            ],
            options={'ordering': ('-occurred_at', '-created_at'), 'indexes': [models.Index(fields=['profile', '-occurred_at'], name='vibe_mem_profile_date_idx')]},
        ),
        migrations.CreateModel(
            name='MemoryTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=60)),
                ('normalized', models.CharField(max_length=60)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memory_tags', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('normalized',)},
        ),
        migrations.AddConstraint(model_name='memorytag', constraint=models.UniqueConstraint(fields=('user', 'normalized'), name='vibe_tag_user_normalized_unique')),
        migrations.CreateModel(
            name='MemoryMedia',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(max_length=8)),
                ('filename', models.CharField(max_length=255)),
                ('content_type', models.CharField(max_length=64)),
                ('content', models.BinaryField()),
                ('size', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('memory', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='media', to='vibe.musicmemory')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memory_media', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]

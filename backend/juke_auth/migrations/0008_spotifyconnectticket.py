import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('juke_auth', '0007_musicprofile_onboarding_completed_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='SpotifyConnectTicket',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('secret_digest', models.CharField(max_length=64, unique=True)),
                ('return_to', models.CharField(max_length=2048)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='spotify_connect_tickets',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.AddIndex(
            model_name='spotifyconnectticket',
            index=models.Index(fields=['user', 'created_at'], name='spotify_tkt_user_created_idx'),
        ),
    ]

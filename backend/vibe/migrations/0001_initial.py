import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name='VibeAccountCapability',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cloud_ai_enabled', models.BooleanField(default=False)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='vibe_capability', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='VibeAuthorizationCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_digest', models.CharField(max_length=64, unique=True)),
                ('client_id', models.CharField(max_length=64)),
                ('redirect_uri', models.CharField(max_length=255)),
                ('state', models.CharField(max_length=512)),
                ('code_challenge', models.CharField(max_length=128)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('consumed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='VibeEncryptedRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('record_id', models.UUIDField()),
                ('kind', models.CharField(choices=[('chatMessage', 'Chat Message'), ('conversationState', 'Conversation State'), ('tasteMemory', 'Taste Memory')], max_length=32)),
                ('ciphertext', models.BinaryField()),
                ('client_modified_at', models.DateTimeField()),
                ('encryption_version', models.PositiveSmallIntegerField()),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vibe_encrypted_chat_records', to=settings.AUTH_USER_MODEL)),
            ],
            options={'indexes': [models.Index(fields=['user', 'modified_at'], name='vibe_enc_user_mod_idx')]},
        ),
        migrations.CreateModel(
            name='VibeEncryptedChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='changes', to='vibe.vibeencryptedrecord')),
            ],
            options={'indexes': [models.Index(fields=['record', 'id'], name='vibe_chg_record_id_idx')]},
        ),
        migrations.AddConstraint(
            model_name='vibeencryptedrecord',
            constraint=models.UniqueConstraint(fields=('user', 'record_id'), name='vibe_chat_user_record_unique'),
        ),
    ]

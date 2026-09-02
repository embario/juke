import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name='JournalAccountCapability',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cloud_ai_enabled', models.BooleanField(default=False)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='journal_capability', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='JournalAuthorizationCode',
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
            name='JournalEncryptedRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('record_id', models.UUIDField()),
                ('kind', models.CharField(choices=[('authoredEntry', 'Authored Entry'), ('listeningReflection', 'Listening Reflection'), ('chatMessage', 'Chat Message')], max_length=32)),
                ('ciphertext', models.BinaryField()),
                ('client_modified_at', models.DateTimeField()),
                ('encryption_version', models.PositiveSmallIntegerField()),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='journal_encrypted_records', to=settings.AUTH_USER_MODEL)),
            ],
            options={'indexes': [models.Index(fields=['user', 'modified_at'], name='journal_jou_user_id_8a22d6_idx')]},
        ),
        migrations.CreateModel(
            name='JournalEncryptedChange',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='changes', to='journal.journalencryptedrecord')),
            ],
            options={'indexes': [models.Index(fields=['record', 'id'], name='journal_jou_record__d3f655_idx')]},
        ),
        migrations.AddConstraint(
            model_name='journalencryptedrecord',
            constraint=models.UniqueConstraint(fields=('user', 'record_id'), name='journal_record_user_record_unique'),
        ),
    ]

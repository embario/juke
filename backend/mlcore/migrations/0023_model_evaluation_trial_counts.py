from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlcore', '0022_listenbrainz_session_track_cold_tablespace'),
    ]

    operations = [
        migrations.AddField(
            model_name='modelevaluation',
            name='n_trials',
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='modelevaluation',
            name='n_cold_trials',
            field=models.BigIntegerField(default=0),
        ),
    ]

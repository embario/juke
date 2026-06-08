from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlcore', '0023_model_evaluation_trial_counts'),
    ]

    operations = [
        migrations.AddField(
            model_name='modelevaluation',
            name='evaluation_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='modelevaluation',
            name='evaluation_elapsed_seconds',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='modelevaluation',
            name='evaluation_trials_per_second',
            field=models.FloatField(blank=True, null=True),
        ),
    ]

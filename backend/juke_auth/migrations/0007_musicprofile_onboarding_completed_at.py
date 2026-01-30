from django.db import migrations, models
from django.utils.dateparse import parse_datetime


def backfill_onboarding_completed_at(apps, schema_editor):
    MusicProfile = apps.get_model('juke_auth', 'MusicProfile')
    for profile in MusicProfile.objects.exclude(custom_data=None):
        custom_data = profile.custom_data or {}
        completed_at = custom_data.get('onboarding_completed_at')
        if completed_at and not profile.onboarding_completed_at:
            parsed = parse_datetime(completed_at)
            if parsed is None:
                continue
            profile.onboarding_completed_at = parsed
            profile.save(update_fields=['onboarding_completed_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('juke_auth', '0006_musicprofile_custom_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='musicprofile',
            name='onboarding_completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_onboarding_completed_at, migrations.RunPython.noop),
    ]

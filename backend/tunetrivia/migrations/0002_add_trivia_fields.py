from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tunetrivia', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tunetriviaguess',
            name='trivia_guess',
            field=models.CharField(blank=True, max_length=300, null=True),
        ),
        migrations.AddField(
            model_name='tunetriviaguess',
            name='trivia_correct',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tunetrivialeaderboardentry',
            name='total_correct_trivia',
            field=models.IntegerField(default=0),
        ),
    ]

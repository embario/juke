from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('juke_auth', '0004_musicprofile_unique_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='musicprofile',
            name='city_lat',
            field=models.FloatField(
                blank=True,
                db_index=True,
                help_text='Latitude rounded to 2 decimal places (~1.1km / city-centroid precision)',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='musicprofile',
            name='city_lng',
            field=models.FloatField(
                blank=True,
                db_index=True,
                help_text='Longitude rounded to 2 decimal places (~1.1km / city-centroid precision)',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='musicprofile',
            name='clout',
            field=models.FloatField(
                default=0.0,
                help_text='Streaming clout metric, 0.0-1.0',
            ),
        ),
    ]

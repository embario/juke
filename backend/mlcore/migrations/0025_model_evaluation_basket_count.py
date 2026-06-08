from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlcore', '0024_model_evaluation_runtime_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='modelevaluation',
            name='n_baskets',
            field=models.BigIntegerField(default=0),
        ),
    ]

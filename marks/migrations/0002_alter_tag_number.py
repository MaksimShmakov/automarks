                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tag',
            name='number',
            field=models.CharField(blank=True, max_length=20, unique=True),
        ),
    ]

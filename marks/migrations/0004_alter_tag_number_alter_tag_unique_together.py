                                                

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0003_alter_branch_unique_together_branch_code_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tag',
            name='number',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AlterUniqueTogether(
            name='tag',
            unique_together={('branch', 'number')},
        ),
    ]

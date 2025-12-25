


from django.db import migrations, models


class Migration(migrations.Migration):


    dependencies = [
        ('marks', '0002_alter_tag_number'),
    ]


    operations = [
        migrations.AlterUniqueTogether(
            name='branch',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='branch',
            name='code',
            field=models.CharField(default=None, max_length=10),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name='branch',
            unique_together={('bot', 'code')},
        ),
    ]

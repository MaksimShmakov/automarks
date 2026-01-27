from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marks", "0008_bot_description_salebot_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="tag",
            name="budget",
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=12, verbose_name="Бюджет"),
        ),
    ]

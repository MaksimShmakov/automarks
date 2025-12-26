from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marks", "0007_bot_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="bot",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="bot",
            name="salebot_url",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
    ]

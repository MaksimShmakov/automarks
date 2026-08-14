"""Флаг «В сейлботе достроен экспорт» — обязателен для активации воронки."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marks", "0032_tiktok_funnels"),
    ]

    operations = [
        migrations.AddField(
            model_name="tiktokfunnelrequest",
            name="salebot_export_ready",
            field=models.BooleanField(
                default=False,
                help_text="В сейлботе достроен экспорт — обязательно для активации",
            ),
        ),
    ]

"""Раздел TikTok-воронок: TikTokAccount + TikTokFunnelRequest.

Порт standalone-сервиса el-tiktok-funnels-auto в automarks. Источник правды —
эти таблицы в БД automarks; дублирование в склад — через n8n (см.
marks.services.tiktok_sync), не через миграции.
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("marks", "0031_outboundnotification"),
    ]

    operations = [
        migrations.CreateModel(
            name="TikTokAccount",
            fields=[
                ("account_no", models.CharField(max_length=255, primary_key=True, serialize=False)),
                ("advertiser_id", models.CharField(blank=True, default="", max_length=255)),
                ("access_token", models.CharField(max_length=500)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "TikTok-кабинет",
                "verbose_name_plural": "TikTok-кабинеты",
                "ordering": ["account_no"],
            },
        ),
        migrations.CreateModel(
            name="TikTokFunnelRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "landing_endpoint",
                    models.CharField(
                        blank=True,
                        help_text="location.pathname лендинга, например /pasha_all",
                        max_length=255,
                        null=True,
                        unique=True,
                    ),
                ),
                ("offer", models.CharField(blank=True, default="", help_text="Оффер/метка, например ell010005", max_length=255)),
                ("bot_url", models.CharField(blank=True, default="", help_text="Ссылка на бота", max_length=500)),
                ("bot_name", models.CharField(blank=True, default="", max_length=255)),
                (
                    "page_type",
                    models.CharField(
                        blank=True,
                        choices=[("button", "С кнопкой"), ("mirror", "Зеркало")],
                        default="",
                        max_length=20,
                    ),
                ),
                ("pixel_code", models.CharField(blank=True, default="", max_length=255)),
                ("account_no", models.CharField(blank=True, default="", max_length=255)),
                ("utm_source", models.CharField(blank=True, default="", max_length=255)),
                ("utm_medium", models.CharField(blank=True, default="", max_length=255)),
                ("utm_term", models.CharField(blank=True, default="", max_length=255)),
                ("comment", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Ожидает подключения"),
                            ("active", "Активна"),
                            ("archived", "В архиве"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "warehouse_synced",
                    models.BooleanField(
                        default=False,
                        help_text="Строка воронки успешно записана в склад activation_data.tt_funnels",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "TikTok-воронка",
                "verbose_name_plural": "TikTok-воронки",
                "ordering": ["-id"],
            },
        ),
    ]

                                                

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('marks', '0004_alter_tag_number_alter_tag_unique_together'),
    ]

    operations = [
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('admin', 'Максимальный'), ('manager', 'Руководитель'), ('marketer', 'Линейный (автометки)')], default='marketer', max_length=20)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='TrafficReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.DateField()),
                ('platform', models.CharField(choices=[('tg', 'Telegram'), ('vk', 'VK'), ('tt', 'TikTok'), ('ig', 'Instagram'), ('other', 'Другое')], default='other', max_length=20)),
                ('vendor', models.CharField(help_text='Подрядчик/исполнитель', max_length=255)),
                ('spend', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('impressions', models.IntegerField(default=0)),
                ('clicks', models.IntegerField(default=0)),
                ('leads_warm', models.IntegerField(default=0)),
                ('leads_cold', models.IntegerField(default=0)),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='traffic_reports', to='marks.product')),
            ],
            options={
                'ordering': ['-month', 'platform', 'vendor'],
            },
        ),
        migrations.CreateModel(
            name='PatchNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('title', models.CharField(max_length=255)),
                ('change_description', models.TextField()),
                ('change_type', models.CharField(default='update', help_text='например: план, метки, воронка, отчёт', max_length=50)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='patch_notes', to='marks.branch')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='bot',
            name='product',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='bots', to='marks.product'),
        ),
        migrations.CreateModel(
            name='PlanMonthly',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.DateField(help_text='Первое число месяца (YYYY-MM-01)')),
                ('budget', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('revenue_target', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('warm_leads_target', models.IntegerField(default=0)),
                ('cold_leads_target', models.IntegerField(default=0)),
                ('notes', models.TextField(blank=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='plans', to='marks.product')),
            ],
            options={
                'ordering': ['-month'],
                'unique_together': {('product', 'month')},
            },
        ),
        migrations.CreateModel(
            name='Funnel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='funnels', to='marks.product')),
            ],
            options={
                'unique_together': {('product', 'name')},
            },
        ),
        migrations.CreateModel(
            name='BranchPlanMonthly',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.DateField()),
                ('warm_leads', models.IntegerField(default=0)),
                ('cold_leads', models.IntegerField(default=0)),
                ('expected_revenue', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('comment', models.CharField(blank=True, max_length=255)),
                ('branch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='plans', to='marks.branch')),
            ],
            options={
                'ordering': ['branch__bot__name', 'branch__name', '-month'],
                'unique_together': {('branch', 'month')},
            },
        ),
    ]

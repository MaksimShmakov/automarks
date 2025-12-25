

from django.db import migrations, models


BOT_GROUP_NAME = "Bot Operators"


def create_bot_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name=BOT_GROUP_NAME)


def drop_bot_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=BOT_GROUP_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0005_product_userprofile_trafficreport_patchnote_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(choices=[('admin', 'Максимальный'), ('manager', 'Руководитель'), ('marketer', 'Линейный (автометки)'), ('bot_user', 'Оператор ботов')], default='marketer', max_length=20),
        ),
        migrations.RunPython(create_bot_group, drop_bot_group),
    ]

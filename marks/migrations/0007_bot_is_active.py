from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("marks", "0006_alter_userprofile_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="bot",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]


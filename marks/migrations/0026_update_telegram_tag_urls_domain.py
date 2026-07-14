from django.db import migrations


OLD_DOMAIN = "https://t.me/"
NEW_DOMAIN = "https://telegram.me/"


def _swap_domain(apps, old, new):
    Tag = apps.get_model("marks", "Tag")
    for tag in Tag.objects.filter(url__startswith=old):
        tag.url = new + tag.url[len(old):]
        tag.save(update_fields=["url"])


def forwards(apps, schema_editor):
    _swap_domain(apps, OLD_DOMAIN, NEW_DOMAIN)


def backwards(apps, schema_editor):
    _swap_domain(apps, NEW_DOMAIN, OLD_DOMAIN)


class Migration(migrations.Migration):

    dependencies = [
        ("marks", "0025_taskrequest_feedback_columns_portable_after_photo"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

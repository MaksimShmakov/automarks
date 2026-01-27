from django.db import migrations, models


def unset_default_budget(apps, schema_editor):
    Tag = apps.get_model("marks", "Tag")
    Tag.objects.filter(budget=0).update(budget=None)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("marks", "0009_tag_budget"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tag",
            name="budget",
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=12, null=True, verbose_name="Бюджет"),
        ),
        migrations.RunPython(unset_default_budget, noop),
    ]

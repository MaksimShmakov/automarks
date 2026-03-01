from django.db import migrations


def fix_legacy_feedback_comment_column(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'marks_taskrequest'
              AND column_name = 'feedback_comment'
            LIMIT 1
            """
        )
        if cursor.fetchone() is None:
            return

        cursor.execute(
            "ALTER TABLE public.marks_taskrequest ALTER COLUMN feedback_comment SET DEFAULT ''"
        )
        cursor.execute(
            "UPDATE public.marks_taskrequest SET feedback_comment = '' WHERE feedback_comment IS NULL"
        )
        cursor.execute(
            "ALTER TABLE public.marks_taskrequest ALTER COLUMN feedback_comment DROP NOT NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("marks", "0014_experiment"),
    ]

    operations = [
        migrations.RunPython(
            fix_legacy_feedback_comment_column,
            reverse_code=migrations.RunPython.noop,
        ),
    ]


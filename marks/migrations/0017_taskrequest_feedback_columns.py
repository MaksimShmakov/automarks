from django.db import migrations


def ensure_feedback_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'marks_taskrequest'
            """
        )
        cols = {row[0] for row in cursor.fetchall()}

        if "tg_username" not in cols:
            cursor.execute(
                "ALTER TABLE public.marks_taskrequest ADD COLUMN tg_username varchar(255) DEFAULT ''"
            )
        if "feedback_comment" not in cols:
            cursor.execute(
                "ALTER TABLE public.marks_taskrequest ADD COLUMN feedback_comment text DEFAULT ''"
            )

        cursor.execute(
            "ALTER TABLE public.marks_taskrequest ALTER COLUMN tg_username SET DEFAULT ''"
        )
        cursor.execute(
            "UPDATE public.marks_taskrequest SET tg_username = '' WHERE tg_username IS NULL"
        )
        cursor.execute(
            "ALTER TABLE public.marks_taskrequest ALTER COLUMN tg_username DROP NOT NULL"
        )

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
        ("marks", "0016_taskrequest_relax_legacy_columns"),
    ]

    operations = [
        migrations.RunPython(
            ensure_feedback_columns,
            reverse_code=migrations.RunPython.noop,
        ),
    ]


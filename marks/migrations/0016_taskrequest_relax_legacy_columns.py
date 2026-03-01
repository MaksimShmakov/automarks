from django.db import migrations


MODEL_TASKREQUEST_COLUMNS = {
    "id",
    "task_type",
    "status",
    "cjm_url",
    "tz_url",
    "build_name",
    "build_token",
    "comment",
    "deadline",
    "created_by_id",
    "created_at",
    "completed_at",
    "updated_at",
}


def _quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def relax_legacy_taskrequest_columns(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return

    table_name = "marks_taskrequest"
    q_table = _quote_ident(table_name)

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
            """,
            [table_name],
        )
        columns = cursor.fetchall()

        for column_name, data_type, is_nullable, column_default in columns:
            if column_name in MODEL_TASKREQUEST_COLUMNS:
                continue

            q_col = _quote_ident(column_name)

            if data_type in {"character varying", "text", "character"} and column_default is None:
                cursor.execute(
                    f"ALTER TABLE public.{q_table} ALTER COLUMN {q_col} SET DEFAULT %s",
                    [""],
                )
                cursor.execute(
                    f"UPDATE public.{q_table} SET {q_col} = %s WHERE {q_col} IS NULL",
                    [""],
                )
            elif data_type == "boolean" and column_default is None:
                cursor.execute(
                    f"ALTER TABLE public.{q_table} ALTER COLUMN {q_col} SET DEFAULT FALSE"
                )

            if is_nullable == "NO":
                cursor.execute(
                    f"ALTER TABLE public.{q_table} ALTER COLUMN {q_col} DROP NOT NULL"
                )


class Migration(migrations.Migration):

    dependencies = [
        ("marks", "0015_taskrequest_feedback_comment_compat"),
    ]

    operations = [
        migrations.RunPython(
            relax_legacy_taskrequest_columns,
            reverse_code=migrations.RunPython.noop,
        ),
    ]


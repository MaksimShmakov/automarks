from django.db import migrations


def _quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def ensure_taskrequest_feedback_columns_portable(apps, schema_editor):
    TaskRequest = apps.get_model("marks", "TaskRequest")
    connection = schema_editor.connection
    table_name = TaskRequest._meta.db_table
    q_table = _quote_ident(table_name)

    with connection.cursor() as cursor:
        existing_columns = {
            column.name for column in connection.introspection.get_table_description(cursor, table_name)
        }

        if "tg_username" not in existing_columns:
            cursor.execute(
                f"ALTER TABLE {q_table} ADD COLUMN {_quote_ident('tg_username')} varchar(255) DEFAULT ''"
            )

        if "feedback_comment" not in existing_columns:
            cursor.execute(
                f"ALTER TABLE {q_table} ADD COLUMN {_quote_ident('feedback_comment')} text DEFAULT ''"
            )


class Migration(migrations.Migration):

    dependencies = [
        ("marks", "0024_taskrequest_photo"),
    ]

    operations = [
        migrations.RunPython(
            ensure_taskrequest_feedback_columns_portable,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

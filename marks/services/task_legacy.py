import logging
from typing import Iterable

from django.db import connection

from ..models import TaskRequest

logger = logging.getLogger(__name__)


def _quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def _task_table_name():
    return TaskRequest._meta.db_table


def task_legacy_columns():
    table_name = _task_table_name()
    try:
        with connection.cursor() as cursor:
            return {column.name for column in connection.introspection.get_table_description(cursor, table_name)}
    except Exception:
        logger.exception("Failed to read legacy columns for table %s", table_name)
        return set()


def has_task_legacy_column(column_name):
    return column_name in task_legacy_columns()


def set_task_tg_username(task_id, tg_username):
    if not has_task_legacy_column("tg_username"):
        return
    table_name = _task_table_name()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {_quote_ident(table_name)} SET {_quote_ident('tg_username')} = %s WHERE id = %s",
                [(tg_username or "").strip(), task_id],
            )
    except Exception:
        logger.exception("Failed to save tg_username for task_id=%s", task_id)


def get_task_tg_username(task_id):
    if not has_task_legacy_column("tg_username"):
        return ""
    table_name = _task_table_name()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COALESCE({_quote_ident('tg_username')}, '') FROM {_quote_ident(table_name)} WHERE id = %s",
                [task_id],
            )
            row = cursor.fetchone()
            return (row[0] or "").strip() if row else ""
    except Exception:
        logger.exception("Failed to read tg_username for task_id=%s", task_id)
        return ""


def set_task_feedback_comment(task_id, feedback_comment):
    if not has_task_legacy_column("feedback_comment"):
        logger.warning("Skipping feedback_comment save for task_id=%s because column is missing", task_id)
        return
    table_name = _task_table_name()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {_quote_ident(table_name)} SET {_quote_ident('feedback_comment')} = %s WHERE id = %s",
                [(feedback_comment or "").strip(), task_id],
            )
    except Exception:
        logger.exception("Failed to save feedback_comment for task_id=%s", task_id)


def get_task_feedback_map(task_ids: Iterable[int]):
    task_ids = [int(v) for v in task_ids if v]
    if not task_ids or not has_task_legacy_column("feedback_comment"):
        return {}

    table_name = _task_table_name()
    placeholders = ", ".join(["%s"] * len(task_ids))
    sql = (
        f"SELECT id, COALESCE({_quote_ident('feedback_comment')}, '') "
        f"FROM {_quote_ident(table_name)} WHERE id IN ({placeholders})"
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, task_ids)
            return {row[0]: (row[1] or "") for row in cursor.fetchall()}
    except Exception:
        logger.exception("Failed to read feedback map for task ids")
        return {}

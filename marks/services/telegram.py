import html
import logging
from datetime import datetime as dt_datetime
from urllib.error import HTTPError, URLError
from urllib import parse, request
import json

from django.conf import settings
from django.utils import timezone

from ..models import TaskRequest

logger = logging.getLogger(__name__)


def _clean_env_value(value):
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def _safe(value):
    return html.escape(str(value))


def _format_datetime(dt):
    if not dt:
        return "-"
    return timezone.localtime(dt).strftime("%d.%m.%Y %H:%M")


def _format_deadline(value):
    if not value:
        return "-"
    if isinstance(value, dt_datetime):
        return timezone.localtime(value).strftime("%d.%m.%Y %H:%M")
    return value.strftime("%d.%m.%Y")


def _mask_token(value):
    value = (value or "").strip()
    if len(value) <= 8:
        return value or "-"
    return f"{value[:4]}...{value[-4:]}"


def _format_branches(task):
    return _safe(task.get_bot_branch_text())


def _build_task_details(task):
    lines = [
        f"ID: #{task.id}",
        f"Тип: {_safe(task.get_task_type_display())}",
        f"Статус: {_safe(task.get_status_display())}",
        f"Создал: {_safe(task.created_by.username if task.created_by else '-')}",
        f"Создано: {_format_datetime(task.created_at)}",
        f"Дедлайн: {_format_deadline(task.deadline)}",
        f"Ветки: {_format_branches(task)}",
    ]

    if task.task_type == TaskRequest.Type.PATCH:
        lines.append(f"CJM: {_safe(task.cjm_url or '-')}")
    elif task.task_type == TaskRequest.Type.MAILING:
        lines.append(f"ТЗ: {_safe(task.tz_url or '-')}")
    elif task.task_type == TaskRequest.Type.BUILD:
        lines.extend(
            [
                f"Бот и ветки: {_safe(task.get_bot_branch_text())}",
                f"Токен: {_safe(_mask_token(task.build_token))}",
                f"CJM: {_safe(task.cjm_url or '-')}",
            ]
        )

    if task.comment:
        lines.append(f"Комментарий: {_safe(task.comment)}")
    return "\n".join(lines)


def _send_message(chat_id, text):
    token = _clean_env_value(getattr(settings, "TELEGRAM_NOTIFY_BOT_TOKEN", ""))
    chat_id = _clean_env_value(chat_id)
    if not token or not chat_id:
        return False, "Не задан TELEGRAM_NOTIFY_BOT_TOKEN или chat_id"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    data = parse.urlencode(payload).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        req = request.Request(url=url, data=data, method="POST")
        with request.urlopen(req, timeout=7):
            return True, ""
    except HTTPError as exc:
        details = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            details = data.get("description") or body
        except Exception:
            details = str(exc)
        logger.exception("Telegram HTTP error")
        return False, f"Telegram API error: {details}"
    except URLError as exc:
        logger.exception("Telegram URL error")
        return False, f"Telegram network error: {exc.reason}"
    except Exception:
        logger.exception("Failed to send Telegram notification")
        return False, "Неизвестная ошибка отправки в Telegram"


def notify_new_task(task):
    chat_id = getattr(settings, "TELEGRAM_NOTIFY_NEW_TASKS_CHAT_ID", "")
    platform_name = (getattr(settings, "TASKS_PLATFORM_NAME", "") or "").strip()
    header = f"[{_safe(platform_name)}] Новая задача" if platform_name else "Новая задача"
    text = f"{header}\n\n{_build_task_details(task)}"
    return _send_message(chat_id=chat_id, text=text)


def notify_status_change(task, old_status, changed_by):
    chat_id = getattr(settings, "TELEGRAM_NOTIFY_STATUS_CHAT_ID", "")
    platform_name = (getattr(settings, "TASKS_PLATFORM_NAME", "") or "").strip()
    try:
        old_label = task.Status(old_status).label
    except Exception:
        old_label = old_status
    new_label = task.get_status_display()
    header = f"[{_safe(platform_name)}] Изменение статуса задачи" if platform_name else "Изменение статуса задачи"
    details = _build_task_details(task)
    text = (
        f"{header}\n\n"
        f"Было: {_safe(old_label)}\n"
        f"Стало: {_safe(new_label)}\n"
        f"Изменил: {_safe(changed_by.username if changed_by else '-')}\n\n"
        f"{details}"
    )
    return _send_message(chat_id=chat_id, text=text)

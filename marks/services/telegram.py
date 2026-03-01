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
    try:
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        dt = timezone.localtime(dt)
    except Exception:
        pass
    return dt.strftime("%d.%m.%Y %H:%M")


def _format_deadline(value):
    if not value:
        return "-"
    if isinstance(value, dt_datetime):
        try:
            if timezone.is_naive(value):
                value = timezone.make_aware(value, timezone.get_current_timezone())
            value = timezone.localtime(value)
        except Exception:
            pass
        return value.strftime("%d.%m.%Y %H:%M")
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


def _normalize_direct_chat(value):
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("@"):
        return raw
    if raw.lstrip("-").isdigit():
        return raw
    return f"@{raw}"


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


def notify_done_to_user(task, tg_username):
    raw_target = (tg_username or "").strip()
    direct_chat_id = _normalize_direct_chat(raw_target)
    if not direct_chat_id:
        return False, "Не указан username/chat_id для персонального уведомления."

    mention = raw_target if raw_target.startswith("@") else f"@{raw_target}"
    platform_name = (getattr(settings, "TASKS_PLATFORM_NAME", "") or "").strip()
    header = f"[{_safe(platform_name)}] Задача выполнена" if platform_name else "Задача выполнена"
    text = (
        f"{header}\n\n"
        f"Получатель: {_safe(mention)}\n"
        f"Ваша задача #{task.id} переведена в статус: {_safe(task.get_status_display())}\n"
        f"Тип: {_safe(task.get_task_type_display())}\n"
        f"Дедлайн: {_format_deadline(task.deadline)}\n"
        f"Бот и ветки: {_format_branches(task)}"
    )
    ok, error = _send_message(chat_id=direct_chat_id, text=text)
    if ok:
        return True, ""

    # Usernames are usually not valid chat_id for direct bot messages.
    # Fallback: notify in status chat with @mention.
    status_chat_id = getattr(settings, "TELEGRAM_NOTIFY_STATUS_CHAT_ID", "")
    if raw_target.lstrip("-").isdigit() or not status_chat_id:
        return False, error
    fallback_ok, fallback_error = _send_message(chat_id=status_chat_id, text=text)
    if fallback_ok:
        return True, ""
    return False, fallback_error or error

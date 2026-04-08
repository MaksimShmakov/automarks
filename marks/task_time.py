from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


TASK_INPUT_FORMATS = (
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
)
TASK_DATETIME_FORMAT = "%d.%m.%Y %H:%M"


def get_tasks_timezone():
    tz_name = (
        getattr(settings, "TASKS_TIME_ZONE", "")
        or getattr(settings, "WEEKLY_TASKS_REPORT_TZ", "")
        or getattr(settings, "TIME_ZONE", "UTC")
        or "UTC"
    ).strip()
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return timezone.get_default_timezone()


def ensure_task_timezone(value):
    if not value:
        return value
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_default_timezone())
    return timezone.localtime(value, get_tasks_timezone())


def format_task_datetime(value, fmt=TASK_DATETIME_FORMAT, empty="-"):
    if not value:
        return empty
    try:
        return ensure_task_timezone(value).strftime(fmt)
    except Exception:
        return empty


def parse_task_input_datetime(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    for fmt in TASK_INPUT_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
            return timezone.make_aware(parsed, get_tasks_timezone())
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {value}")


def build_task_day_window(day_from=None, day_to=None):
    tz = get_tasks_timezone()
    dt_from = None
    dt_to = None
    if day_from:
        dt_from = datetime.combine(day_from, datetime.min.time(), tzinfo=tz)
    if day_to:
        dt_to = datetime.combine(day_to, datetime.max.time(), tzinfo=tz)
    return dt_from, dt_to

from django import template

from marks.task_time import format_task_datetime

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Позволяет доставать элемент из списка кортежей."""
    for num, name in dictionary:
        if num == key:
            return name
    return ""


@register.filter(name="abs")
def absolute(value):
    try:
        return abs(value)
    except Exception:
        try:
            from decimal import Decimal
            return abs(Decimal(str(value)))
        except Exception:
            try:
                return abs(float(value))
            except Exception:
                return value


@register.filter(name="has_group")
def has_group(user, group_name: str):
    try:
        return user.is_authenticated and user.groups.filter(name=str(group_name)).exists()
    except Exception:
        return False


@register.filter(name="has_any_group")
def has_any_group(user, names: str):
    try:
        wanted = {n.strip() for n in str(names).split(',') if n.strip()}
        if not wanted:
            return False
        return user.is_authenticated and user.groups.filter(name__in=list(wanted)).exists()
    except Exception:
        return False


@register.filter(name="task_datetime")
def task_datetime(value, fmt="%d.%m.%Y %H:%M"):
    try:
        return format_task_datetime(value, fmt=fmt)
    except Exception:
        return "-"

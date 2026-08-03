"""Сборка utm_campaign и готового URL с метками.

Важно: значения UTM НЕ экранируем — в content/term встречаются плейсхолдеры рекламных
кабинетов (`{ad_id}`, `{keyword}`) и разделители (`tg:ad:2`), которые должны попасть в
ссылку буквально, как в справочнике (лист 05). Значения валидируются формой (без пробелов).
"""

UTM_ORDER = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]


def build_campaign(mark_type, direction, funnel, name):
    """campaign = тип_направление_воронка_имя (напр. acq_oge_bot_pyweek2026)."""
    return f"{mark_type}_{direction}_{funnel}_{name}"


def build_full_url(original_url, utm):
    """original_url + UTM-query. utm — dict {utm_source: ..., ...}. Пустые пропускаем."""
    query = "&".join(f"{key}={utm[key]}" for key in UTM_ORDER if utm.get(key))
    if not query:
        return original_url
    separator = "&" if "?" in original_url else "?"
    return f"{original_url}{separator}{query}"

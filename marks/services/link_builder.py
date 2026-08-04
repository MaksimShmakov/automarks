"""Сборка utm_campaign и готового URL с метками + валидация метки против справочника."""

import re

UTM_ORDER = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]

NAME_RE = re.compile(r"^[a-z0-9-]+$")


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


def _source_ok(source, sets):
    if source in sets.get("source", set()):
        return True
    return any(
        source.startswith(prefix) and NAME_RE.match(source)
        for prefix in sets.get("source_template_prefixes", [])
    )


def validate_tag_utm_row(row, sets):
    """Проверяет строку CSV-импорта метки против справочника. Возвращает список ошибок (пусто = ок).

    sets — множества активных значений справочника (см. load_dictionary_sets).
    """
    errors = []
    source = (row.get("utm_source") or "").strip()
    medium = (row.get("utm_medium") or "").strip()
    campaign = (row.get("utm_campaign") or "").strip()
    term = (row.get("utm_term") or "").strip()
    content = (row.get("utm_content") or "").strip()

    if not _source_ok(source, sets):
        errors.append(f"source '{source}' не из справочника")
    if medium not in sets.get("medium", set()):
        errors.append(f"medium '{medium}' не из справочника")

    parts = campaign.split("_")
    if len(parts) != 4:
        errors.append(f"campaign '{campaign}' должен быть тип_направление_воронка_имя")
    else:
        mark_type, direction, funnel, name = parts
        if mark_type not in sets.get("type", set()):
            errors.append(f"тип '{mark_type}' не из справочника")
        if direction not in sets.get("direction", set()):
            errors.append(f"направление '{direction}' не из справочника")
        if funnel.split("-")[0] not in sets.get("funnel", set()):
            errors.append(f"воронка '{funnel}' не из справочника")
        if not NAME_RE.match(name):
            errors.append(f"имя '{name}' — только латиница/цифры/дефис")

    if term and not NAME_RE.match(term):
        errors.append("term — только латиница/цифры/дефис")
    if content and not NAME_RE.match(content):
        errors.append("content — только латиница/цифры/дефис")
    return errors

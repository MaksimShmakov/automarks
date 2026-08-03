"""Толерантный парсер справочника UTM (Google Sheet «Справочник UTM v.2»).

Вкладки свёрстаны «для людей»: заголовок, описание, пустые строки, строки-примеры,
секции «Часть 1/2/3». Парсер читает вкладки 02 (medium), 03 (source), 04 (campaign)
и возвращает плоский список словарей вида:

    {"field", "value", "label", "group", "is_template", "is_active"}

Функции принимают уже прочитанный список строк (list[list[str]]), чтобы их можно было
юнит-тестировать без файлов и переиспользовать в авто-sync (Phase 3).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path


CAMPAIGN_SECTIONS = {
    "Часть 1": "type",
    "Часть 2": "direction",
    "Часть 3": "funnel",
    "Часть 4": None,  # имя — свободное, в справочник не тянем
}


def _cell(row, index):
    if index < len(row):
        return (row[index] or "").strip().lstrip("﻿")
    return ""


def read_csv(path) -> list[list[str]]:
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def parse_medium(rows) -> list[dict]:
    """Вкладка 02: header `medium,Что значит,Группа,...`, затем значения."""
    entries = []
    started = False
    for row in rows:
        c0 = _cell(row, 0)
        if not started:
            if c0 == "medium":
                started = True
            continue
        if not c0 or c0 == "__":
            continue
        entries.append({
            "field": "medium",
            "value": c0,
            "label": _cell(row, 1),
            "group": _cell(row, 2),
            "is_template": False,
            "is_active": True,
        })
    return entries


def parse_source(rows) -> list[dict]:
    """Вкладка 03: header `source,Группа,Что это,Активно,...`, затем значения (+ шаблоны <...>)."""
    entries = []
    started = False
    for row in rows:
        c0 = _cell(row, 0)
        if not started:
            if c0 == "source":
                started = True
            continue
        if not c0 or c0 == "__":
            continue
        active_raw = _cell(row, 3).lower()
        entries.append({
            "field": "source",
            "value": c0,
            "label": _cell(row, 2),   # «Что это»
            "group": _cell(row, 1),   # «Группа»
            "is_template": ("<" in c0 or ">" in c0),
            "is_active": active_raw != "нет",  # google_ads = «НЕТ» → неактивен
        })
    return entries


def parse_campaign(rows) -> list[dict]:
    """Вкладка 04: секции «Часть 1/2/3» → type/direction/funnel; «Часть 4» (имя) пропускаем."""
    entries = []
    field = None
    for row in rows:
        c0 = _cell(row, 0)

        section_hit = False
        for marker, mapped in CAMPAIGN_SECTIONS.items():
            if c0.startswith(marker):
                field = mapped
                section_hit = True
                break
        if section_hit:
            continue

        if field is None:
            continue
        if not c0 or c0 == "__" or c0 in {"значение", "формат"}:  # пропуск заголовков секций
            continue

        entries.append({
            "field": field,
            "value": c0,
            "label": _cell(row, 1),
            "group": "",
            "is_template": False,
            "is_active": True,
        })
    return entries


def parse_directory(directory) -> list[dict]:
    """Читает medium.csv / source.csv / campaign.csv из папки и возвращает все записи."""
    directory = Path(directory)
    entries = []
    entries += parse_medium(read_csv(directory / "medium.csv"))
    entries += parse_source(read_csv(directory / "source.csv"))
    entries += parse_campaign(read_csv(directory / "campaign.csv"))
    return entries


PARSERS = {
    "medium": parse_medium,
    "source": parse_source,
    "campaign": parse_campaign,
}


def fetch_csv_rows(url):
    """Скачивает CSV по URL и возвращает список строк. requests импортируется лениво."""
    import requests

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    return list(csv.reader(io.StringIO(response.text)))


def sync_entries(entries):
    """Upsert записей справочника + деактивация исчезнувших (по затронутым полям).

    Возвращает (created, updated, deactivated).
    """
    from django.utils import timezone

    from marks.models import UtmDictionaryEntry

    now = timezone.now()
    seen = set()
    created = updated = 0

    for entry in entries:
        seen.add((entry["field"], entry["value"]))
        _, was_created = UtmDictionaryEntry.objects.update_or_create(
            field=entry["field"],
            value=entry["value"],
            defaults={
                "label": entry["label"],
                "group": entry["group"],
                "is_template": entry["is_template"],
                "is_active": entry["is_active"],
                "synced_at": now,
            },
        )
        created += int(was_created)
        updated += int(not was_created)

    touched_fields = {field for field, _ in seen}
    deactivated = 0
    for obj in UtmDictionaryEntry.objects.filter(field__in=touched_fields, is_active=True):
        if (obj.field, obj.value) not in seen:
            obj.is_active = False
            obj.synced_at = now
            obj.save(update_fields=["is_active", "synced_at"])
            deactivated += 1

    return created, updated, deactivated

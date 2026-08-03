"""Импорт справочника UTM из локальных CSV-файлов в UtmDictionaryEntry.

    python manage.py import_utm_dictionary [--dir PATH]

Читает medium.csv / source.csv / campaign.csv (по умолчанию из marks/fixtures/utm_dictionary/),
делает upsert записей и деактивирует те, что исчезли из справочника.
В Phase 3 источником станут CSV-URL вкладок Google Sheet — парсер тот же.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from marks.services.utm_dictionary import parse_directory, sync_entries


DEFAULT_DIR = Path(settings.BASE_DIR) / "marks" / "fixtures" / "utm_dictionary"


class Command(BaseCommand):
    help = "Импортировать справочник UTM (medium/source/campaign) из локальных CSV в UtmDictionaryEntry"

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(DEFAULT_DIR), help="Папка с medium.csv/source.csv/campaign.csv")

    def handle(self, *args, **options):
        entries = parse_directory(Path(options["dir"]))
        created, updated, deactivated = sync_entries(entries)
        self.stdout.write(self.style.SUCCESS(
            f"Справочник UTM: +{created} новых, {updated} обновлено, {deactivated} деактивировано."
        ))

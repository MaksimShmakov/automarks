"""Авто-sync справочника UTM из Google Sheet (CSV-экспорт вкладок) в UtmDictionaryEntry.

    python manage.py sync_utm_dictionary

URL-адреса вкладок берутся из settings.UTM_DICTIONARY_CSV_URLS
(env UTM_DICTIONARY_MEDIUM_CSV_URL / _SOURCE_CSV_URL / _CAMPAIGN_CSV_URL).
Парсер — тот же, что у локального импорта. Предназначена для cron.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from marks.services.utm_dictionary import PARSERS, fetch_csv_rows, sync_entries


class Command(BaseCommand):
    help = "Синхронизировать справочник UTM из CSV-URL вкладок Google Sheet"

    def handle(self, *args, **options):
        urls = getattr(settings, "UTM_DICTIONARY_CSV_URLS", {}) or {}
        configured = {field: url for field, url in urls.items() if url}
        if not configured:
            raise CommandError(
                "Не заданы URL вкладок. Укажите UTM_DICTIONARY_MEDIUM_CSV_URL / "
                "_SOURCE_CSV_URL / _CAMPAIGN_CSV_URL в .env."
            )

        entries = []
        for field, url in configured.items():
            parser = PARSERS.get(field)
            if parser is None:
                continue
            rows = fetch_csv_rows(url)
            entries += parser(rows)

        created, updated, deactivated = sync_entries(entries)
        self.stdout.write(self.style.SUCCESS(
            f"Sync справочника UTM ({', '.join(sorted(configured))}): "
            f"+{created} новых, {updated} обновлено, {deactivated} деактивировано."
        ))

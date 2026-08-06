"""Повторная отправка неотправленных Telegram-уведомлений задачника (до победной, в пределах часа).

    python manage.py retry_notifications

Ставится в cron (каждые ~3 минуты). Берёт из очереди недоставленные уведомления не старше
часа, пробует отправить, помечает доставленные. Старше часа — сдаётся (в лог).
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from marks.models import OutboundNotification
from marks.services.telegram import _send_message


MAX_ATTEMPTS = 30
MAX_AGE = timedelta(hours=1)


class Command(BaseCommand):
    help = "Добить очередь Telegram-уведомлений (повтор до успеха, в пределах часа)"

    def handle(self, *args, **options):
        cutoff = timezone.now() - MAX_AGE
        pending = OutboundNotification.objects.filter(
            delivered=False, created_at__gte=cutoff, attempts__lt=MAX_ATTEMPTS
        )

        sent = failed = 0
        for note in pending:
            ok, error = _send_message(note.chat_id, note.text, attempts=1)
            note.attempts += 1
            if ok:
                note.delivered = True
                note.delivered_at = timezone.now()
                sent += 1
            else:
                note.last_error = (error or "")[:500]
                failed += 1
            note.save(update_fields=["delivered", "delivered_at", "attempts", "last_error"])

        stale = OutboundNotification.objects.filter(delivered=False, created_at__lt=cutoff).count()
        self.stdout.write(self.style.SUCCESS(
            f"Повтор уведомлений: доставлено {sent}, не удалось {failed}, просрочено(>1ч) {stale}"
        ))

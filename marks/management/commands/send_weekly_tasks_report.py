import io
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import openpyxl
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from openpyxl.styles import Alignment, Font

from marks.models import TaskRequest
from marks.services.telegram import send_weekly_tasks_report


def _report_window(base_date):
    # Friday is weekday 4 (Mon=0). We always take the latest Friday <= base_date.
    days_since_friday = (base_date.weekday() - 4) % 7
    friday = base_date - timedelta(days=days_since_friday)
    sunday = friday - timedelta(days=5)
    return sunday, friday


def _to_tz(dt_value, tz):
    if dt_value is None:
        return "-"
    return dt_value.astimezone(tz).strftime("%d.%m.%Y %H:%M")


def _build_workbook(tasks, report_tz):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Выполненные задачи"

    ws.append(
        [
            "ID",
            "Тип",
            "Статус",
            "Создал",
            "Создано",
            "Дедлайн",
            "Завершено",
            "Комментарий",
            "CJM/ТЗ",
            "Бот и ветки",
        ]
    )
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    count = 0
    for task in tasks:
        links = [value for value in [task.cjm_url, task.tz_url] if value]
        ws.append(
            [
                task.id,
                task.get_task_type_display(),
                task.get_status_display(),
                task.created_by.username if task.created_by else "-",
                _to_tz(task.created_at, report_tz),
                _to_tz(task.deadline, report_tz),
                _to_tz(task.completed_at, report_tz),
                task.comment or "",
                " | ".join(links),
                task.get_bot_branch_text(),
            ]
        )
        count += 1

    for column_cells in ws.columns:
        max_len = max(len(str(c.value or "")) for c in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(max_len + 2, 70)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue(), count


class Command(BaseCommand):
    help = "Send weekly completed tasks report (Sunday-Friday) to Telegram as XLSX."

    def add_arguments(self, parser):
        parser.add_argument(
            "--chat-id",
            dest="chat_id",
            default=getattr(settings, "WEEKLY_TASKS_REPORT_CHAT_ID", ""),
            help="Telegram chat_id or @username target.",
        )
        parser.add_argument(
            "--tz",
            dest="tz_name",
            default=getattr(settings, "WEEKLY_TASKS_REPORT_TZ", "Europe/Moscow"),
            help="IANA timezone for window calculation and datetime formatting (default: Europe/Moscow).",
        )
        parser.add_argument(
            "--base-date",
            dest="base_date",
            default="",
            help="Optional base date in YYYY-MM-DD. Latest Friday <= this date will be used.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Build report and print summary without sending to Telegram.",
        )

    def handle(self, *args, **options):
        chat_id = (options.get("chat_id") or "").strip()
        if not chat_id:
            raise CommandError("chat_id is required. Use --chat-id or WEEKLY_TASKS_REPORT_CHAT_ID.")

        tz_name = options.get("tz_name") or "Europe/Moscow"
        try:
            report_tz = ZoneInfo(tz_name)
        except Exception as exc:
            raise CommandError(f"Invalid timezone '{tz_name}': {exc}") from exc

        base_date_raw = (options.get("base_date") or "").strip()
        if base_date_raw:
            try:
                base_date = datetime.strptime(base_date_raw, "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("Invalid --base-date format. Use YYYY-MM-DD.") from exc
        else:
            base_date = datetime.now(report_tz).date()

        period_from, period_to = _report_window(base_date)
        dt_from_local = datetime.combine(period_from, time.min, tzinfo=report_tz)
        dt_to_local_exclusive = datetime.combine(period_to + timedelta(days=1), time.min, tzinfo=report_tz)

        tasks_qs = (
            TaskRequest.objects.select_related("created_by")
            .prefetch_related("branches__bot")
            .filter(
                status=TaskRequest.Status.DONE,
                completed_at__isnull=False,
                completed_at__gte=dt_from_local,
                completed_at__lt=dt_to_local_exclusive,
            )
            .order_by("-completed_at")
        )

        content, tasks_count = _build_workbook(tasks_qs, report_tz)
        filename = f"tasks_weekly_{period_from.isoformat()}_{period_to.isoformat()}.xlsx"
        caption = (
            f"Отчёт задачника за период {period_from.strftime('%d.%m.%Y')} - "
            f"{period_to.strftime('%d.%m.%Y')} (вс-пт).\n"
            f"Выполненных задач: {tasks_count}"
        )

        self.stdout.write(
            self.style.WARNING(
                f"Weekly window: {period_from.isoformat()}..{period_to.isoformat()}, tasks={tasks_count}"
            )
        )
        if options.get("dry_run"):
            self.stdout.write(self.style.SUCCESS("Dry-run: report built successfully, not sent."))
            return

        ok, error = send_weekly_tasks_report(
            chat_id=chat_id,
            filename=filename,
            content_bytes=content,
            caption=caption,
        )
        if not ok:
            raise CommandError(f"Failed to send weekly report: {error}")

        self.stdout.write(self.style.SUCCESS(f"Weekly report sent to {chat_id}."))

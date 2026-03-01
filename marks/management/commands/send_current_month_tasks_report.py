import io
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import openpyxl
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from openpyxl.styles import Alignment, Font

from marks.models import TaskRequest
from marks.services.telegram import send_weekly_tasks_report
from marks.services.task_legacy import get_task_feedback_map


def _month_to_date_window(base_date):
    month_start = base_date.replace(day=1)
    return month_start, base_date


def _to_tz(dt_value, tz):
    if dt_value is None:
        return "-"
    return dt_value.astimezone(tz).strftime("%d.%m.%Y %H:%M")


def _build_workbook(tasks, report_tz):
    tasks = list(tasks)
    feedback_map = get_task_feedback_map(task.id for task in tasks)

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
            "Фидбек",
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
                feedback_map.get(task.id, ""),
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
    help = "Send current month-to-date completed tasks report (1st day..today) to Telegram as XLSX."

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
            help="Optional base date in YYYY-MM-DD. Window will be first day of month..base-date.",
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

        period_from, period_to = _month_to_date_window(base_date)
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
        filename = f"tasks_month_current_{period_from.isoformat()}_{period_to.isoformat()}.xlsx"
        caption = (
            f"Отчёт задачника за текущий месяц {period_from.strftime('%d.%m.%Y')} - "
            f"{period_to.strftime('%d.%m.%Y')} (по текущую дату).\n"
            f"Выполненных задач: {tasks_count}"
        )

        self.stdout.write(
            self.style.WARNING(
                f"Current-month window: {period_from.isoformat()}..{period_to.isoformat()}, tasks={tasks_count}"
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
            raise CommandError(f"Failed to send current-month report: {error}")

        self.stdout.write(self.style.SUCCESS(f"Current-month report sent to {chat_id}."))


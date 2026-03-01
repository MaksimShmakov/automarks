import io
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from .models import Bot, Branch, Product, TaskRequest, UserProfile


class TaskBoardBaseTestCase(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user(username="admin", password="StrongPass123!")
        self.admin_user.profile.role = UserProfile.Role.ADMIN
        self.admin_user.profile.save(update_fields=["role"])

        self.manager_user = user_model.objects.create_user(username="manager", password="StrongPass123!")
        self.manager_user.profile.role = UserProfile.Role.MANAGER
        self.manager_user.profile.save(update_fields=["role"])

        self.product = Product.objects.create(name="Test product")
        self.bot = Bot.objects.create(name="test_bot_name", product=self.product)
        self.branch_main = Branch.objects.create(bot=self.bot, name="Main", code="MN")


class TaskBoardAccessTests(TaskBoardBaseTestCase):
    def test_admin_has_access_to_tasks_board(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("tasks_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Задачник")
        self.assertContains(response, "Выгрузить выполненные за период")

    def test_non_admin_has_access_but_no_kanban(self):
        self.client.force_login(self.manager_user)
        response = self.client.get(reverse("tasks_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Задачник")
        self.assertNotContains(response, "Непрочитанное")
        self.assertNotContains(response, "Выгрузить выполненные за период")


class TaskBoardActionsTests(TaskBoardBaseTestCase):
    @patch("marks.views.notify_new_task")
    def test_create_patch_task(self, notify_mock):
        self.client.force_login(self.admin_user)
        deadline = timezone.now() + timedelta(days=3)
        response = self.client.post(
            reverse("create_patch_task"),
            {
                "patch-branches": [self.branch_main.id],
                "patch-cjm_url": "https://example.com/cjm",
                "patch-comment": "Комментарий",
                "patch-deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("tasks_board"))

        task = TaskRequest.objects.get()
        self.assertEqual(task.task_type, TaskRequest.Type.PATCH)
        self.assertEqual(task.status, TaskRequest.Status.UNREAD)
        self.assertEqual(task.created_by, self.admin_user)
        self.assertEqual(list(task.branches.values_list("id", flat=True)), [self.branch_main.id])
        notify_mock.assert_called_once_with(task)

    @patch("marks.views.notify_new_task")
    def test_create_build_task_sets_formatted_build_name(self, notify_mock):
        self.client.force_login(self.admin_user)
        deadline = timezone.now() + timedelta(days=2)
        response = self.client.post(
            reverse("create_build_task"),
            {
                "build-branches": [self.branch_main.id],
                "build-build_token": "1234567890",
                "build-cjm_url": "https://example.com/cjm-build",
                "build-comment": "Build comment",
                "build-deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("tasks_board"))

        task = TaskRequest.objects.get(task_type=TaskRequest.Type.BUILD)
        self.assertEqual(task.build_name, "test_bot_name")
        self.assertEqual(task.get_scope_units(), 1)
        notify_mock.assert_called_once_with(task)

    @patch("marks.views.notify_new_task")
    def test_create_mailing_task_accepts_local_deadline_format(self, notify_mock):
        self.client.force_login(self.admin_user)
        deadline = timezone.now() + timedelta(days=2)
        response = self.client.post(
            reverse("create_mailing_task"),
            {
                "mailing-branches": [self.branch_main.id],
                "mailing-tz_url": "https://example.com/tz",
                "mailing-comment": "Mailing comment",
                "mailing-deadline": deadline.strftime("%d.%m.%Y %H:%M"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("tasks_board"))

        task = TaskRequest.objects.get(task_type=TaskRequest.Type.MAILING)
        self.assertEqual(task.status, TaskRequest.Status.UNREAD)
        self.assertEqual(task.created_by, self.admin_user)
        self.assertEqual(task.tz_url, "https://example.com/tz")
        self.assertEqual(list(task.branches.values_list("id", flat=True)), [self.branch_main.id])
        notify_mock.assert_called_once_with(task)

    @patch("marks.views.notify_new_task")
    def test_create_task_with_notify_requires_tg_username(self, notify_mock):
        self.client.force_login(self.admin_user)
        deadline = timezone.now() + timedelta(days=2)
        response = self.client.post(
            reverse("create_patch_task"),
            {
                "patch-branches": [self.branch_main.id],
                "patch-cjm_url": "https://example.com/cjm",
                "patch-comment": "Комментарий",
                "patch-deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
                "patch-notify_me": "on",
                "patch-tg_username": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Укажите username в Telegram или chat_id.")
        self.assertFalse(TaskRequest.objects.filter(task_type=TaskRequest.Type.PATCH).exists())
        notify_mock.assert_not_called()

    @patch("marks.views.notify_status_change")
    def test_status_done_sets_completed_at_and_sends_notification(self, notify_mock):
        task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.BUILD,
            build_name="bot + branches",
            build_token="1234567890",
            cjm_url="https://example.com/cjm",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
        )
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("update_task_status", kwargs={"task_id": task.id}),
            {"status": TaskRequest.Status.DONE},
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("tasks_board"))
        task.refresh_from_db()
        self.assertEqual(task.status, TaskRequest.Status.DONE)
        self.assertIsNotNone(task.completed_at)

        notify_mock.assert_called_once()
        kwargs = notify_mock.call_args.kwargs
        self.assertEqual(kwargs["task"], task)
        self.assertEqual(kwargs["old_status"], TaskRequest.Status.UNREAD)
        self.assertEqual(kwargs["changed_by"], self.admin_user)

    @patch("marks.views.notify_done_to_user")
    @patch("marks.views.get_task_tg_username", return_value="test_user")
    @patch("marks.views.notify_status_change")
    def test_status_done_sends_personal_notification_when_username_exists(
        self,
        status_notify_mock,
        legacy_username_mock,
        user_notify_mock,
    ):
        task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.MAILING,
            tz_url="https://example.com/tz",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
        )
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("update_task_status", kwargs={"task_id": task.id}),
            {"status": TaskRequest.Status.DONE},
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("tasks_board"))
        task.refresh_from_db()
        self.assertEqual(task.status, TaskRequest.Status.DONE)

        status_notify_mock.assert_called_once()
        legacy_username_mock.assert_called_once_with(task.id)
        user_notify_mock.assert_called_once_with(task=task, tg_username="test_user")

    @override_settings(TELEGRAM_WEBHOOK_SECRET="secret-key")
    @patch("marks.views.set_task_feedback_comment")
    def test_telegram_webhook_saves_feedback_from_reply(self, set_feedback_mock):
        task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.PATCH,
            cjm_url="https://example.com/cjm",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        payload = {
            "update_id": 1,
            "message": {
                "message_id": 101,
                "text": "Все ок, спасибо!",
                "reply_to_message": {
                    "message_id": 100,
                    "text": f"ID задачи: #{task.id}\nЗадача выполнена",
                },
            },
        }

        response = self.client.post(
            reverse("telegram_webhook", kwargs={"webhook_key": "secret-key"}),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        set_feedback_mock.assert_called_once_with(task_id=task.id, feedback_comment="Все ок, спасибо!")

    @override_settings(TELEGRAM_WEBHOOK_SECRET="secret-key")
    @patch("marks.views.send_text_message")
    @patch("marks.views.send_weekly_tasks_report", return_value=(True, ""))
    def test_telegram_webhook_week_command_sends_report(self, send_report_mock, send_text_mock):
        task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.PATCH,
            cjm_url="https://example.com/cjm",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        task.completed_at = timezone.now()
        task.save(update_fields=["completed_at"])

        payload = {
            "update_id": 2,
            "message": {
                "message_id": 102,
                "text": "/week",
                "chat": {"id": 439144407},
            },
        }
        response = self.client.post(
            reverse("telegram_webhook", kwargs={"webhook_key": "secret-key"}),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        send_report_mock.assert_called_once()
        kwargs = send_report_mock.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], "439144407")
        self.assertIn("tasks_week_current_", kwargs["filename"])
        self.assertIn("текущую неделю", kwargs["caption"])
        send_text_mock.assert_not_called()

    @override_settings(TELEGRAM_WEBHOOK_SECRET="secret-key")
    @patch("marks.views.send_text_message")
    @patch("marks.views.send_weekly_tasks_report", return_value=(True, ""))
    def test_telegram_webhook_month_command_rejects_bad_date(self, send_report_mock, send_text_mock):
        payload = {
            "update_id": 3,
            "message": {
                "message_id": 103,
                "text": "/month 15-02-2026",
                "chat": {"id": 439144407},
            },
        }
        response = self.client.post(
            reverse("telegram_webhook", kwargs={"webhook_key": "secret-key"}),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        send_report_mock.assert_not_called()
        send_text_mock.assert_called_once()

    def test_tasks_board_filters_by_status(self):
        done_task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.BUILD,
            build_name="done task",
            build_token="token",
            cjm_url="https://example.com/cjm",
            deadline=timezone.now() + timedelta(days=2),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        unread_task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.BUILD,
            build_name="unread task",
            build_token="token2",
            cjm_url="https://example.com/cjm2",
            deadline=timezone.now() + timedelta(days=2),
            created_by=self.admin_user,
            status=TaskRequest.Status.UNREAD,
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(
            reverse("tasks_board"),
            {"task_status": TaskRequest.Status.DONE},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"#{done_task.id}")
        self.assertNotContains(response, f"#{unread_task.id}")

    def test_completed_counters_use_branch_units(self):
        second_branch = Branch.objects.create(bot=self.bot, name="Dev", code="DV")
        third_branch = Branch.objects.create(bot=self.bot, name="Feature", code="FT")

        mailing_task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.MAILING,
            tz_url="https://example.com/tz",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        mailing_task.branches.set([self.branch_main, second_branch])

        build_task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.BUILD,
            build_token="build-token",
            cjm_url="https://example.com/cjm",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        build_task.branches.set([self.branch_main, second_branch, third_branch])

        patch_task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.PATCH,
            cjm_url="https://example.com/cjm-patch",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        patch_task.branches.set([self.branch_main])

        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("tasks_board"))

        self.assertEqual(response.status_code, 200)
        counters = response.context["completed_type_counters"]
        self.assertEqual(counters["mailing"], 2)
        self.assertEqual(counters["build"], 3)
        self.assertEqual(counters["patch"], 1)

    def test_export_completed_tasks_by_period(self):
        recent_task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.BUILD,
            build_name="recent",
            build_token="token",
            cjm_url="https://example.com/cjm",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        old_task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.BUILD,
            build_name="old",
            build_token="token",
            cjm_url="https://example.com/cjm",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )

        recent_task.completed_at = timezone.now() - timedelta(days=1)
        recent_task.save(update_fields=["completed_at"])
        old_task.completed_at = timezone.now() - timedelta(days=30)
        old_task.save(update_fields=["completed_at"])

        self.client.force_login(self.admin_user)
        date_from = (timezone.localdate() - timedelta(days=3)).isoformat()
        date_to = timezone.localdate().isoformat()
        response = self.client.get(
            reverse("export_completed_tasks"),
            {"completed_from": date_from, "completed_to": date_to},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", response["Content-Type"])

        workbook = load_workbook(io.BytesIO(response.content))
        sheet = workbook.active
        rows = list(sheet.iter_rows(min_row=2, values_only=True))
        task_ids = [row[0] for row in rows]
        self.assertIn(recent_task.id, task_ids)
        self.assertNotIn(old_task.id, task_ids)

    def test_export_has_combined_link_column_and_bot_branch_column(self):
        task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.MAILING,
            tz_url="https://example.com/tz",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        task.branches.set([self.branch_main])
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("export_completed_tasks"))
        workbook = load_workbook(io.BytesIO(response.content))
        sheet = workbook.active
        headers = [cell.value for cell in sheet[1]]

        self.assertNotIn("Ветки", headers)
        self.assertIn("CJM/ТЗ", headers)
        self.assertIn("Бот и ветки", headers)
        self.assertIn("Фидбек", headers)

        first_data_row = [cell.value for cell in sheet[2]]
        self.assertIn("https://example.com/tz", first_data_row)
        self.assertIn("test_bot_name", first_data_row)

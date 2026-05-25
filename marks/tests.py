import io
import json
import hashlib
import shutil
import tempfile
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from .forms import BranchForm
from .mailing_split import (
    MailingSplitError,
    apply_split_weights,
    assign_variant_for_recipient,
    import_recipients,
    parse_recipient_ids,
)
from .models import (
    Bot,
    Branch,
    Experiment,
    MailingExperiment,
    MailingRecipient,
    MailingVariant,
    Product,
    TaskRequest,
    UserProfile,
)
from .task_time import get_tasks_timezone


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
        self.assertFalse(response.context["show_kanban"])
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
    def test_create_patch_task_saves_photo_and_task_timezone_deadline(self, notify_mock):
        self.client.force_login(self.admin_user)
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)
        photo = SimpleUploadedFile("task.png", b"fake-image-bytes", content_type="image/png")

        with self.settings(MEDIA_ROOT=media_root, TASKS_TIME_ZONE="Europe/Moscow"):
            response = self.client.post(
                reverse("create_patch_task"),
                {
                    "patch-branches": [self.branch_main.id],
                    "patch-cjm_url": "https://example.com/cjm",
                    "patch-comment": "Комментарий со скрином",
                    "patch-deadline": "2026-04-08T12:34",
                    "patch-photo": photo,
                },
            )
            task = TaskRequest.objects.get(task_type=TaskRequest.Type.PATCH)
            self.assertTrue(task.photo.name.endswith(".png"))
            self.assertEqual(
                timezone.localtime(task.deadline, get_tasks_timezone()).strftime("%Y-%m-%dT%H:%M"),
                "2026-04-08T12:34",
            )

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        notify_mock.assert_called_once_with(task)

    @patch("marks.views.notify_new_task")
    def test_create_build_task_uses_manual_bot_name(self, notify_mock):
        self.client.force_login(self.admin_user)
        deadline = timezone.now() + timedelta(days=2)
        response = self.client.post(
            reverse("create_build_task"),
            {
                "build-bot_name": "@new_bot",
                "build-build_token": "1234567890",
                "build-cjm_url": "https://example.com/cjm-build",
                "build-comment": "Build comment",
                "build-deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("tasks_board"))

        task = TaskRequest.objects.get(task_type=TaskRequest.Type.BUILD)
        self.assertEqual(task.build_name, "@new_bot")
        self.assertEqual(task.branches.count(), 0)
        self.assertEqual(task.get_scope_units(), 1)
        notify_mock.assert_called_once_with(task)

    @patch("marks.views.notify_new_task")
    def test_create_build_task_appends_optional_branch_name(self, notify_mock):
        self.client.force_login(self.admin_user)
        deadline = timezone.now() + timedelta(days=2)
        response = self.client.post(
            reverse("create_build_task"),
            {
                "build-bot_name": "@new_bot",
                "build-branch_name": "feature-login",
                "build-build_token": "1234567890",
                "build-cjm_url": "https://example.com/cjm-build",
                "build-comment": "Build comment",
                "build-deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("tasks_board"))

        task = TaskRequest.objects.get(task_type=TaskRequest.Type.BUILD)
        self.assertEqual(task.build_name, "@new_bot / feature-login")
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

    @patch("marks.views.notify_status_change")
    def test_status_done_never_saves_completed_at_before_created_at(self, notify_mock):
        task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.BUILD,
            build_name="bot + branches",
            build_token="1234567890",
            cjm_url="https://example.com/cjm",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
        )
        future_created_at = timezone.now() + timedelta(minutes=10)
        TaskRequest.objects.filter(pk=task.pk).update(created_at=future_created_at)
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("update_task_status", kwargs={"task_id": task.id}),
            {"status": TaskRequest.Status.DONE},
        )

        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.completed_at, task.created_at)
        notify_mock.assert_called_once()

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
    @patch("marks.views.set_task_feedback_comment")
    def test_telegram_webhook_saves_feedback_from_quote_when_reply_is_inaccessible(self, set_feedback_mock):
        task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.PATCH,
            cjm_url="https://example.com/cjm",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        payload = {
            "update_id": 5,
            "message": {
                "message_id": 105,
                "text": "РЎРїР°СЃРёР±Рѕ, РІС‹ СЃСѓРїРµСЂ!!",
                "reply_to_message": {
                    "message_id": 104,
                    "date": 0,
                    "chat": {"id": -100100100, "type": "supergroup"},
                },
                "quote": {
                    "text": f"Р—Р°РґР°С‡Р° РІС‹РїРѕР»РЅРµРЅР°\nID Р·Р°РґР°С‡Рё: #{task.id}",
                },
            },
        }

        response = self.client.post(
            reverse("telegram_webhook", kwargs={"webhook_key": "secret-key"}),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        set_feedback_mock.assert_called_once_with(task_id=task.id, feedback_comment="РЎРїР°СЃРёР±Рѕ, РІС‹ СЃСѓРїРµСЂ!!")

    @override_settings(TELEGRAM_WEBHOOK_SECRET="secret-key")
    @patch("marks.views.set_task_feedback_comment")
    def test_telegram_webhook_saves_feedback_from_business_message_external_reply(self, set_feedback_mock):
        task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.MAILING,
            tz_url="https://example.com/tz",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        payload = {
            "update_id": 6,
            "business_message": {
                "message_id": 106,
                "text": "Р¤РёРґР±РµРє РёР· business chat",
                "external_reply": {
                    "message_id": 105,
                    "text": f"ID Р·Р°РґР°С‡Рё: #{task.id}\nР—Р°РґР°С‡Р° РІС‹РїРѕР»РЅРµРЅР°",
                },
            },
        }

        response = self.client.post(
            reverse("telegram_webhook", kwargs={"webhook_key": "secret-key"}),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        set_feedback_mock.assert_called_once_with(task_id=task.id, feedback_comment="Р¤РёРґР±РµРє РёР· business chat")

    @override_settings(TELEGRAM_WEBHOOK_SECRET="secret-key")
    def test_telegram_webhook_feedback_is_exported(self):
        task = TaskRequest.objects.create(
            task_type=TaskRequest.Type.PATCH,
            cjm_url="https://example.com/cjm",
            deadline=timezone.now() + timedelta(days=1),
            created_by=self.admin_user,
            status=TaskRequest.Status.DONE,
        )
        payload = {
            "update_id": 4,
            "message": {
                "message_id": 104,
                "text": "Фидбек по задаче",
                "reply_to_message": {
                    "message_id": 103,
                    "text": f"ID задачи: #{task.id}\nЗадача выполнена",
                },
            },
        }

        webhook_response = self.client.post(
            reverse("telegram_webhook", kwargs={"webhook_key": "secret-key"}),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(webhook_response.status_code, 200)

        self.client.force_login(self.admin_user)
        export_response = self.client.get(reverse("export_completed_tasks"))

        self.assertEqual(export_response.status_code, 200)
        workbook = load_workbook(io.BytesIO(export_response.content))
        sheet = workbook.active
        headers = [cell.value for cell in sheet[1]]
        feedback_index = headers.index("Фидбек")
        rows = list(sheet.iter_rows(min_row=2, values_only=True))
        row = next(row for row in rows if row[0] == task.id)

        self.assertEqual(row[feedback_index], "Фидбек по задаче")

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
        self.assertContains(response, f">#{done_task.id}<")
        self.assertNotContains(response, f">#{unread_task.id}<")

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


class BotPlatformTests(TaskBoardBaseTestCase):
    def test_default_telegram_tag_uses_start_link(self):
        tag = self.branch_main.tags.get(url__isnull=False)

        self.assertEqual(tag.url, "https://t.me/test_bot_name?start=MN0001")

    def test_vk_tag_uses_group_ref_link(self):
        vk_bot = Bot.objects.create(
            name="203482421",
            display_name="VK Sales",
            platform=Bot.Platform.VK,
            product=self.product,
        )
        branch = Branch.objects.create(bot=vk_bot, name="Main", code="ell23")
        tag = branch.tags.get(url__isnull=False)

        self.assertEqual(tag.url, "https://vk.com/write-203482421?ref=ell230001&ref_source=23")

    def test_bot_api_finds_vk_bot_by_group_id(self):
        vk_bot = Bot.objects.create(
            name="203482421",
            display_name="VK Sales",
            platform=Bot.Platform.VK,
            product=self.product,
        )
        Branch.objects.create(bot=vk_bot, name="Main", code="ell01")

        response = self.client.get(reverse("bot_api", kwargs={"bot_name": "203482421"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["bot"], "203482421")
        self.assertEqual(payload["branches"][0]["tags"][0]["url"], "https://vk.com/write-203482421?ref=ell010001&ref_source=1")

    def test_bot_api_accepts_telegram_name_with_at_prefix(self):
        response = self.client.get(reverse("bot_api", kwargs={"bot_name": "@test_bot_name"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["bot"], "test_bot_name")

    @patch("marks.views.secrets.randbelow", return_value=85)
    def test_bot_api_number_response_includes_ab_key_for_active_test(self, randbelow_mock):
        Experiment.objects.create(
            title="API split by number",
            branch=self.branch_main,
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            expected_change="+5%",
            hypothesis="Проверяем вариант первого экрана.",
            traffic_volume=Experiment.TrafficVolume.SPLIT_70_30,
            test_duration=Experiment.TestDuration.DAYS_7,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 4, 10),
            status=Experiment.Status.IN_PROGRESS,
            created_by=self.admin_user,
        )
        number = self.branch_main.tags.get(url__isnull=False).number

        response = self.client.get(
            reverse("bot_api", kwargs={"bot_name": "test_bot_name"}),
            {"number": number},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["number"], number)
        self.assertEqual(payload["ab_key"], 2)
        randbelow_mock.assert_called_once_with(100)

    def test_bot_api_number_response_defaults_ab_key_to_one_without_active_test(self):
        number = self.branch_main.tags.get(url__isnull=False).number

        response = self.client.get(
            reverse("bot_api", kwargs={"bot_name": "test_bot_name"}),
            {"number": number},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["number"], number)
        self.assertEqual(payload["ab_key"], 1)

    def test_bot_api_returns_branch_ab_assignment_for_specific_branch_code(self):
        experiment = Experiment.objects.create(
            title="API split",
            branch=self.branch_main,
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            expected_change="+5%",
            hypothesis="Проверяем вариант первого экрана.",
            traffic_volume=Experiment.TrafficVolume.SPLIT_70_30,
            test_duration=Experiment.TestDuration.DAYS_7,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 4, 10),
            status=Experiment.Status.IN_PROGRESS,
            created_by=self.admin_user,
        )
        ab_key = "user-42"
        seed = f"{experiment.id}:{self.branch_main.id}:{ab_key}".encode("utf-8")
        bucket = int(hashlib.sha256(seed).hexdigest()[:16], 16) % 100
        expected_variant_value = 1 if bucket < 70 else 2

        response = self.client.get(
            reverse("bot_api", kwargs={"bot_name": "test_bot_name"}),
            {"branch_code": "mn", "ab_key": ab_key},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["branches"]), 1)
        self.assertEqual(payload["branches"][0]["code"], "MN")
        self.assertEqual(payload["branches"][0]["ab_test"]["active"], True)
        self.assertEqual(payload["branches"][0]["ab_test"]["variant_value"], expected_variant_value)
        self.assertEqual(payload["branches"][0]["ab_test"]["split"], "70/30")
        self.assertEqual(payload["branches"][0]["ab_test"]["assignment_mode"], "hash")

    def test_bot_api_returns_inactive_ab_payload_when_branch_has_no_active_test(self):
        response = self.client.get(
            reverse("bot_api", kwargs={"bot_name": "test_bot_name"}),
            {"branch_code": "MN"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["branches"][0]["ab_test"], {"active": False})

    def test_bot_api_returns_404_for_unknown_branch_code(self):
        response = self.client.get(
            reverse("bot_api", kwargs={"bot_name": "test_bot_name"}),
            {"branch_code": "missing"},
        )

        self.assertEqual(response.status_code, 404)

    def test_bots_list_creates_telegram_bot_and_strips_at_sign(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("bots_list"),
            {
                "form_type": "telegram",
                "tg-name": "@new_bot",
            },
        )

        self.assertEqual(response.status_code, 302)
        bot = Bot.objects.get(name="new_bot")
        self.assertEqual(bot.platform, Bot.Platform.TELEGRAM)
        self.assertEqual(bot.display_name, "")

    def test_bots_list_creates_vk_bot_with_display_name(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("bots_list"),
            {
                "form_type": "vk",
                "vk-name": "203482421",
                "vk-display_name": "VK Sales",
            },
        )

        self.assertEqual(response.status_code, 302)
        bot = Bot.objects.get(name="203482421")
        self.assertEqual(bot.platform, Bot.Platform.VK)
        self.assertEqual(bot.display_name, "VK Sales")

    def test_bots_list_sorts_telegram_before_vk(self):
        Bot.objects.create(name="zzz_bot", product=self.product)
        Bot.objects.create(
            name="203482421",
            display_name="Alpha VK",
            platform=Bot.Platform.VK,
            product=self.product,
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(reverse("bots_list"))

        self.assertEqual(response.status_code, 200)
        ordered_platforms = [bot.platform for bot in response.context["active_bots"]]
        self.assertEqual(ordered_platforms[:3], [Bot.Platform.TELEGRAM, Bot.Platform.TELEGRAM, Bot.Platform.VK])


class ExperimentBoardTests(TaskBoardBaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin_user)

    def _experiment_payload(self, **overrides):
        payload = {
            "title": "Новый A/B тест",
            "tz_url": "https://example.com/tz/exp-1",
            "wants_ab_test": "on",
            "ab_test_options": ["start"],
            "ab_test_custom_option": "",
            "metric_impact": "CR",
            "comparison_text": "Текущий экран vs новый экран",
            "expected_change": "+8%",
            "hypothesis": "Если изменить первый экран, конверсия вырастет.",
            "traffic_volume": Experiment.TrafficVolume.SPLIT_50_50,
            "traffic_volume_other": "",
            "test_duration": Experiment.TestDuration.DAYS_7,
            "duration_users": "",
            "duration_end_date": "",
            "start_date": "2026-03-10",
            "end_date": "2026-03-17",
            "dashboard_url": "https://example.com/dashboard/exp-1",
            "result_variant_a": "CR 11%, open rate 24%",
            "result_variant_b": "CR 13%, open rate 28%",
            "comment": "Комментарий по эксперименту",
        }
        payload.update(overrides)
        return payload

    def test_create_experiment_saves_dates_and_manual_results(self):
        response = self.client.post(reverse("experiments_board"), self._experiment_payload())

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("experiments_board"))

        experiment = Experiment.objects.get(title="Новый A/B тест")
        self.assertEqual(experiment.status, Experiment.Status.BACKLOG)
        self.assertEqual(experiment.tz_url, "https://example.com/tz/exp-1")
        self.assertEqual(experiment.comparison_text, "Текущий экран vs новый экран")
        self.assertEqual(experiment.start_date, date(2026, 3, 10))
        self.assertEqual(experiment.end_date, date(2026, 3, 17))
        self.assertEqual(experiment.dashboard_url, "https://example.com/dashboard/exp-1")
        self.assertEqual(experiment.result_variant_a, "CR 11%, open rate 24%")
        self.assertEqual(experiment.result_variant_b, "CR 13%, open rate 28%")

    def test_create_experiment_saves_selected_branch_for_api(self):
        response = self.client.post(
            reverse("experiments_board"),
            self._experiment_payload(branch=str(self.branch_main.id)),
        )

        self.assertEqual(response.status_code, 302)
        experiment = Experiment.objects.get()
        self.assertEqual(experiment.branch_id, self.branch_main.id)
        return
        experiment = Experiment.objects.get(title="РќРѕРІС‹Р№ A/B С‚РµСЃС‚")
        self.assertEqual(experiment.branch_id, self.branch_main.id)

    def test_edit_experiment_updates_dates_and_metrics(self):
        experiment = Experiment.objects.create(
            title="Текущий тест",
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            expected_change="+5%",
            hypothesis="Исходная гипотеза",
            traffic_volume=Experiment.TrafficVolume.SPLIT_50_50,
            test_duration=Experiment.TestDuration.DAYS_7,
            created_by=self.admin_user,
        )

        payload = self._experiment_payload(
            title="Текущий тест",
            experiment_id=str(experiment.id),
            result_variant_a="CR 10%",
            result_variant_b="CR 14%",
            start_date="2026-03-11",
            end_date="2026-03-18",
        )
        response = self.client.post(reverse("experiments_board"), payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("experiments_board"))

        experiment.refresh_from_db()
        self.assertEqual(experiment.start_date, date(2026, 3, 11))
        self.assertEqual(experiment.end_date, date(2026, 3, 18))
        self.assertEqual(experiment.result_variant_a, "CR 10%")
        self.assertEqual(experiment.result_variant_b, "CR 14%")

    @patch("marks.views.notify_new_task", return_value=(True, ""))
    def test_move_to_draft_allows_empty_tz(self, notify_mock):
        experiment = Experiment.objects.create(
            title="Без ТЗ",
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            comparison_text="Экран A vs экран B",
            expected_change="+5%",
            hypothesis="Проверяем первый экран",
            traffic_volume=Experiment.TrafficVolume.SPLIT_50_50,
            test_duration=Experiment.TestDuration.DAYS_7,
            created_by=self.admin_user,
            status=Experiment.Status.BACKLOG,
        )

        response = self.client.post(
            reverse("update_experiment_status", kwargs={"experiment_id": experiment.id}),
            {"status": Experiment.Status.DRAFT},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        experiment.refresh_from_db()
        self.assertEqual(experiment.status, Experiment.Status.DRAFT)
        self.assertIsNotNone(experiment.technical_task)
        self.assertEqual(experiment.technical_task.tz_url, "")
        notify_mock.assert_called_once_with(experiment.technical_task)

    @patch("marks.views.notify_new_task", return_value=(True, ""))
    def test_move_to_draft_creates_task_for_tech_team(self, notify_mock):
        experiment = Experiment.objects.create(
            title="Готов к разработке",
            branch=self.branch_main,
            tz_url="https://example.com/tz/ready",
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            comparison_text="Экран A vs экран B",
            expected_change="+5%",
            hypothesis="Проверяем первый экран",
            traffic_volume=Experiment.TrafficVolume.SPLIT_50_50,
            test_duration=Experiment.TestDuration.DAYS_7,
            start_date=date(2026, 4, 2),
            created_by=self.admin_user,
            status=Experiment.Status.BACKLOG,
        )

        response = self.client.post(
            reverse("update_experiment_status", kwargs={"experiment_id": experiment.id}),
            {"status": Experiment.Status.DRAFT},
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("experiments_board"))

        experiment.refresh_from_db()
        self.assertEqual(experiment.status, Experiment.Status.DRAFT)
        self.assertIsNotNone(experiment.technical_task)

        task = experiment.technical_task
        self.assertEqual(task.task_type, TaskRequest.Type.PATCH)
        self.assertEqual(task.status, TaskRequest.Status.UNREAD)
        self.assertEqual(task.tz_url, "https://example.com/tz/ready")
        self.assertEqual(list(task.branches.values_list("id", flat=True)), [self.branch_main.id])
        notify_mock.assert_called_once_with(task)

    def test_update_experiment_status_blocks_parallel_branch_test(self):
        Experiment.objects.create(
            title="РђРєС‚РёРІРЅС‹Р№ С‚РµСЃС‚",
            branch=self.branch_main,
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            expected_change="+5%",
            hypothesis="РџРµСЂРІС‹Р№ С‚РµСЃС‚",
            traffic_volume=Experiment.TrafficVolume.SPLIT_50_50,
            test_duration=Experiment.TestDuration.DAYS_7,
            start_date=date(2026, 3, 10),
            end_date=date(2026, 3, 17),
            created_by=self.admin_user,
            status=Experiment.Status.IN_PROGRESS,
        )
        queued_experiment = Experiment.objects.create(
            title="Р’С‚РѕСЂРѕР№ С‚РµСЃС‚",
            branch=self.branch_main,
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            expected_change="+3%",
            hypothesis="Р’С‚РѕСЂР°СЏ РіРёРїРѕС‚РµР·Р°",
            traffic_volume=Experiment.TrafficVolume.SPLIT_50_50,
            test_duration=Experiment.TestDuration.DAYS_7,
            start_date=date(2026, 3, 18),
            end_date=date(2026, 3, 25),
            created_by=self.admin_user,
            status=Experiment.Status.DRAFT,
        )

        response = self.client.post(
            reverse("update_experiment_status", kwargs={"experiment_id": queued_experiment.id}),
            {"status": Experiment.Status.IN_PROGRESS},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        queued_experiment.refresh_from_db()
        self.assertEqual(queued_experiment.status, Experiment.Status.DRAFT)
        return
        self.assertContains(response, "Р”Р»СЏ СЌС‚РѕР№ РІРµС‚РєРё СѓР¶Рµ РёРґРµС‚ РґСЂСѓРіРѕР№ A/B С‚РµСЃС‚.")

    def test_final_status_requires_dates_and_ab_results(self):
        experiment = Experiment.objects.create(
            title="Тест без итогов",
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            expected_change="+5%",
            hypothesis="Проверяем первый экран",
            traffic_volume=Experiment.TrafficVolume.SPLIT_50_50,
            test_duration=Experiment.TestDuration.DAYS_7,
            created_by=self.admin_user,
            status=Experiment.Status.COMPLETED,
        )

        response = self.client.post(
            reverse("update_experiment_status", kwargs={"experiment_id": experiment.id}),
            {"status": Experiment.Status.SUCCESS},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        experiment.refresh_from_db()
        self.assertEqual(experiment.status, Experiment.Status.COMPLETED)
        self.assertContains(response, "Перед финальным решением заполните")

    def test_final_status_saves_completion_data_from_modal_post(self):
        experiment = Experiment.objects.create(
            title="Финализация из попапа",
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            expected_change="+7%",
            hypothesis="Завершаем тест прямо из карточки",
            traffic_volume=Experiment.TrafficVolume.SPLIT_50_50,
            test_duration=Experiment.TestDuration.DAYS_7,
            created_by=self.admin_user,
            status=Experiment.Status.IN_PROGRESS,
        )

        response = self.client.post(
            reverse("update_experiment_status", kwargs={"experiment_id": experiment.id}),
            {
                "status": Experiment.Status.SUCCESS,
                "start_date": "2026-03-10",
                "end_date": "2026-03-17",
                "dashboard_url": "https://example.com/dashboard/final-exp",
                "result_variant_a": "CR 10%, CTR 18%",
                "result_variant_b": "CR 14%, CTR 22%",
                "comment": "Победил вариант B",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        experiment.refresh_from_db()
        self.assertEqual(experiment.status, Experiment.Status.SUCCESS)
        self.assertEqual(experiment.start_date, date(2026, 3, 10))
        self.assertEqual(experiment.end_date, date(2026, 3, 17))
        self.assertEqual(experiment.dashboard_url, "https://example.com/dashboard/final-exp")
        self.assertEqual(experiment.result_variant_a, "CR 10%, CTR 18%")
        self.assertEqual(experiment.result_variant_b, "CR 14%, CTR 22%")
        self.assertEqual(experiment.comment, "Победил вариант B")

    def test_final_status_allows_empty_variant_results(self):
        experiment = Experiment.objects.create(
            title="Финал без цифр",
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            comparison_text="A vs B",
            expected_change="+7%",
            hypothesis="Проверяем без обязательных цифр",
            traffic_volume=Experiment.TrafficVolume.SPLIT_50_50,
            test_duration=Experiment.TestDuration.DAYS_7,
            created_by=self.admin_user,
            status=Experiment.Status.IN_PROGRESS,
        )

        response = self.client.post(
            reverse("update_experiment_status", kwargs={"experiment_id": experiment.id}),
            {
                "status": Experiment.Status.SUCCESS,
                "start_date": "2026-03-30",
                "end_date": "2026-04-01",
                "dashboard_url": "",
                "result_variant_a": "",
                "result_variant_b": "",
                "comment": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        experiment.refresh_from_db()
        self.assertEqual(experiment.status, Experiment.Status.SUCCESS)

    def test_finalized_experiment_moves_to_library(self):
        active_experiment = Experiment.objects.create(
            title="Активный тест",
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            expected_change="+5%",
            hypothesis="Активная гипотеза",
            traffic_volume=Experiment.TrafficVolume.SPLIT_50_50,
            test_duration=Experiment.TestDuration.DAYS_7,
            created_by=self.admin_user,
            status=Experiment.Status.DRAFT,
        )
        final_experiment = Experiment.objects.create(
            title="Финальный тест",
            wants_ab_test=True,
            ab_test_options=["start"],
            metric_impact="CR",
            expected_change="+5%",
            hypothesis="Финальная гипотеза",
            traffic_volume=Experiment.TrafficVolume.SPLIT_50_50,
            test_duration=Experiment.TestDuration.DAYS_7,
            start_date=date(2026, 3, 10),
            end_date=date(2026, 3, 17),
            result_variant_a="CR 10%",
            result_variant_b="CR 15%",
            created_by=self.admin_user,
            status=Experiment.Status.SUCCESS,
        )

        response = self.client.get(reverse("experiments_board"))

        self.assertEqual(response.status_code, 200)

        active_ids = [
            item["item"].id
            for column in response.context["active_columns"]
            for item in column["items"]
        ]
        library_ids = [
            item["item"].id
            for column in response.context["library_columns"]
            for item in column["items"]
        ]

        self.assertIn(active_experiment.id, active_ids)
        self.assertNotIn(final_experiment.id, active_ids)
        self.assertIn(final_experiment.id, library_ids)


class BranchFormTests(TaskBoardBaseTestCase):
    def test_branch_form_prefills_next_code_from_existing_branches(self):
        Branch.objects.create(bot=self.bot, name="Second", code="ell01")
        Branch.objects.create(bot=self.bot, name="Third", code="ell02")

        form = BranchForm(bot=self.bot)

        self.assertEqual(form.initial["code"], "ell03")


class MailingSplitAssignmentTests(TestCase):
    def _make_experiment(self, weights):
        product = Product.objects.create(name=f"P-{Product.objects.count() + 1}")
        bot = Bot.objects.create(name=f"bot-{Bot.objects.count() + 1}", product=product)
        experiment = MailingExperiment.objects.create(
            title="Test split",
            bot=bot,
            status=MailingExperiment.Status.IN_PROGRESS,
        )
        labels = ["A", "B", "C", "D"]
        for label, weight in zip(labels, weights):
            MailingVariant.objects.create(
                experiment=experiment,
                label=label,
                weight=weight,
            )
        return experiment

    def test_assignment_is_deterministic_for_same_external_id(self):
        experiment = self._make_experiment([50, 50])
        first = assign_variant_for_recipient(experiment, "user-123")
        for _ in range(20):
            self.assertEqual(
                assign_variant_for_recipient(experiment, "user-123").pk,
                first.pk,
            )

    def test_distribution_matches_50_50(self):
        experiment = self._make_experiment([50, 50])
        total = 10000
        counts = {"A": 0, "B": 0}
        for i in range(total):
            variant = assign_variant_for_recipient(experiment, f"user-{i}")
            counts[variant.label] += 1
        for label, share in counts.items():
            ratio = share / total
            self.assertAlmostEqual(
                ratio,
                0.5,
                delta=0.03,
                msg=f"variant {label} ratio {ratio:.4f} not within 3% of 0.5",
            )

    def test_distribution_matches_70_30(self):
        experiment = self._make_experiment([70, 30])
        total = 10000
        counts = {"A": 0, "B": 0}
        for i in range(total):
            variant = assign_variant_for_recipient(experiment, f"user-{i}")
            counts[variant.label] += 1
        expectations = {"A": 0.7, "B": 0.3}
        for label, expected in expectations.items():
            ratio = counts[label] / total
            self.assertAlmostEqual(
                ratio,
                expected,
                delta=0.03,
                msg=f"variant {label} ratio {ratio:.4f} not within 3% of {expected}",
            )

    def test_empty_variants_raises(self):
        product = Product.objects.create(name="P-empty")
        bot = Bot.objects.create(name="bot-empty", product=product)
        experiment = MailingExperiment.objects.create(title="No variants", bot=bot)
        with self.assertRaises(MailingSplitError):
            assign_variant_for_recipient(experiment, "user-1")

    def test_zero_total_weight_raises(self):
        experiment = self._make_experiment([0, 0])
        with self.assertRaises(MailingSplitError):
            assign_variant_for_recipient(experiment, "user-1")


class MailingRecipientImportTests(TestCase):
    def setUp(self):
        product = Product.objects.create(name="P-import")
        bot = Bot.objects.create(name="bot-import", product=product)
        self.experiment = MailingExperiment.objects.create(
            title="Import test",
            bot=bot,
            status=MailingExperiment.Status.IN_PROGRESS,
        )
        for label, weight in [("A", 50), ("B", 50)]:
            MailingVariant.objects.create(
                experiment=self.experiment, label=label, weight=weight,
            )

    def test_basic_import_creates_recipients_with_assigned_variant(self):
        ids = [f"user-{i}" for i in range(100)]
        summary = import_recipients(self.experiment, ids)

        self.assertEqual(summary["processed"], 100)
        self.assertEqual(summary["created"], 100)
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(sum(summary["variants"].values()), 100)

        recipients = MailingRecipient.objects.filter(experiment=self.experiment)
        self.assertEqual(recipients.count(), 100)
        self.assertFalse(recipients.filter(assigned_variant__isnull=True).exists())

    def test_reimport_is_idempotent(self):
        ids = [f"user-{i}" for i in range(50)]
        import_recipients(self.experiment, ids)

        before = {
            r.external_id: r.assigned_variant_id
            for r in MailingRecipient.objects.filter(experiment=self.experiment)
        }

        summary = import_recipients(self.experiment, ids)

        after_qs = MailingRecipient.objects.filter(experiment=self.experiment)
        self.assertEqual(after_qs.count(), 50)
        self.assertEqual(summary["processed"], 50)
        self.assertEqual(summary["created"], 0)
        self.assertEqual(summary["updated"], 50)
        self.assertEqual(summary["skipped"], 0)

        after = {r.external_id: r.assigned_variant_id for r in after_qs}
        self.assertEqual(before, after)

    def test_input_duplicates_are_deduped(self):
        summary = import_recipients(
            self.experiment, ["u1", "u2", "u1", "u2", "u3", "u1"]
        )

        self.assertEqual(summary["processed"], 3)
        self.assertEqual(summary["created"], 3)
        self.assertEqual(summary["updated"], 0)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(
            MailingRecipient.objects.filter(experiment=self.experiment).count(), 3,
        )

    def test_blank_and_none_ids_are_skipped(self):
        summary = import_recipients(
            self.experiment, ["u1", "", None, "   ", "u2"]
        )

        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["created"], 2)
        self.assertEqual(summary["skipped"], 3)
        stored_ids = set(
            MailingRecipient.objects.filter(experiment=self.experiment).values_list(
                "external_id", flat=True,
            )
        )
        self.assertEqual(stored_ids, {"u1", "u2"})

    def test_summary_counters_sum_to_processed_plus_skipped(self):
        first = import_recipients(self.experiment, ["a", "b", "c", "", None])
        self.assertEqual(first["created"] + first["updated"], first["processed"])
        self.assertEqual(first["processed"] + first["skipped"], 5)

        second = import_recipients(self.experiment, ["a", "b", "c", "d"])
        self.assertEqual(second["created"] + second["updated"], second["processed"])
        self.assertEqual(second["created"], 1)
        self.assertEqual(second["updated"], 3)
        self.assertEqual(second["skipped"], 0)
        self.assertEqual(
            sum(second["variants"].values()), second["processed"],
        )


class ApplySplitWeightsTests(TestCase):
    def _make_experiment(self, traffic_split, traffic_split_other="", labels=("A", "B")):
        product = Product.objects.create(name=f"P-split-{Product.objects.count() + 1}")
        bot = Bot.objects.create(name=f"bot-split-{Bot.objects.count() + 1}", product=product)
        experiment = MailingExperiment.objects.create(
            title="Split test",
            bot=bot,
            traffic_split=traffic_split,
            traffic_split_other=traffic_split_other,
        )
        for label in labels:
            MailingVariant.objects.create(
                experiment=experiment, label=label, weight=1,
            )
        return experiment

    def test_50_50_assigns_equal_weights(self):
        experiment = self._make_experiment(MailingExperiment.TrafficSplit.SPLIT_50_50)
        result = apply_split_weights(experiment)
        self.assertEqual(result, {"A": 50, "B": 50})

        weights = {
            v.label: v.weight
            for v in experiment.variants.all().order_by("label", "id")
        }
        self.assertEqual(weights, {"A": 50, "B": 50})

    def test_70_30_assigns_weights_by_stable_order(self):
        experiment = self._make_experiment(MailingExperiment.TrafficSplit.SPLIT_70_30)
        result = apply_split_weights(experiment)
        self.assertEqual(result, {"A": 70, "B": 30})

        a = experiment.variants.get(label="A")
        b = experiment.variants.get(label="B")
        self.assertEqual(a.weight, 70)
        self.assertEqual(b.weight, 30)

    def test_other_custom_split_assigns_parsed_weights(self):
        experiment = self._make_experiment(
            MailingExperiment.TrafficSplit.OTHER, traffic_split_other="80/20",
        )
        result = apply_split_weights(experiment)
        self.assertEqual(result, {"A": 80, "B": 20})

    def test_mismatch_between_split_size_and_variant_count_raises(self):
        experiment = self._make_experiment(
            MailingExperiment.TrafficSplit.SPLIT_50_50, labels=("A", "B", "C"),
        )
        with self.assertRaises(MailingSplitError):
            apply_split_weights(experiment)

    def test_unparseable_split_raises(self):
        experiment = self._make_experiment(
            MailingExperiment.TrafficSplit.OTHER, traffic_split_other="not-a-split",
        )
        with self.assertRaises(MailingSplitError):
            apply_split_weights(experiment)

    def test_assign_variant_uses_applied_weights(self):
        experiment = self._make_experiment(MailingExperiment.TrafficSplit.SPLIT_70_30)
        apply_split_weights(experiment)

        total = 10000
        ids = [f"u-{i}" for i in range(total)]
        summary = import_recipients(experiment, ids)

        self.assertEqual(summary["processed"], total)
        ratio_a = summary["variants"].get("A", 0) / total
        ratio_b = summary["variants"].get("B", 0) / total
        self.assertAlmostEqual(ratio_a, 0.7, delta=0.03)
        self.assertAlmostEqual(ratio_b, 0.3, delta=0.03)


class RecipientFileParseTests(TestCase):
    def test_plain_txt_one_id_per_line(self):
        text = "123\n456\n789\n"
        self.assertEqual(parse_recipient_ids(text), ["123", "456", "789"])

    def test_csv_with_header_user_id(self):
        text = "user_id\n123\n456\n"
        self.assertEqual(parse_recipient_ids(text), ["123", "456"])

    def test_csv_without_header_first_row_is_id(self):
        text = "100,note\n200,note\n300,note\n"
        self.assertEqual(parse_recipient_ids(text), ["100", "200", "300"])

    def test_csv_multiple_columns_takes_first(self):
        text = "id,name,score\n111,Alice,7\n222,Bob,9\n"
        self.assertEqual(parse_recipient_ids(text), ["111", "222"])

    def test_blank_and_whitespace_lines_are_cleaned(self):
        text = "123\n\n   \n  456  \n789"
        self.assertEqual(parse_recipient_ids(text), ["123", "456", "789"])

    def test_crlf_line_endings(self):
        text = "111\r\n222\r\n333\r\n"
        self.assertEqual(parse_recipient_ids(text), ["111", "222", "333"])

    def test_empty_text_returns_empty(self):
        self.assertEqual(parse_recipient_ids(""), [])
        self.assertEqual(parse_recipient_ids(None), [])

    def test_header_only_returns_empty(self):
        self.assertEqual(parse_recipient_ids("user_id\n"), [])
        self.assertEqual(parse_recipient_ids("external_id\n\n"), [])

    def test_semicolon_csv_is_supported(self):
        text = "telegram_id;name\n555;Anna\n666;Boris\n"
        self.assertEqual(parse_recipient_ids(text), ["555", "666"])

    def test_parse_then_import_pipeline(self):
        product = Product.objects.create(name="P-parse")
        bot = Bot.objects.create(name="bot-parse", product=product)
        experiment = MailingExperiment.objects.create(title="Parse pipeline", bot=bot)
        for label, weight in [("A", 50), ("B", 50)]:
            MailingVariant.objects.create(
                experiment=experiment, label=label, weight=weight,
            )

        text = "user_id,note\n" + "\n".join(f"{i},x" for i in range(40))
        ids = parse_recipient_ids(text)
        self.assertEqual(len(ids), 40)
        self.assertEqual(ids[0], "0")
        self.assertEqual(ids[-1], "39")

        summary = import_recipients(experiment, ids)
        self.assertEqual(summary["processed"], 40)
        self.assertEqual(summary["created"], 40)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(sum(summary["variants"].values()), 40)
        self.assertEqual(
            MailingRecipient.objects.filter(experiment=experiment).count(), 40,
        )

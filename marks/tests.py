from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
        self.branch = Branch.objects.create(bot=self.bot, name="Main", code="MN")


class TaskBoardAccessTests(TaskBoardBaseTestCase):
    def test_admin_has_access_to_tasks_board(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse("tasks_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Задачи")

    def test_non_admin_has_no_access_to_tasks_board(self):
        self.client.force_login(self.manager_user)
        response = self.client.get(reverse("tasks_board"))

        self.assertEqual(response.status_code, 403)


class TaskBoardActionsTests(TaskBoardBaseTestCase):
    @patch("marks.views.notify_new_task")
    def test_create_patch_task(self, notify_mock):
        self.client.force_login(self.admin_user)
        deadline = timezone.now() + timedelta(days=3)
        response = self.client.post(
            reverse("create_patch_task"),
            {
                "branches": [self.branch.id],
                "cjm_url": "https://example.com/cjm",
                "comment": "Комментарий",
                "deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("tasks_board"))

        task = TaskRequest.objects.get()
        self.assertEqual(task.task_type, TaskRequest.Type.PATCH)
        self.assertEqual(task.status, TaskRequest.Status.UNREAD)
        self.assertEqual(task.created_by, self.admin_user)
        self.assertEqual(list(task.branches.values_list("id", flat=True)), [self.branch.id])
        notify_mock.assert_called_once_with(task)

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

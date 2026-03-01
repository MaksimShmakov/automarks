from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone


class Product(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return self.name


class Bot(models.Model):
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="bots")
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    salebot_url = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)


    def __str__(self):
        return self.name


class PlanMonthly(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="plans")
    month = models.DateField(help_text="Первое число месяца (YYYY-MM-01)")


    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    revenue_target = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    warm_leads_target = models.IntegerField(default=0)
    cold_leads_target = models.IntegerField(default=0)
    notes = models.TextField(blank=True)


    class Meta:
        unique_together = ("product", "month")
        ordering = ["-month"]


    def __str__(self):
        return f"{self.product} · {self.month:%Y-%m}"


class BranchPlanMonthly(models.Model):
    branch = models.ForeignKey("Branch", on_delete=models.CASCADE, related_name="plans")
    month = models.DateField()
    warm_leads = models.IntegerField(default=0)
    cold_leads = models.IntegerField(default=0)
    expected_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    comment = models.CharField(max_length=255, blank=True)


    class Meta:
        unique_together = ("branch", "month")
        ordering = ["branch__bot__name", "branch__name", "-month"]


    def __str__(self):
        return f"{self.branch} · {self.month:%Y-%m}"


class Funnel(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="funnels")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        unique_together = ("product", "name")


    def __str__(self):
        return f"{self.product} · {self.name}"


class TrafficReport(models.Model):
    class Platform(models.TextChoices):
        TG = "tg", "Telegram"
        VK = "vk", "VK"
        TIKTOK = "tt", "TikTok"
        INST = "ig", "Instagram"
        OTHER = "other", "Другое"


    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="traffic_reports")
    month = models.DateField()
    platform = models.CharField(max_length=20, choices=Platform.choices, default=Platform.OTHER)
    vendor = models.CharField(max_length=255, help_text="Подрядчик/исполнитель")
    spend = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    leads_warm = models.IntegerField(default=0)
    leads_cold = models.IntegerField(default=0)
    notes = models.CharField(max_length=255, blank=True)


    class Meta:
        ordering = ["-month", "platform", "vendor"]


class PatchNote(models.Model):
    branch = models.ForeignKey("Branch", on_delete=models.CASCADE, related_name="patch_notes")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=255)
    change_description = models.TextField()


    change_type = models.CharField(max_length=50, default="update", help_text="например: план, метки, воронка, отчёт")


    class Meta:
        ordering = ["-created_at"]


    def __str__(self):
        return f"{self.branch} · {self.title}"


class Branch(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        unique_together = ("bot", "code")


    def __str__(self):
        return f"{self.bot.name} - {self.name} ({self.code})"


class TaskRequest(models.Model):
    class Type(models.TextChoices):
        PATCH = "patch", "Правка в ветках бота"
        MAILING = "mailing", "Рассылка"
        BUILD = "build", "Сборка бота"

    class Status(models.TextChoices):
        UNREAD = "unread", "Непрочитанное"
        IN_PROGRESS = "in_progress", "В процессе"
        DONE = "done", "Готово"

    task_type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNREAD)
    branches = models.ManyToManyField(Branch, related_name="task_requests", blank=True)

    cjm_url = models.URLField(blank=True, default="")
    tz_url = models.URLField(blank=True, default="")
    build_name = models.CharField(max_length=255, blank=True, default="")
    build_token = models.CharField(max_length=255, blank=True, default="")
    comment = models.TextField(blank=True, default="")
    deadline = models.DateTimeField()

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.id} {self.get_task_type_display()}"

    def save(self, *args, **kwargs):
        if self.status == self.Status.DONE and self.completed_at is None:
            self.completed_at = timezone.now()
        elif self.status != self.Status.DONE and self.completed_at is not None:
            self.completed_at = None
        super().save(*args, **kwargs)

    @staticmethod
    def _bot_branch_label(branch):
        bot_name = (getattr(getattr(branch, "bot", None), "name", "") or "").strip()
        branch_name = (getattr(branch, "name", "") or "").strip()
        if not bot_name:
            return ""
        if not branch_name or branch_name.lower() == "main":
            return bot_name
        normalized_branch = "_".join(branch_name.split())
        return f"{bot_name}_{normalized_branch}"

    def get_bot_branch_labels(self):
        labels = []
        seen = set()
        for branch in self.branches.select_related("bot").all():
            label = self._bot_branch_label(branch)
            if label and label not in seen:
                labels.append(label)
                seen.add(label)
        if labels:
            return labels

        raw = (self.build_name or "").strip()
        if not raw:
            return []
        fallback = []
        for part in raw.split(","):
            value = part.strip()
            if value and value not in seen:
                fallback.append(value)
                seen.add(value)
        return fallback

    def get_bot_branch_text(self):
        labels = self.get_bot_branch_labels()
        if not labels:
            return "-"
        return ", ".join(labels)

    def get_scope_units(self):
        if self.task_type not in {self.Type.PATCH, self.Type.MAILING, self.Type.BUILD}:
            return 0
        labels = self.get_bot_branch_labels()
        if labels:
            return len(labels)
        return 1


class Experiment(models.Model):
    class Status(models.TextChoices):
        BACKLOG = "backlog", "Backlog"
        DRAFT = "draft", "Draft"
        IN_PROGRESS = "in_progress", "В процессе"
        COMPLETED = "completed", "Завершен"
        SUCCESS = "success", "Успех"
        FAILED = "failed", "Провал"
        RETEST = "retest", "Нужен ретест"

    class TrafficVolume(models.TextChoices):
        SPLIT_50_50 = "50_50", "50/50"
        SPLIT_70_30 = "70_30", "70/30"
        PART_OF_BASE = "part_of_base", "Только часть базы"
        OTHER = "other", "Другое"

    class TestDuration(models.TextChoices):
        DAYS_3 = "3_days", "3 дня"
        DAYS_7 = "7_days", "7 дней"
        UNTIL_USERS = "until_users", "До набора X пользователей"
        END_DATE = "end_date", "Конкретная дата окончания"

    title = models.CharField(max_length=255, blank=True, default="")
    wants_ab_test = models.BooleanField(default=False)
    ab_test_options = models.JSONField(blank=True, default=list)
    ab_test_custom_option = models.CharField(max_length=255, blank=True, default="")
    metric_impact = models.CharField(max_length=255, blank=True, default="")
    expected_change = models.CharField(max_length=255, blank=True, default="")
    hypothesis = models.TextField(blank=True, default="")
    traffic_volume = models.CharField(max_length=20, choices=TrafficVolume.choices, blank=True, default="")
    traffic_volume_other = models.CharField(max_length=255, blank=True, default="")
    test_duration = models.CharField(max_length=20, choices=TestDuration.choices, blank=True, default="")
    duration_users = models.PositiveIntegerField(null=True, blank=True)
    duration_end_date = models.DateField(null=True, blank=True)
    comment = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BACKLOG)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        name = self.title or f"Эксперимент #{self.id}"
        return f"{name} ({self.get_status_display()})"


class Tag(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="tags")
    number = models.CharField(max_length=20, blank=True)
    utm_source = models.CharField(max_length=255, blank=True, null=True)
    utm_medium = models.CharField(max_length=255, blank=True, null=True)
    utm_campaign = models.CharField(max_length=255, blank=True, null=True)
    utm_term = models.CharField(max_length=255, blank=True, null=True)
    utm_content = models.CharField(max_length=255, blank=True, null=True)
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=None, null=True, blank=True, verbose_name="Бюджет")
    url = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        unique_together = ("branch", "number")
        ordering = ["number"]


    def save(self, *args, **kwargs):
        if not self.number:
            prefix = self.branch.code
            last_tag = Tag.objects.filter(branch=self.branch).order_by("-number").first()
            if last_tag:
                last_num = int(last_tag.number.replace(prefix, ""))
                new_num = str(last_num + 1).zfill(4)
            else:
                new_num = "0001"
            self.number = f"{prefix}{new_num}"


        if not self.url:
            self.url = f"https://t.me/{self.branch.bot.name}?start={self.number}"


        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.number} ({self.branch})"


@receiver(post_save, sender=Branch)
def create_first_tag(sender, instance, created, **kwargs):
    if created and not instance.tags.exists():
        Tag.objects.create(branch=instance)


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Максимальный"
        MANAGER = "manager", "Руководитель"
        MARKETER = "marketer", "Линейный (автометки)"
        BOT_USER = "bot_user", "Оператор ботов"


    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MARKETER)


    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

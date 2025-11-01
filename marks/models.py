from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.contrib.auth.models import User


# === Product ===
class Product(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# --- ДОБАВЬ FK в существующую модель Bot ---
class Bot(models.Model):
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="bots")
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name


# === План по продукту (месячный) ===
class PlanMonthly(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="plans")
    month = models.DateField(help_text="Первое число месяца (YYYY-MM-01)")
    # ключевые KPI — под себя дополнишь
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


# === Детализация плана по веткам (месяц) ===
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


# === Воронка продукта ===
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


# === Отчёт по трафику ===
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


# === Патч-ноут по веткам ===
class PatchNote(models.Model):
    branch = models.ForeignKey("Branch", on_delete=models.CASCADE, related_name="patch_notes")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=255)
    change_description = models.TextField()
    # простая категоризация
    change_type = models.CharField(max_length=50, default="update", help_text="например: план, метки, воронка, отчёт")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.branch} · {self.title}"


class Branch(models.Model):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=50)  # человекочитаемое название
    code = models.CharField(max_length=10)  # ell01, ell02...
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("bot", "code")

    def __str__(self):
        return f"{self.bot.name} - {self.name} ({self.code})"


class Tag(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="tags")
    number = models.CharField(max_length=20, blank=True)  # ell010001
    utm_source = models.CharField(max_length=255, blank=True, null=True)
    utm_medium = models.CharField(max_length=255, blank=True, null=True)
    utm_campaign = models.CharField(max_length=255, blank=True, null=True)
    utm_term = models.CharField(max_length=255, blank=True, null=True)
    utm_content = models.CharField(max_length=255, blank=True, null=True)
    url = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("branch", "number")

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


# 🔹 Сигнал: при создании новой ветки → создаём первую метку
@receiver(post_save, sender=Branch)
def create_first_tag(sender, instance, created, **kwargs):
    if created and not instance.tags.exists():
        Tag.objects.create(branch=instance)  # сработает автогенерация number = ell01 + 0001


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Максимальный"
        MANAGER = "manager", "Руководитель"
        MARKETER = "marketer", "Линейный (автометки)"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MARKETER)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

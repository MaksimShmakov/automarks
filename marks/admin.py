from django.contrib import admin
from .models import (
    Product,
    Bot,
    Branch,
    PlanMonthly,
    BranchPlanMonthly,
    Funnel,
    TrafficReport,
    PatchNote,
    UserProfile,
    TaskRequest,
    Experiment,
    ShortLink,
    UtmDictionaryEntry,
    MarkedLink,
    OutboundNotification,
)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at", "bots_count")
    list_filter = ("is_active",)
    search_fields = ("name",)
    def bots_count(self, obj): return obj.bots.count()


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = ("title", "platform", "name", "product", "created_at")
    list_filter = ("platform", "product")
    search_fields = ("name", "display_name", "product__name")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "bot", "product")
    list_filter = ("bot__product", "bot")
    search_fields = ("name", "code", "bot__name", "bot__product__name")

    def product(self, obj):
        return obj.bot.product
    product.short_description = "Product"


@admin.register(PlanMonthly)
class PlanMonthlyAdmin(admin.ModelAdmin):
    list_display = ("product", "month", "budget", "revenue_target", "warm_leads_target", "cold_leads_target")
    list_filter = ("product", "month")
    search_fields = ("product__name",)


@admin.register(BranchPlanMonthly)
class BranchPlanMonthlyAdmin(admin.ModelAdmin):
    list_display = ("branch", "month", "warm_leads", "cold_leads", "expected_revenue")
    list_filter = ("branch__bot__product", "branch__bot", "month")
    search_fields = ("branch__name", "branch__bot__name")


@admin.register(Funnel)
class FunnelAdmin(admin.ModelAdmin):
    list_display = ("product", "name", "is_active", "created_at")
    list_filter = ("product", "is_active")
    search_fields = ("name", "product__name")


@admin.register(TrafficReport)
class TrafficReportAdmin(admin.ModelAdmin):
    list_display = ("product", "month", "platform", "vendor", "spend", "clicks", "leads_warm", "leads_cold")
    list_filter = ("product", "platform", "month")
    search_fields = ("vendor",)


@admin.register(PatchNote)
class PatchNoteAdmin(admin.ModelAdmin):
    list_display = ("branch", "title", "change_type", "created_by", "created_at")
    list_filter = ("change_type", "branch__bot__product")
    search_fields = ("title", "change_description")


@admin.register(TaskRequest)
class TaskRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "task_type", "status", "deadline", "created_by", "created_at", "completed_at")
    list_filter = ("task_type", "status", "deadline")
    search_fields = ("comment", "build_name", "cjm_url", "tz_url", "created_by__username")
    filter_horizontal = ("branches",)


@admin.register(Experiment)
class ExperimentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "start_date", "end_date", "wants_ab_test", "created_by", "created_at", "updated_at")
    list_filter = ("status", "wants_ab_test", "traffic_volume", "test_duration")
    search_fields = ("title", "metric_impact", "expected_change", "hypothesis", "comment", "result_variant_a", "result_variant_b")


@admin.register(ShortLink)
class ShortLinkAdmin(admin.ModelAdmin):
    list_display = ("code", "target_url", "clicks", "last_click_at", "created_by", "created_at")
    search_fields = ("code", "target_url")
    readonly_fields = ("clicks", "last_click_at", "created_at")


@admin.register(UtmDictionaryEntry)
class UtmDictionaryEntryAdmin(admin.ModelAdmin):
    list_display = ("field", "value", "label", "group", "is_template", "is_active", "synced_at")
    list_filter = ("field", "is_active", "is_template")
    search_fields = ("value", "label", "group")


@admin.register(MarkedLink)
class MarkedLinkAdmin(admin.ModelAdmin):
    list_display = ("utm_campaign", "utm_source", "utm_medium", "author", "pending_review", "created_at")
    list_filter = ("utm_source", "direction", "pending_review")
    search_fields = ("utm_campaign", "original_url", "full_url", "author__username")


@admin.register(OutboundNotification)
class OutboundNotificationAdmin(admin.ModelAdmin):
    list_display = ("chat_id", "delivered", "attempts", "created_at", "delivered_at", "last_error")
    list_filter = ("delivered",)
    search_fields = ("chat_id", "text", "last_error")
    readonly_fields = ("created_at", "delivered_at")

from django.contrib import admin
from .models import (
    Product, PlanMonthly, BranchPlanMonthly, Funnel, TrafficReport, PatchNote, UserProfile
)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at", "bots_count")
    list_filter = ("is_active",)
    search_fields = ("name",)
    def bots_count(self, obj): return obj.bots.count()

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

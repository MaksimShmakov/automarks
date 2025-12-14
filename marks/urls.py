from django.urls import path
from django.shortcuts import redirect
from django.contrib.auth import views as auth_views
from django.views.decorators.cache import never_cache
from marks import views, views_products


# ---------- Главная ----------
def root_redirect(request):
    """Главная страница — редирект в зависимости от авторизации."""
    if request.user.is_authenticated:
        return redirect(views.get_role_home_view_name(request.user))
    return redirect("/accounts/login/")


# ---------- LoginView безопасно ----------
@never_cache
def safe_login_view(request, *args, **kwargs):
    """Login без redirect_authenticated_user и без ошибок 500."""
    if request.user.is_authenticated:
        return redirect(views.get_role_home_view_name(request.user))
    view = views.RoleAwareLoginView.as_view()
    return view(request, *args, **kwargs)


urlpatterns = [
    # Главная
    path("", root_redirect, name="home"),

    # --- Аутентификация ---
    path("accounts/login/", safe_login_view, name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="/accounts/login/"), name="logout"),

    # --- Основные страницы ---
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/export/excel/", views.export_excel, name="export_excel"),
    path("dashboard/export/pdf/", views.export_pdf, name="export_pdf"),

    # --- Боты и метки ---
    path("bots/", views.bots_list, name="bots_list"),
    path("bot/<int:bot_id>/", views.branches_list, name="branches_list"),
    path("branch/<int:branch_id>/", views.tags_list, name="tags_list"),
    path("tag/<int:tag_id>/edit/", views.edit_tag, name="edit_tag"),
    path("tag/<int:tag_id>/duplicate/", views.duplicate_tag, name="duplicate_tag"),
    path("branch/<int:branch_id>/copy/", views.copy_tags, name="copy_tags"),
    path("branch/<int:branch_id>/paste/", views.paste_tags, name="paste_tags"),
    path("branch/<int:branch_id>/import/", views.import_tags_csv, name="import_tags_csv"),
    path("branch/<int:branch_id>/duplicate_all/", views.duplicate_all_tags, name="duplicate_all_tags"),
    path("api/bot/<str:bot_name>/", views.bot_api, name="bot_api"),

    # --- Продукты ---
    path("products/", views_products.products_list, name="products_list"),
    path("products/<int:product_id>/", views_products.product_detail, name="product_detail"),
    path("plans/new/", views_products.plan_create, name="plan_create"),
    path("funnels/new/", views_products.funnel_master_create, name="funnel_create"),
    path("traffic/new/", views_products.traffic_report_create, name="traffic_create"),
    path("patch/new/", views_products.patchnote_create, name="patch_create"),
    path("product/<int:product_id>/reports/", views.product_reports, name="product_reports"),

    # --- AJAX / утилиты ---
    path("update_field/", views.update_field, name="update_field"),
]

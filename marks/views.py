from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import login
from django.urls import reverse
from datetime import datetime, timedelta
from django.db import transaction, connection
from django.db.models import Sum, Count
from django.utils import timezone
from decimal import Decimal
import logging
import json
import csv
import io
from urllib.parse import urlencode
import openpyxl
from openpyxl.styles import Font, Alignment
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


from .models import Bot, Branch, Tag, Product, PlanMonthly, Funnel, TrafficReport, PatchNote, UserProfile, TaskRequest, Experiment
from .forms import (
    BotForm,
    BotStatusForm,
    BotDetailsForm,
    BranchForm,
    TagForm,
    CustomUserCreationForm,
    TagImportForm,
    PatchTaskRequestForm,
    MailingTaskRequestForm,
    BuildTaskRequestForm,
    TaskStatusForm,
    ExperimentForm,
)
from .permissions import require_roles, BOT_OPERATORS_GROUP
from .services.telegram import notify_new_task, notify_status_change, notify_done_to_user

logger = logging.getLogger(__name__)

TAG_UTM_FIELDS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]
TAG_CLEAR_FIELDS = {field: None for field in TAG_UTM_FIELDS}
TAG_CLEAR_FIELDS["budget"] = None
TAG_CLEAR_FIELDS["url"] = None
TAG_UNDO_SESSION_KEY = "last_tag_action"


def get_user_role(user):
    return getattr(getattr(user, "profile", None), "role", None)


def get_role_home_view_name(user):
    return "dashboard"

def _active_tags_qs(tags_qs):
    return tags_qs.filter(url__isnull=False)

def _tag_snapshot(tag):
    snapshot = {field: getattr(tag, field) for field in TAG_UTM_FIELDS + ["budget", "url"]}
    if snapshot.get("budget") is not None:
        snapshot["budget"] = str(snapshot["budget"])
    return snapshot

def _set_last_tag_action(request, action, branch_id, payload):
    request.session[TAG_UNDO_SESSION_KEY] = {
        "action": action,
        "branch_id": branch_id,
        "payload": payload,
    }
    request.session.modified = True


class RoleAwareLoginView(LoginView):
    template_name = "registration/login.html"


    def get_success_url(self):
        return reverse(get_role_home_view_name(self.request.user))


def user_is_admin(user):
    role = get_user_role(user)
    if user.is_superuser or role == UserProfile.Role.ADMIN:
        return True
    try:
        return user.groups.filter(name="Администратор").exists()
    except Exception:
        return False


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst')
def export_pdf(request):
    month = int(request.GET.get("month", datetime.now().month))
    year = int(request.GET.get("year", datetime.now().year))


    response = HttpResponse(content_type="application/pdf")
    filename = f"Отчёт_{month}_{year}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'


    p = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    y = height - 100


    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, y, f"Отчёт по продуктам - {month}.{year}")
    y -= 30


    p.setFont("Helvetica", 11)
    for d in _get_dashboard_data(month, year):
        p.drawString(50, y, f"{d['product'].name}")
        y -= 20
        p.drawString(70, y, f"Расход: {d['spend']} руб. ({d['spend_delta']}%)")
        y -= 15
        p.drawString(70, y, f"Лиды: {d['leads']} ({d['leads_delta']}%)")
        y -= 25
        if y < 100:
            p.showPage()
            y = height - 100
            p.setFont("Helvetica", 11)
    p.save()
    return response


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst')
def export_excel(request):
    month = int(request.GET.get("month", datetime.now().month))
    year = int(request.GET.get("year", datetime.now().year))


    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Отчёт {month}.{year}"
    ws.append(["Продукт", "Расход (руб.)", "Лиды", "Изм. расхода (%)", "Изм. лидов (%)"])


    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")


    for d in _get_dashboard_data(month, year):
        ws.append([
            d["product"].name,
            d["spend"],
            d["leads"],
            f"{d['spend_delta']}%" if d["spend_delta"] else "-",
            f"{d['leads_delta']}%" if d["leads_delta"] else "-",
        ])


    for column_cells in ws.columns:
        max_len = max(len(str(c.value or "")) for c in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = max_len + 2


    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="Отчёт_{month}_{year}.xlsx"'
    wb.save(response)
    return response


def _get_dashboard_data(month, year):
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    products = Product.objects.all()
    def delta(curr, prev):
        if prev == 0:
            return None
        return round(((curr - prev) / prev) * 100, 1)
    data = []
    for product in products:
        reports = TrafficReport.objects.filter(product=product, month__month=month, month__year=year)
        prev_reports = TrafficReport.objects.filter(product=product, month__month=prev_month, month__year=prev_year)
        total_spend = reports.aggregate(Sum("spend"))["spend__sum"] or 0
        prev_spend = prev_reports.aggregate(Sum("spend"))["spend__sum"] or 0
        total_leads = (
            (reports.aggregate(Sum("leads_warm"))["leads_warm__sum"] or 0)
            + (reports.aggregate(Sum("leads_cold"))["leads_cold__sum"] or 0)
        )
        prev_leads = (
            (prev_reports.aggregate(Sum("leads_warm"))["leads_warm__sum"] or 0)
            + (prev_reports.aggregate(Sum("leads_cold"))["leads_cold__sum"] or 0)
        )
        data.append({
            "product": product,
            "spend": total_spend,
            "leads": total_leads,
            "spend_delta": delta(total_spend, prev_spend),
            "leads_delta": delta(total_leads, prev_leads),
        })
    return data


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def dashboard(request):
    return render(
        request,
        "marks/dashboard.html",
        {
            "is_admin_user": user_is_admin(request.user),
        },
    )


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)
def update_field(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Некорректный JSON"}, status=400)


    model_type = data.get("model")
    record_id = data.get("id")
    field = data.get("field")
    value = data.get("value")


    model_map = {"plan": PlanMonthly, "report": TrafficReport, "tag": Tag}
    allowed_fields = {
        "plan": {"budget", "revenue_target", "warm_leads_target", "cold_leads_target", "notes"},
        "report": {"spend", "impressions", "clicks", "leads_warm", "leads_cold", "vendor", "notes", "platform", "month"},
        "tag": {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "budget"},
    }


    model = model_map.get(model_type)
    if not model:
        return JsonResponse({"error": "Недопустимая модель"}, status=400)
    if field not in allowed_fields.get(model_type, set()):
        return JsonResponse({"error": "Поле недоступно"}, status=400)


    try:
        obj = model.objects.get(id=record_id)
        previous_tag_snapshot = _tag_snapshot(obj) if model_type == "tag" else None
        model_field = obj._meta.get_field(field)
        itype = model_field.get_internal_type()


        def to_bool(v):
            if isinstance(v, bool):
                return v
            return str(v).lower() in {"1", "true", "yes", "on"}


        if itype in {"DecimalField"}:
            if model_type == "tag" and field == "budget" and (value is None or str(value).strip() == ""):
                coerced = None
            else:
                coerced = Decimal(value or 0)
        elif itype in {"IntegerField", "PositiveIntegerField", "BigIntegerField"}:
            coerced = int(value or 0)
        elif itype in {"DateField"}:
            s = (value or "").strip()
            if len(s) == 7:
                s = f"{s}-01"
            coerced = datetime.strptime(s, "%Y-%m-%d").date()
        elif itype in {"BooleanField"}:
            coerced = to_bool(value)
        else:
            coerced = value


        setattr(obj, field, coerced)
        obj.save(update_fields=[field])
        if model_type == "tag" and previous_tag_snapshot is not None:
            _set_last_tag_action(
                request,
                "edit",
                obj.branch_id,
                {"tag_id": obj.id, "fields": previous_tag_snapshot},
            )
        return JsonResponse({"success": True})
    except model.DoesNotExist:
        return JsonResponse({"error": "Объект не найден"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)
def duplicate_all_tags(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)
    count = int(request.POST.get("count", 1))
    tags = list(_active_tags_qs(branch.tags))
    total_created = 0
    created_ids = []


    for _ in range(count):
        for tag in tags:
            new_tag = Tag.objects.create(
                branch=branch,
                utm_source=tag.utm_source,
                utm_medium=tag.utm_medium,
                utm_campaign=tag.utm_campaign,
                utm_term=tag.utm_term,
                utm_content=tag.utm_content,
                budget=tag.budget,
            )
            total_created += 1
            created_ids.append(new_tag.id)
    if created_ids:
        _set_last_tag_action(
            request,
            "duplicate_all",
            branch.id,
            {"tag_ids": created_ids},
        )


    messages.success(request, f"Скопировано {total_created} меток ({len(tags)} x {count}).")
    return redirect("tags_list", branch_id=branch.id)


def register(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            profile = getattr(user, "profile", None)
            if profile is None:
                profile = UserProfile.objects.create(user=user)
            if profile.role != UserProfile.Role.BOT_USER:
                profile.role = UserProfile.Role.BOT_USER
                profile.save(update_fields=["role"])


            group, _ = Group.objects.get_or_create(name=BOT_OPERATORS_GROUP)
            user.groups.add(group)


            login(request, user)
            return redirect("bots_list")
    else:
        form = CustomUserCreationForm()
    return render(request, "registration/register.html", {"form": form})


def bot_api(request, bot_name):
    try:
        bot = Bot.objects.get(name=bot_name)
    except Bot.DoesNotExist:
        return JsonResponse({"error": "Бот не найден"}, status=404)


    filterable_fields = [
        "number",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
    ]
    utm_fields = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]
    tag_filters = {
        field: request.GET.get(field)
        for field in filterable_fields
        if request.GET.get(field)
    }


    data = {"bot": bot.name, "branches": []}
    filtered_tags = []
    branches_qs = bot.branches.all().prefetch_related("tags")
    for branch in branches_qs:
        tags_qs = _active_tags_qs(branch.tags)
        if tag_filters:
            tags_qs = tags_qs.filter(**tag_filters)
        tags_payload = list(
            tags_qs.values(
                "number",
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_term",
                "utm_content",
                "budget",
                "url",
            )
        )
        for tag in tags_payload:
            for field in utm_fields:
                if not tag.get(field):
                    tag[field] = "None"


        if tag_filters:
            filtered_tags.extend(tags_payload)
            continue


        branch_data = {
            "name": branch.name,
            "code": branch.code,
            "tags": tags_payload,
        }
        data["branches"].append(branch_data)


    if tag_filters:
        if not filtered_tags:
            return JsonResponse([], safe=False)
        if len(filtered_tags) == 1:
            return JsonResponse(filtered_tags[0])
        return JsonResponse(filtered_tags, safe=False)


    return JsonResponse(data, safe=False)


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def bots_list(request):
    bots = Bot.objects.all().annotate(branches_total=Count("branches"))
    active_bots = bots.filter(is_active=True).order_by("name", "created_at")
    inactive_bots = bots.filter(is_active=False).order_by("name", "created_at")
    if request.method == "POST":
        form = BotForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("bots_list")
    else:
        form = BotForm()
    return render(
        request,
        "marks/bots_list.html",
        {
            "active_bots": active_bots,
            "inactive_bots": inactive_bots,
            "form": form,
        },
    )


@login_required
@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)
def branches_list(request, bot_id):
    bot = get_object_or_404(Bot, id=bot_id)
    branches = bot.branches.all()
    patchnotes = PatchNote.objects.filter(branch__bot=bot).select_related("branch")
    bot_status_form = BotStatusForm(bot=bot)
    bot_details_form = BotDetailsForm(instance=bot)
    form = BranchForm()
    if request.method == "POST":
        if request.POST.get("form_type") == "bot_status":
            bot_status_form = BotStatusForm(request.POST, bot=bot)
            if bot_status_form.is_valid():
                bot_status_form.save()
                messages.success(request, "Статус бота обновлён")
                return redirect("branches_list", bot_id=bot.id)
        elif request.POST.get("form_type") == "bot_details":
            bot_details_form = BotDetailsForm(request.POST, instance=bot)
            if bot_details_form.is_valid():
                bot_details_form.save()
                messages.success(request, "Информация о боте обновлена.")
                return redirect("branches_list", bot_id=bot.id)
        else:
            form = BranchForm(request.POST)
            if form.is_valid():
                branch = form.save(commit=False)
                branch.bot = bot
                branch.save()
                return redirect("branches_list", bot_id=bot.id)
    return render(
        request,
        "marks/branches_list.html",
        {
            "bot": bot,
            "branches": branches,
            "patchnotes": patchnotes,
            "form": form,
            "bot_status_form": bot_status_form,
            "bot_details_form": bot_details_form,
        },
    )


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def tags_list(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)
    tags = _active_tags_qs(branch.tags)
    patchnotes = branch.patch_notes.all()
    has_copied = bool(request.session.get("copied_tags"))


    if request.method == "POST" and "create_tag" in request.POST:
        if get_user_role(request.user) != 'analyst':
            form = TagForm(request.POST)
            if form.is_valid():
                tag = form.save(commit=False)
                tag.branch = branch
                tag.save()
                _set_last_tag_action(
                    request,
                    "create",
                    branch.id,
                    {"tag_ids": [tag.id]},
                )
                messages.success(request, "Метка создана")
                return redirect("tags_list", branch_id=branch.id)
    else:
        form = TagForm()


    import_form = TagImportForm()


    return render(
        request,
        "marks/tags_list.html",
        {
            "branch": branch,
            "tags": tags,
            "patchnotes": patchnotes,
            "form": form,
            "has_copied": has_copied,
            "import_form": import_form,
            "import_columns": TagImportForm.EXPECTED_COLUMNS,
        },
    )


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)
def edit_tag(request, tag_id):
    tag = get_object_or_404(Tag, id=tag_id, url__isnull=False)
    previous_tag_snapshot = _tag_snapshot(tag)
    form = TagForm(request.POST, instance=tag)
    if form.is_valid():
        form.save()
        _set_last_tag_action(
            request,
            "edit",
            tag.branch_id,
            {"tag_id": tag.id, "fields": previous_tag_snapshot},
        )
        messages.success(request, f"Метка {tag.number} обновлена")
    else:
        messages.error(request, "Ошибка при обновлении метки")
    return redirect("tags_list", branch_id=tag.branch.id)


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)
def copy_tags(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)
    copied = list(_active_tags_qs(branch.tags).values(
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "budget"
    ))
    for tag in copied:
        if tag.get("budget") is not None:
            tag["budget"] = str(tag["budget"])
    request.session["copied_tags"] = copied
    request.session.modified = True
    messages.success(request, "Таблица меток скопирована!")
    return redirect("tags_list", branch_id=branch.id)


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)
def paste_tags(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)
    copied_tags = request.session.get("copied_tags")
    if not copied_tags:
        messages.error(request, "Нет скопированных меток.")
        return redirect("tags_list", branch_id=branch.id)
    created_ids = []
    for tag_data in copied_tags:
        new_tag = Tag.objects.create(branch=branch, **tag_data)
        created_ids.append(new_tag.id)
    if created_ids:
        _set_last_tag_action(
            request,
            "paste",
            branch.id,
            {"tag_ids": created_ids},
        )
    messages.success(request, "Таблица меток вставлена!")
    return redirect("tags_list", branch_id=branch.id)


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)
def import_tags_csv(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)
    form = TagImportForm(request.POST, request.FILES)
    if not form.is_valid():
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
        return redirect("tags_list", branch_id=branch.id)


    uploaded = form.cleaned_data["file"]
    uploaded.seek(0)
    expected = TagImportForm.EXPECTED_COLUMNS


    try:
        decoded = uploaded.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        messages.error(request, "Файл не прочитан в UTF-8.")
        return redirect("tags_list", branch_id=branch.id)


    reader = csv.DictReader(io.StringIO(decoded))
    headers = [(h or "").strip() for h in (reader.fieldnames or [])]
    if headers != expected:
        messages.error(
            request,
            "Структура CSV не подходит. Нужны столбцы: "
            + ", ".join(expected),
        )
        return redirect("tags_list", branch_id=branch.id)


    created = 0
    created_ids = []
    try:
        with transaction.atomic():
            for row in reader:
                if not any((row.get(col) or "").strip() for col in expected):
                    continue
                tag_kwargs = {col: (row.get(col) or "").strip() or None for col in expected}
                new_tag = Tag.objects.create(branch=branch, **tag_kwargs)
                created += 1
                created_ids.append(new_tag.id)
    except csv.Error as exc:
        messages.error(request, f"Ошибка CSV: {exc}")
        return redirect("tags_list", branch_id=branch.id)
    except Exception as exc:
        messages.error(request, f"Ошибка при импорте: {exc}")
        return redirect("tags_list", branch_id=branch.id)


    if created_ids:
        _set_last_tag_action(
            request,
            "import",
            branch.id,
            {"tag_ids": created_ids},
        )
    if created:
        messages.success(request, f"Метки добавлены: {created}.")
    else:
        messages.warning(request, "Подходящих строк в файле не нашлось.")
    return redirect("tags_list", branch_id=branch.id)


@login_required
@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)
def duplicate_tag(request, tag_id):
    tag = get_object_or_404(Tag, id=tag_id, url__isnull=False)
    branch = tag.branch
    new_tag = Tag.objects.create(
        branch=branch,
        utm_source=tag.utm_source,
        utm_medium=tag.utm_medium,
        utm_campaign=tag.utm_campaign,
        utm_term=tag.utm_term,
        utm_content=tag.utm_content,
        budget=tag.budget,
    )
    _set_last_tag_action(
        request,
        "duplicate",
        branch.id,
        {"tag_ids": [new_tag.id]},
    )
    messages.success(request, f"Метка {new_tag.number} успешно создана как копия {tag.number}!")
    return redirect("tags_list", branch_id=branch.id)


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)
def delete_tag(request, tag_id):
    tag = get_object_or_404(Tag, id=tag_id, url__isnull=False)
    previous_tag_snapshot = _tag_snapshot(tag)
    branch_id = tag.branch_id
    tag_number = tag.number
    Tag.objects.filter(id=tag.id).update(**TAG_CLEAR_FIELDS)
    _set_last_tag_action(
        request,
        "delete",
        branch_id,
        {"tag_id": tag.id, "fields": previous_tag_snapshot},
    )
    messages.success(request, f"Метка {tag_number} удалена.")
    return redirect("tags_list", branch_id=branch_id)


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)
def undo_tags_action(request, branch_id):
    action = request.session.get(TAG_UNDO_SESSION_KEY)
    if not action or action.get("branch_id") != branch_id:
        messages.error(request, "Нет изменений для отмены.")
        return redirect("tags_list", branch_id=branch_id)
    payload = action.get("payload") or {}
    action_type = action.get("action")
    if action_type in {"edit", "delete"}:
        tag_id = payload.get("tag_id")
        fields = payload.get("fields") or {}
        if tag_id and fields:
            Tag.objects.filter(id=tag_id, branch_id=branch_id).update(**fields)
            messages.success(request, "Последнее изменение отменено.")
        else:
            messages.error(request, "Нет данных для отмены изменения.")
    elif action_type in {"create", "duplicate", "duplicate_all", "paste", "import"}:
        tag_ids = payload.get("tag_ids") or []
        if tag_ids:
            Tag.objects.filter(id__in=tag_ids, branch_id=branch_id).update(**TAG_CLEAR_FIELDS)
            messages.success(request, "Последнее действие отменено.")
        else:
            messages.error(request, "Нет данных для отмены действия.")
    else:
        messages.error(request, "Нет изменений для отмены.")
    request.session.pop(TAG_UNDO_SESSION_KEY, None)
    request.session.modified = True
    return redirect("tags_list", branch_id=branch_id)


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst')
def product_reports(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    plans = PlanMonthly.objects.filter(product=product).order_by("-month")
    reports = TrafficReport.objects.filter(product=product).order_by("-month")


    if request.method == "POST" and get_user_role(request.user) != 'analyst':
        month = request.POST.get("month")
        platform = request.POST.get("platform")
        vendor = request.POST.get("vendor")
        spend = request.POST.get("spend")
        clicks = request.POST.get("clicks")
        leads_warm = request.POST.get("leads_warm")
        leads_cold = request.POST.get("leads_cold")


        TrafficReport.objects.create(
            product=product,
            month=month,
            platform=platform,
            vendor=vendor,
            spend=spend or 0,
            clicks=clicks or 0,
            leads_warm=leads_warm or 0,
            leads_cold=leads_cold or 0,
        )
        messages.success(request, "Отчёт успешно добавлен.")
        return redirect("product_reports", product_id=product.id)


    return render(request, "marks/product_reports.html", {"product": product, "plans": plans, "reports": reports})


def _parse_filter_date(value):
    value = (value or "").strip()
    if not value:
        return None, ""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
        return parsed, value
    except ValueError:
        return None, ""


def _get_task_filter_values(request):
    task_type = (request.GET.get("task_type") or "").strip()
    task_status = (request.GET.get("task_status") or "").strip()
    bot_id = (request.GET.get("bot_id") or "").strip()
    completed_from, completed_from_raw = _parse_filter_date(request.GET.get("completed_from"))
    completed_to, completed_to_raw = _parse_filter_date(request.GET.get("completed_to"))

    if task_type not in TaskRequest.Type.values:
        task_type = ""
    if task_status not in TaskRequest.Status.values:
        task_status = ""
    if not bot_id.isdigit():
        bot_id = ""

    if completed_from and completed_to and completed_from > completed_to:
        completed_from, completed_to = completed_to, completed_from
        completed_from_raw, completed_to_raw = completed_to_raw, completed_from_raw

    return {
        "task_type": task_type,
        "task_status": task_status,
        "bot_id": bot_id,
        "completed_from": completed_from,
        "completed_to": completed_to,
        "completed_from_raw": completed_from_raw,
        "completed_to_raw": completed_to_raw,
    }


def _apply_task_filters(tasks_qs, filters):
    if filters["task_type"]:
        tasks_qs = tasks_qs.filter(task_type=filters["task_type"])
    if filters["task_status"]:
        tasks_qs = tasks_qs.filter(status=filters["task_status"])
    if filters["bot_id"]:
        tasks_qs = tasks_qs.filter(branches__bot_id=int(filters["bot_id"]))
    if filters["completed_from"]:
        tasks_qs = tasks_qs.filter(completed_at__date__gte=filters["completed_from"])
    if filters["completed_to"]:
        tasks_qs = tasks_qs.filter(completed_at__date__lte=filters["completed_to"])
    return tasks_qs.distinct()


def _build_task_filter_query(filters):
    params = {}
    if filters.get("task_type"):
        params["task_type"] = filters["task_type"]
    if filters.get("task_status"):
        params["task_status"] = filters["task_status"]
    if filters.get("bot_id"):
        params["bot_id"] = filters["bot_id"]
    if filters.get("completed_from_raw"):
        params["completed_from"] = filters["completed_from_raw"]
    if filters.get("completed_to_raw"):
        params["completed_to"] = filters["completed_to_raw"]
    return urlencode(params)


def _quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def _legacy_task_columns(table_name):
    if connection.vendor != "postgresql":
        return set()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                """,
                [table_name],
            )
            return {row[0] for row in cursor.fetchall()}
    except Exception:
        logger.exception("Failed to read legacy columns for table %s", table_name)
        return set()


def _set_legacy_task_notify_data(task_id, tg_username, wants_notify):
    tg_username = (tg_username or "").strip()
    table_name = TaskRequest._meta.db_table

    try:
        legacy_cols = _legacy_task_columns(table_name)
        if "tg_username" not in legacy_cols:
            return

        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {_quote_ident(table_name)} SET {_quote_ident('tg_username')} = %s WHERE id = %s",
                [tg_username if wants_notify else "", task_id],
            )
    except Exception:
        logger.exception("Failed to set legacy notify data (task_id=%s)", task_id)


def _get_legacy_task_notify_username(task_id):
    table_name = TaskRequest._meta.db_table
    try:
        legacy_cols = _legacy_task_columns(table_name)
        if "tg_username" not in legacy_cols:
            return ""
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT COALESCE({_quote_ident('tg_username')}, '') FROM {_quote_ident(table_name)} WHERE id = %s",
                [task_id],
            )
            row = cursor.fetchone()
            return (row[0] or "").strip() if row else ""
    except Exception:
        logger.exception("Failed to read legacy notify username (task_id=%s)", task_id)
        return ""


def _tasks_board_context(
    patch_form=None,
    mailing_form=None,
    build_form=None,
    tasks=None,
    filter_values=None,
    current_user=None,
):
    branch_options = list(Branch.objects.select_related("bot").order_by("bot__name", "name"))
    branch_total = len(branch_options)
    patch_form = patch_form or PatchTaskRequestForm(prefix="patch")
    mailing_form = mailing_form or MailingTaskRequestForm(prefix="mailing")
    build_form = build_form or BuildTaskRequestForm(prefix="build")

    patch_selected = set(str(v) for v in (patch_form["branches"].value() or []))
    mailing_selected = set(str(v) for v in (mailing_form["branches"].value() or []))
    build_selected = set(str(v) for v in (build_form["branches"].value() or []))

    if tasks is None:
        tasks = list(
            TaskRequest.objects.select_related("created_by").prefetch_related("branches__bot").order_by("-created_at")
        )
    else:
        tasks = list(tasks)

    filter_values = filter_values or {
        "task_type": "",
        "task_status": "",
        "bot_id": "",
        "completed_from": None,
        "completed_to": None,
        "completed_from_raw": "",
        "completed_to_raw": "",
    }

    bot_filter_options = list(Bot.objects.filter(branches__isnull=False).distinct().order_by("name"))
    completed_tasks_count = sum(1 for task in tasks if task.status == TaskRequest.Status.DONE and task.completed_at)
    done_tasks = [task for task in tasks if task.status == TaskRequest.Status.DONE and task.completed_at]
    completed_type_counters = {
        "build": sum(task.get_scope_units() for task in done_tasks if task.task_type == TaskRequest.Type.BUILD),
        "mailing": sum(task.get_scope_units() for task in done_tasks if task.task_type == TaskRequest.Type.MAILING),
        "patch": sum(task.get_scope_units() for task in done_tasks if task.task_type == TaskRequest.Type.PATCH),
    }

    columns = [
        {
            "status": TaskRequest.Status.UNREAD,
            "title": "Непрочитанное",
            "color": "secondary",
            "text": "text-white",
            "tasks": [],
        },
        {
            "status": TaskRequest.Status.IN_PROGRESS,
            "title": "В процессе",
            "color": "warning",
            "text": "text-dark",
            "tasks": [],
        },
        {
            "status": TaskRequest.Status.DONE,
            "title": "Готово",
            "color": "success",
            "text": "text-white",
            "tasks": [],
        },
    ]
    for task in tasks:
        for column in columns:
            if task.status == column["status"]:
                column["tasks"].append(task)
                break
    return {
        "patch_form": patch_form,
        "mailing_form": mailing_form,
        "build_form": build_form,
        "branch_options": branch_options,
        "patch_selected_branch_ids": patch_selected,
        "mailing_selected_branch_ids": mailing_selected,
        "build_selected_branch_ids": build_selected,
        "branch_total": branch_total,
        "task_type_choices": TaskRequest.Type.choices,
        "status_filter_choices": TaskRequest.Status.choices,
        "bot_filter_options": bot_filter_options,
        "filter_values": filter_values,
        "current_filter_query": _build_task_filter_query(filter_values),
        "completed_tasks_count": completed_tasks_count,
        "completed_type_counters": completed_type_counters,
        "kanban_columns": columns,
        "status_choices": TaskRequest.Status.choices,
        "show_kanban": user_is_admin(current_user) if current_user else False,
    }


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def tasks_board(request):
    filter_values = _get_task_filter_values(request)
    tasks_qs = TaskRequest.objects.select_related("created_by").prefetch_related("branches__bot").order_by("-created_at")
    filtered_tasks = _apply_task_filters(tasks_qs, filter_values)
    return render(
        request,
        "marks/tasks_board.html",
        _tasks_board_context(tasks=filtered_tasks, filter_values=filter_values, current_user=request.user),
    )


@login_required
@require_roles(UserProfile.Role.ADMIN)
def export_completed_tasks(request):
    filter_values = _get_task_filter_values(request)
    tasks_qs = TaskRequest.objects.select_related("created_by").prefetch_related("branches__bot").order_by("-completed_at")
    tasks_qs = _apply_task_filters(tasks_qs, filter_values).filter(
        status=TaskRequest.Status.DONE,
        completed_at__isnull=False,
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Выполненные задачи"
    ws.append([
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
    ])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    for task in tasks_qs:
        links = [value for value in [task.cjm_url, task.tz_url] if value]
        ws.append([
            task.id,
            task.get_task_type_display(),
            task.get_status_display(),
            task.created_by.username if task.created_by else "-",
            timezone.localtime(task.created_at).strftime("%d.%m.%Y %H:%M") if task.created_at else "-",
            timezone.localtime(task.deadline).strftime("%d.%m.%Y %H:%M") if task.deadline else "-",
            timezone.localtime(task.completed_at).strftime("%d.%m.%Y %H:%M") if task.completed_at else "-",
            task.comment or "",
            " | ".join(links),
            task.get_bot_branch_text(),
        ])

    for column_cells in ws.columns:
        max_len = max(len(str(c.value or "")) for c in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(max_len + 2, 70)

    period_parts = []
    if filter_values.get("completed_from_raw"):
        period_parts.append(f"from_{filter_values['completed_from_raw']}")
    if filter_values.get("completed_to_raw"):
        period_parts.append(f"to_{filter_values['completed_to_raw']}")
    suffix = "_".join(period_parts) if period_parts else "all"

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="completed_tasks_{suffix}.xlsx"'
    wb.save(response)
    return response


def _handle_task_create(request, form, success_message, invalid_form_key):
    try:
        is_valid = form.is_valid()
    except Exception:
        logger.exception(
            "Task form validation crashed (form=%s, user_id=%s)",
            form.__class__.__name__,
            getattr(request.user, "id", None),
        )
        messages.error(
            request,
            "Произошла внутренняя ошибка при проверке формы заявки.",
        )
        return redirect("tasks_board")

    if not is_valid:
        logger.warning(
            "Task form invalid (form=%s, fields=%s, user_id=%s)",
            form.__class__.__name__,
            ",".join(sorted(form.errors.keys())),
            getattr(request.user, "id", None),
        )
        messages.error(request, "Не удалось создать задачу. Проверьте заполнение полей.")
        forms_state = {
            "patch_form": PatchTaskRequestForm(prefix="patch"),
            "mailing_form": MailingTaskRequestForm(prefix="mailing"),
            "build_form": BuildTaskRequestForm(prefix="build"),
        }
        forms_state[invalid_form_key] = form
        try:
            return render(
                request,
                "marks/tasks_board.html",
                _tasks_board_context(current_user=request.user, **forms_state),
            )
        except Exception:
            logger.exception("Failed to render tasks board with invalid form")
            return redirect("tasks_board")

    try:
        with transaction.atomic():
            task = form.save(commit=False)
            task.created_by = request.user
            task.status = TaskRequest.Status.UNREAD
            task.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()
            wants_notify = bool(form.cleaned_data.get("notify_me"))
            tg_username = form.cleaned_data.get("tg_username") or ""
            _set_legacy_task_notify_data(
                task_id=task.id,
                tg_username=tg_username,
                wants_notify=wants_notify,
            )
    except Exception:
        logger.exception(
            "Failed to create task request (form=%s, user_id=%s)",
            form.__class__.__name__,
            getattr(request.user, "id", None),
        )
        messages.error(
            request,
            "Произошла внутренняя ошибка при создании заявки. Детали записаны в логах сервера.",
        )
        return redirect("tasks_board")

    notify_ok, notify_error = True, ""
    try:
        notify_result = notify_new_task(task)
        if isinstance(notify_result, tuple):
            notify_ok, notify_error = notify_result
        else:
            notify_ok, notify_error = bool(notify_result), ""
    except Exception:
        logger.exception("Failed to send new task notification (task_id=%s)", task.id)
        notify_ok, notify_error = False, "Сбой отправки уведомления."

    messages.success(request, success_message)
    if not notify_ok:
        messages.warning(
            request,
            "Задача создана, но уведомление в Telegram не отправлено. "
            + (notify_error or "Проверьте token/chat_id и перезапуск сервиса."),
        )
    return redirect("tasks_board")


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def create_patch_task(request):
    form = PatchTaskRequestForm(request.POST, prefix="patch")
    return _handle_task_create(
        request,
        form,
        "Заявка на правку создана.",
        "patch_form",
    )


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def create_mailing_task(request):
    form = MailingTaskRequestForm(request.POST, prefix="mailing")
    return _handle_task_create(
        request,
        form,
        "Заявка на рассылку создана.",
        "mailing_form",
    )


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def create_build_task(request):
    form = BuildTaskRequestForm(request.POST, prefix="build")
    return _handle_task_create(
        request,
        form,
        "Заявка на сборку бота создана.",
        "build_form",
    )


@login_required
@require_POST
@require_roles(UserProfile.Role.ADMIN)
def update_task_status(request, task_id):
    task = get_object_or_404(TaskRequest, id=task_id)
    old_status = task.status
    form = TaskStatusForm(request.POST, instance=task)
    if not form.is_valid():
        messages.error(request, "Не удалось обновить статус задачи.")
        return redirect("tasks_board")

    form.save()
    if old_status != task.status:
        notify_result = notify_status_change(task=task, old_status=old_status, changed_by=request.user)
        if isinstance(notify_result, tuple):
            notify_ok, notify_error = notify_result
        else:
            notify_ok, notify_error = bool(notify_result), ""
        user_notify_ok, user_notify_error = True, ""
        if task.status == TaskRequest.Status.DONE:
            tg_username = _get_legacy_task_notify_username(task.id)
            if tg_username:
                user_notify_result = notify_done_to_user(task=task, tg_username=tg_username)
                if isinstance(user_notify_result, tuple):
                    user_notify_ok, user_notify_error = user_notify_result
                else:
                    user_notify_ok, user_notify_error = bool(user_notify_result), ""
        messages.success(request, "Статус задачи обновлён.")
        if not notify_ok:
            messages.warning(
                request,
                "Статус обновлён, но уведомление в Telegram не отправлено. "
                + (notify_error or "Проверьте token/chat_id и перезапуск сервиса."),
            )
        if not user_notify_ok:
            messages.warning(
                request,
                "Задача отмечена как выполненная, но персональное уведомление не отправлено. "
                + (user_notify_error or "Проверьте username/chat_id в заявке."),
            )
    else:
        messages.info(request, "Статус не изменился.")
    return redirect("tasks_board")


@login_required
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def experiments_board(request):
    if request.method == "POST":
        form = ExperimentForm(request.POST)
        if form.is_valid():
            experiment = form.save(commit=False)
            experiment.created_by = request.user
            experiment.save()
            messages.success(request, "Эксперимент создан.")
            return redirect("experiments_board")
        messages.error(request, "Не удалось создать эксперимент. Проверьте заполнение полей.")
    else:
        form = ExperimentForm(initial={"status": Experiment.Status.BACKLOG})

    option_labels = dict(ExperimentForm.AB_TEST_OPTIONS)
    experiments = []
    for experiment in Experiment.objects.select_related("created_by").all():
        selected_options = experiment.ab_test_options or []
        experiments.append(
            {
                "item": experiment,
                "ab_option_labels": [option_labels.get(code, code) for code in selected_options],
            }
        )

    return render(
        request,
        "marks/experiments_board.html",
        {
            "form": form,
            "experiments": experiments,
            "status_choices": Experiment.Status.choices,
        },
    )


@login_required
@require_POST
@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)
def update_experiment_status(request, experiment_id):
    experiment = get_object_or_404(Experiment, id=experiment_id)
    status_value = (request.POST.get("status") or "").strip()
    if status_value not in Experiment.Status.values:
        messages.error(request, "Недопустимый статус эксперимента.")
        return redirect("experiments_board")

    if experiment.status == status_value:
        messages.info(request, "Статус эксперимента не изменился.")
        return redirect("experiments_board")

    experiment.status = status_value
    experiment.save(update_fields=["status", "updated_at"])
    messages.success(request, "Статус эксперимента обновлен.")
    return redirect("experiments_board")

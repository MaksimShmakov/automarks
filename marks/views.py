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


from django.db import transaction


from django.db.models import Sum, Count


from decimal import Decimal


import json


import csv


import io


import openpyxl


from openpyxl.styles import Font, Alignment


from reportlab.lib.pagesizes import A4


from reportlab.pdfgen import canvas





from .models import Bot, Branch, Tag, Product, PlanMonthly, Funnel, TrafficReport, PatchNote, UserProfile


from .forms import BotForm, BotStatusForm, BranchForm, TagForm, CustomUserCreationForm, TagImportForm


from .permissions import require_roles, BOT_OPERATORS_GROUP








                                    


def get_user_role(user):


    return getattr(getattr(user, "profile", None), "role", None)








def get_role_home_view_name(user):


    role = get_user_role(user)


    if role == UserProfile.Role.BOT_USER:


        return "bots_list"


    try:


        if user.is_authenticated and user.groups.filter(name=BOT_OPERATORS_GROUP).exists():


            return "bots_list"


    except Exception:


        pass


    return "dashboard"








class RoleAwareLoginView(LoginView):


    template_name = "registration/login.html"





    def get_success_url(self):


        return reverse(get_role_home_view_name(self.request.user))








                                                          


def is_admin(user):


    role = get_user_role(user)


    return bool(user.is_superuser or role == "admin")





def is_marketer(user):


    role = get_user_role(user)


    return role in {"manager", "marketer", "admin"}





def is_analyst(user):


    role = get_user_role(user)


    return role == "analyst"








                                      


def is_admin(user):


    return user.is_superuser or user.groups.filter(name="Администратор").exists()





def is_marketer(user):


    return user.groups.filter(name="Маркетолог").exists() or is_admin(user)





def is_analyst(user):


    return user.groups.filter(name="Аналитик").exists()








                                   


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
@require_roles('admin', 'manager', 'marketer', 'analyst')
def dashboard(request):
    selected_month = request.GET.get("month")
    selected_year = request.GET.get("year")
    now = datetime.now()
    month = int(selected_month) if selected_month else now.month
    year = int(selected_year) if selected_year else now.year

    dashboard_data = _get_dashboard_data(month, year)

    months = [(i, name) for i, name in enumerate(
        ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
         "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабр"], 1)]
    years = range(now.year - 3, now.year + 2)

    return render(request, "marks/dashboard.html", {
        "dashboard_data": dashboard_data,
        "months": months,
        "years": years,
        "selected_month": month,
        "selected_year": year,
    })










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


        "tag": {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"},


    }





    model = model_map.get(model_type)


    if not model:


        return JsonResponse({"error": "Недопустимая модель"}, status=400)


    if field not in allowed_fields.get(model_type, set()):


        return JsonResponse({"error": "Поле недоступно"}, status=400)





    try:


        obj = model.objects.get(id=record_id)


        model_field = obj._meta.get_field(field)


        itype = model_field.get_internal_type()





        def to_bool(v):


            if isinstance(v, bool):


                return v


            return str(v).lower() in {"1", "true", "yes", "on"}





        if itype in {"DecimalField"}:


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


    tags = list(branch.tags.all())


    total_created = 0





    for _ in range(count):


        for tag in tags:


            Tag.objects.create(


                branch=branch,


                utm_source=tag.utm_source,


                utm_medium=tag.utm_medium,


                utm_campaign=tag.utm_campaign,


                utm_term=tag.utm_term,


                utm_content=tag.utm_content,


            )


            total_created += 1





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


        tags_qs = branch.tags.all()


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


@require_roles('admin', UserProfile.Role.BOT_USER)


def bots_list(request):


    bots = Bot.objects.all().annotate(branches_total=Count("branches"))


    active_bots = bots.filter(is_active=True).order_by("name")


    inactive_bots = bots.filter(is_active=False).order_by("name")


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


    form = BranchForm()


    if request.method == "POST":


        if request.POST.get("form_type") == "bot_status":


            bot_status_form = BotStatusForm(request.POST, bot=bot)


            if bot_status_form.is_valid():


                bot_status_form.save()


                messages.success(request, "Статус бота обновлён")


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


        },


    )








                             


@login_required


@require_roles('admin', 'manager', 'marketer', 'analyst', UserProfile.Role.BOT_USER)


def tags_list(request, branch_id):


    branch = get_object_or_404(Branch, id=branch_id)


    tags = branch.tags.all()


    patchnotes = branch.patch_notes.all()


    has_copied = bool(request.session.get("copied_tags"))





    if request.method == "POST" and "create_tag" in request.POST:


        if get_user_role(request.user) != 'analyst':


            form = TagForm(request.POST)


            if form.is_valid():


                tag = form.save(commit=False)


                tag.branch = branch


                tag.save()


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


    tag = get_object_or_404(Tag, id=tag_id)


    form = TagForm(request.POST, instance=tag)


    if form.is_valid():


        form.save()


        messages.success(request, f"Метка {tag.number} обновлена")


    else:


        messages.error(request, "Ошибка при обновлении метки")


    return redirect("tags_list", branch_id=tag.branch.id)








                                             


@login_required


@require_POST


@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)


def copy_tags(request, branch_id):


    branch = get_object_or_404(Branch, id=branch_id)


    request.session["copied_tags"] = list(branch.tags.values(


        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"


    ))


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


    for tag_data in copied_tags:


        Tag.objects.create(branch=branch, **tag_data)


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


    try:


        with transaction.atomic():


            for row in reader:


                if not any((row.get(col) or "").strip() for col in expected):


                    continue


                tag_kwargs = {


                    col: (row.get(col) or "").strip() or None


                    for col in expected


                }


                Tag.objects.create(branch=branch, **tag_kwargs)


                created += 1


    except csv.Error as exc:


        messages.error(request, f"Ошибка CSV: {exc}")


        return redirect("tags_list", branch_id=branch.id)


    except Exception as exc:


        messages.error(request, f"Ошибка при импорте: {exc}")


        return redirect("tags_list", branch_id=branch.id)





    if created:


        messages.success(request, f"Метки добавлены: {created}.")


    else:


        messages.warning(request, "Подходящих строк в файле не нашлось.")


    return redirect("tags_list", branch_id=branch.id)





                                              


@login_required


@require_roles('admin', 'manager', 'marketer', UserProfile.Role.BOT_USER)


def duplicate_tag(request, tag_id):


    tag = get_object_or_404(Tag, id=tag_id)


    branch = tag.branch


    new_tag = Tag.objects.create(


        branch=branch,


        utm_source=tag.utm_source,


        utm_medium=tag.utm_medium,


        utm_campaign=tag.utm_campaign,


        utm_term=tag.utm_term,


        utm_content=tag.utm_content,


    )


    messages.success(request, f"Метка {new_tag.number} успешно создана как копия {tag.number}!")


    return redirect("tags_list", branch_id=branch.id)








                              


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
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Product, PlanMonthly, Funnel, TrafficReport, PatchNote, Bot, Branch
from .forms import ProductForm, PlanMonthlyForm, FunnelForm, FunnelMasterForm, TrafficReportForm, PatchNoteForm
from .permissions import require_roles
from .models import UserProfile

@login_required
@require_roles(UserProfile.Role.ADMIN, UserProfile.Role.MANAGER)
def products_list(request):
    products = Product.objects.order_by("-created_at")
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Продукт создан")
            return redirect("products_list")
    else:
        form = ProductForm()
    return render(request, "marks/products_list.html", {"products": products, "form": form})

@login_required
def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    plans = product.plans.all()[:12]
    funnels = product.funnels.all()
    bots = product.bots.all()
    traffic = product.traffic_reports.all()[:12]
    return render(request, "marks/product_detail.html", {
        "product": product,
        "plans": plans,
        "funnels": funnels,
        "bots": bots,
        "traffic": traffic,
    })

@login_required
@require_roles(UserProfile.Role.ADMIN, UserProfile.Role.MANAGER)
def plan_create(request):
    if request.method == "POST":
        form = PlanMonthlyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "План сохранён")
            return redirect("product_detail", product_id=form.cleaned_data["product"].id)
    else:
        form = PlanMonthlyForm()
    return render(request, "marks/plan_form.html", {"form": form})

@login_required
@require_roles(UserProfile.Role.ADMIN, UserProfile.Role.MANAGER)
def funnel_create(request):
    if request.method == "POST":
        form = FunnelForm(request.POST)
        if form.is_valid():
            funnel = form.save()
            messages.success(request, "Воронка создана")
            return redirect("product_detail", product_id=funnel.product.id)
    else:
        form = FunnelForm()
    return render(request, "marks/funnel_form.html", {"form": form})

@login_required
@require_roles(UserProfile.Role.ADMIN, UserProfile.Role.MANAGER)
def traffic_report_create(request):
    if request.method == "POST":
        form = TrafficReportForm(request.POST)
        if form.is_valid():
            tr = form.save()
            messages.success(request, "Отчёт по трафику добавлен")
            return redirect("product_detail", product_id=tr.product.id)
    else:
        form = TrafficReportForm()
    return render(request, "marks/traffic_form.html", {"form": form})

@login_required
def patchnote_create(request):
    bot_id = request.GET.get("bot_id") or request.POST.get("bot_id")
    branch_id = request.GET.get("branch_id") or request.POST.get("branch_id")
    next_url = request.GET.get("next") or request.POST.get("next")

    branches_qs = Branch.objects.all()
    initial = {"created_at": timezone.localdate()}

    if bot_id:
        bot = get_object_or_404(Bot, id=bot_id)
        branches_qs = bot.branches.all()

    if branch_id:
        branch = get_object_or_404(Branch, id=branch_id)
        branches_qs = branches_qs.filter(id=branch.id)
        initial["branches"] = [branch]

    if request.method == "POST":
        form = PatchNoteForm(request.POST, branches=branches_qs)
        if form.is_valid():
            text = form.cleaned_data["text"].strip()
            created_date = form.cleaned_data["created_at"]
            created_at = timezone.now().replace(
                year=created_date.year,
                month=created_date.month,
                day=created_date.day,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            title = text.splitlines()[0][:80] if text else "Patch note"
            created = 0
            for branch in form.cleaned_data["branches"]:
                pn = PatchNote.objects.create(
                    branch=branch,
                    created_by=request.user,
                    title=title,
                    change_description=text,
                )
                if pn.created_at != created_at:
                    pn.created_at = created_at
                    pn.save(update_fields=["created_at"])
                created += 1
            messages.success(request, f"Patch notes created: {created}.")
            if next_url:
                return redirect(next_url)
            if branch_id:
                return redirect("tags_list", branch_id=branch_id)
            if bot_id:
                return redirect("branches_list", bot_id=bot_id)
            return redirect("bots_list")
    else:
        form = PatchNoteForm(branches=branches_qs, initial=initial)
    return render(
        request,
        "marks/patch_form.html",
        {"form": form, "bot_id": bot_id, "branch_id": branch_id, "next": next_url},
    )

@login_required
@require_roles(UserProfile.Role.ADMIN, UserProfile.Role.MANAGER)
def funnel_master_create(request):
    if request.method == "POST":
        form = FunnelMasterForm(request.POST)
        if form.is_valid():
            t = form.cleaned_data["type"]
            product = form.cleaned_data["product"]
            name = form.cleaned_data["name"]
            description = form.cleaned_data.get("description")
            is_active = form.cleaned_data.get("is_active") or False

            if t == "bot":
                from .models import Bot
                bot = Bot.objects.create(name=name, product=product)
                messages.success(request, "Бот создан")
                return redirect("branches_list", bot_id=bot.id)
            else:
                funnel = Funnel.objects.create(
                    product=product,
                    name=name,
                    description=description or "",
                    is_active=is_active,
                )
                messages.success(request, "Воронка создана")
                return redirect("product_detail", product_id=funnel.product.id)
    else:
        form = FunnelMasterForm()
    return render(request, "marks/funnel_form.html", {"form": form})

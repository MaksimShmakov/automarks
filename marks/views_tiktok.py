"""Раздел «TikTok-воронки» — порт вьюх сервиса el-tiktok-funnels-auto.

Три экрана:
- Заявка (login) — маркетолог создаёт черновик воронки;
- Дев-панель (login + токен-гейт) — редактируемая таблица воронок, активация,
  генерация скрипта/UTM-ссылки, ретрай синка, архив;
- Кабинеты (login + токен-гейт) — CRUD рекламных кабинетов TikTok (токены).

Токен-гейт (один общий токен на Дев-панель + Кабинеты) держится в сессии —
это server-side аналог X-Dev-Token из standalone-сервиса.
"""

from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import TikTokAccountForm, TikTokFunnelIntakeForm
from .models import TikTokAccount, TikTokFunnelRequest
from .services.landing_templates import render_landing_script, render_utm_link
from .services.telegram import notify_new_tiktok_funnel
from .services.tiktok_sync import sync_account, sync_funnel

SESSION_KEY = "funnels_unlocked"

# Поля воронки, редактируемые в дев-панели (инлайн).
EDITABLE_FIELDS = [
    "landing_endpoint",
    "offer",
    "bot_url",
    "page_type",
    "pixel_code",
    "account_no",
    "utm_source",
    "utm_medium",
    "utm_term",
    "comment",
    "status",
]


# --- Токен-гейт --------------------------------------------------------------


def require_funnels_token(view):
    """Пускает, только если в сессии стоит флаг разблокировки токеном.

    Иначе редирект на страницу ввода токена с ?next=. Предполагает, что
    аутентификация уже проверена (ставить под @login_required).
    """

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if request.session.get(SESSION_KEY):
            return view(request, *args, **kwargs)
        return redirect(f"{reverse('tiktok_unlock')}?next={request.path}")

    return _wrapped


@login_required
def tiktok_unlock(request):
    configured = (getattr(settings, "FUNNELS_DEV_TOKEN", "") or "").strip()
    next_url = request.POST.get("next") or request.GET.get("next") or reverse("tiktok_panel")
    if request.method == "POST":
        if not configured:
            messages.error(request, "FUNNELS_DEV_TOKEN не настроен на сервере — доступ закрыт.")
        elif (request.POST.get("token") or "").strip() == configured:
            request.session[SESSION_KEY] = True
            request.session.modified = True
            return redirect(next_url)
        else:
            messages.error(request, "Неверный токен.")
    return render(request, "marks/tiktok_unlock.html", {"next": next_url})


# --- Заявка (login) ----------------------------------------------------------


@login_required
def tiktok_apply(request):
    if request.method == "POST":
        form = TikTokFunnelIntakeForm(request.POST)
        if form.is_valid():
            funnel = form.save(commit=False)
            funnel.landing_endpoint = (
                TikTokFunnelRequest.normalize_endpoint(funnel.landing_endpoint) or None
            )
            funnel.bot_name = TikTokFunnelRequest.parse_bot_name(funnel.bot_url)
            funnel.created_by = request.user
            funnel.status = TikTokFunnelRequest.Status.PENDING
            try:
                funnel.save()
            except IntegrityError:
                messages.error(
                    request,
                    f"Воронка на этот эндпоинт уже существует: {funnel.landing_endpoint}",
                )
                return render(request, "marks/tiktok_apply.html", {"form": form})

            funnel.warehouse_synced = sync_funnel(funnel)
            funnel.save(update_fields=["warehouse_synced"])
            notify_new_tiktok_funnel(funnel)
            messages.success(request, "Заявка на воронку создана.")
            return redirect("tiktok_apply")
    else:
        form = TikTokFunnelIntakeForm()
    return render(request, "marks/tiktok_apply.html", {"form": form})


# --- Дев-панель (login + токен) ----------------------------------------------


@login_required
@require_funnels_token
def tiktok_panel(request):
    hide_archived = request.GET.get("archived") != "1"
    funnels = TikTokFunnelRequest.objects.select_related("created_by")
    if hide_archived:
        funnels = funnels.exclude(status=TikTokFunnelRequest.Status.ARCHIVED)
    accounts = set(TikTokAccount.objects.values_list("account_no", flat=True))
    return render(
        request,
        "marks/tiktok_panel.html",
        {
            "funnels": list(funnels),
            "page_types": TikTokFunnelRequest.PageType.choices,
            "statuses": TikTokFunnelRequest.Status.choices,
            "known_accounts": accounts,
            "hide_archived": hide_archived,
        },
    )


@login_required
@require_funnels_token
@require_POST
def tiktok_funnel_update(request, funnel_id):
    funnel = get_object_or_404(TikTokFunnelRequest, id=funnel_id)

    data = {f: (request.POST.get(f, "") or "").strip() for f in EDITABLE_FIELDS if f in request.POST}

    # Чекбокс: галка присылается в POST только когда включена → присутствие = значение.
    new_export_ready = "salebot_export_ready" in request.POST

    new_status = data.get("status", funnel.status)
    target_account = data.get("account_no", funnel.account_no)

    # Guard: в active только если экспорт в Salebot достроен И задан/заведён кабинет
    # (иначе воронка «активна», но события/конверсии не пойдут).
    if new_status == TikTokFunnelRequest.Status.ACTIVE:
        if not new_export_ready:
            messages.error(
                request,
                f"#{funnel.id}: нельзя активировать — не отмечено «В сейлботе достроен экспорт».",
            )
            return redirect("tiktok_panel")
        if not target_account:
            messages.error(request, f"#{funnel.id}: нельзя активировать без account_no.")
            return redirect("tiktok_panel")
        if not TikTokAccount.objects.filter(account_no=target_account).exists():
            messages.error(
                request,
                f"#{funnel.id}: кабинет №{target_account} не заведён — добавьте его в «Кабинеты».",
            )
            return redirect("tiktok_panel")

    funnel.salebot_export_ready = new_export_ready

    if "landing_endpoint" in data:
        funnel.landing_endpoint = TikTokFunnelRequest.normalize_endpoint(data.pop("landing_endpoint")) or None
    if "bot_url" in data:
        funnel.bot_url = data.pop("bot_url")
        funnel.bot_name = TikTokFunnelRequest.parse_bot_name(funnel.bot_url)

    for field, value in data.items():
        setattr(funnel, field, value)

    try:
        funnel.save()
    except IntegrityError:
        messages.error(request, f"#{funnel.id}: эндпоинт уже занят другой воронкой.")
        return redirect("tiktok_panel")

    funnel.warehouse_synced = sync_funnel(funnel)
    funnel.save(update_fields=["warehouse_synced"])
    messages.success(request, f"#{funnel.id}: сохранено.")
    return redirect("tiktok_panel")


@login_required
@require_funnels_token
@require_POST
def tiktok_funnel_sync(request, funnel_id):
    funnel = get_object_or_404(TikTokFunnelRequest, id=funnel_id)
    funnel.warehouse_synced = sync_funnel(funnel)
    funnel.save(update_fields=["warehouse_synced"])
    if funnel.warehouse_synced:
        messages.success(request, f"#{funnel.id}: записана в склад.")
    else:
        messages.warning(request, f"#{funnel.id}: не удалось записать в склад (см. логи / N8N_SYNC_URL).")
    return redirect("tiktok_panel")


@login_required
@require_funnels_token
def tiktok_funnel_script(request, funnel_id):
    funnel = get_object_or_404(TikTokFunnelRequest, id=funnel_id)
    if not (funnel.landing_endpoint and funnel.pixel_code and funnel.page_type):
        messages.error(request, f"#{funnel.id}: для скрипта нужны landing_endpoint, pixel_code и page_type.")
        return redirect("tiktok_panel")
    script = render_landing_script(
        page_type=funnel.page_type,
        offer=funnel.offer,
        bot_url=funnel.bot_url,
        bot_name=funnel.bot_name,
        pixel_code=funnel.pixel_code,
        ym_counter_id=getattr(settings, "YM_COUNTER_ID", ""),
        webhook_url=getattr(settings, "WEBHOOK_URL", ""),
        webhook_token=getattr(settings, "WEBHOOK_TOKEN", ""),
    )
    return render(request, "marks/tiktok_script.html", {"funnel": funnel, "script": script})


@login_required
@require_funnels_token
def tiktok_funnel_utm(request, funnel_id):
    funnel = get_object_or_404(TikTokFunnelRequest, id=funnel_id)
    if not funnel.landing_endpoint:
        messages.error(request, f"#{funnel.id}: сначала укажите landing_endpoint.")
        return redirect("tiktok_panel")
    url = render_utm_link(
        base_url=getattr(settings, "LANDING_BASE_URL", "https://go-egeland.ru"),
        landing_endpoint=funnel.landing_endpoint,
        utm_source=funnel.utm_source,
        utm_medium=funnel.utm_medium,
        utm_term=funnel.utm_term,
    )
    return render(request, "marks/tiktok_utm.html", {"funnel": funnel, "url": url})


# --- Кабинеты (login + токен) ------------------------------------------------


@login_required
@require_funnels_token
def tiktok_accounts(request):
    if request.method == "POST":
        form = TikTokAccountForm(request.POST)
        if form.is_valid():
            account = form.save()
            synced = sync_account(account)
            if synced:
                messages.success(request, f"Кабинет №{account.account_no} сохранён и записан в склад.")
            else:
                messages.warning(request, f"Кабинет №{account.account_no} сохранён, но не записан в склад.")
            return redirect("tiktok_accounts")
    else:
        form = TikTokAccountForm()
    return render(
        request,
        "marks/tiktok_accounts.html",
        {"accounts": list(TikTokAccount.objects.all()), "form": form},
    )


@login_required
@require_funnels_token
@require_POST
def tiktok_account_update(request, account_no):
    account = get_object_or_404(TikTokAccount, account_no=account_no)
    account.advertiser_id = (request.POST.get("advertiser_id", "") or "").strip()
    account.access_token = (request.POST.get("access_token", account.access_token) or "").strip()
    account.note = (request.POST.get("note", "") or "").strip()
    account.save()
    synced = sync_account(account)
    if synced:
        messages.success(request, f"Кабинет №{account.account_no} обновлён и записан в склад.")
    else:
        messages.warning(request, f"Кабинет №{account.account_no} обновлён, но не записан в склад.")
    return redirect("tiktok_accounts")


@login_required
@require_funnels_token
@require_POST
def tiktok_account_delete(request, account_no):
    account = get_object_or_404(TikTokAccount, account_no=account_no)
    account.delete()
    messages.success(
        request,
        f"Кабинет №{account_no} удалён из automarks (строка в складе tiktok_accounts остаётся — уберите вручную при необходимости).",
    )
    return redirect("tiktok_accounts")

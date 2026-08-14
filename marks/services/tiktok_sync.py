"""Синхронный dual-write воронок/кабинетов в удалённый склад через n8n.

Порт из el-tiktok-funnels-auto/backend/app/n8n_sync.py. automarks в склад
напрямую НЕ пишет — он POST-ит JSON в вебхук n8n `funnel-sync`, а n8n делает
upsert в activation_data.tt_funnels / tiktok_accounts (см. n8n/v2/funnels-writer).

Возвращает bool «долетело ли». Никогда не бросает наружу: сеть/склад могут
лежать, а UI не должен падать — воронка сохраняется в БД automarks, флаг
warehouse_synced=False и кнопка ретрая в дев-панели.
"""

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 10


def _none(value):
    """Пустую строку → None (чтобы в складе был NULL, а не ''): важно для account_no,
    иначе CAPI-JOIN a.account_no = f.account_no сматчит «пустой» кабинет."""
    value = (value or "").strip() if isinstance(value, str) else value
    return value or None


def _post(payload):
    url = (getattr(settings, "N8N_SYNC_URL", "") or "").strip()
    if not url:
        logger.info("N8N_SYNC_URL не задан — синк в склад пропущен (payload=%s)", payload.get("type"))
        return False
    headers = {"Content-Type": "application/json"}
    token = (getattr(settings, "N8N_SYNC_TOKEN", "") or "").strip()
    if token:
        headers["Authorization"] = token
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Синк в склад через n8n не удался (type=%s): %s", payload.get("type"), exc)
        return False


def sync_funnel(funnel):
    """POST строки воронки в n8n. Без landing_endpoint upsert невозможен (склад
    конфликтит по landing_endpoint) — тогда синк пропускаем."""
    if not funnel.landing_endpoint:
        return False
    payload = {
        "type": "funnel",
        "landing_endpoint": funnel.landing_endpoint,
        "offer": _none(funnel.offer),
        "bot_url": _none(funnel.bot_url),
        "bot_name": _none(funnel.bot_name),
        "page_type": _none(funnel.page_type),
        "pixel_code": _none(funnel.pixel_code),
        "account_no": _none(funnel.account_no),
        "utm_source": _none(funnel.utm_source),
        "utm_medium": _none(funnel.utm_medium),
        "utm_term": _none(funnel.utm_term),
        "status": funnel.status,
    }
    return _post(payload)


def sync_account(account):
    """POST кабинета в n8n (upsert в tiktok_accounts по account_no)."""
    payload = {
        "type": "account",
        "account_no": account.account_no,
        "advertiser_id": _none(account.advertiser_id),
        "access_token": account.access_token,
        "note": _none(account.note),
    }
    return _post(payload)

# app/routers/routes_provider.py
from fastapi import APIRouter, HTTPException, Query
import os
import httpx
import re

router = APIRouter(prefix="/api/provider", tags=["provider"])

PROVIDER_URL = os.getenv("SMM_API_URL", "").strip().rstrip("/")
PROVIDER_KEY = os.getenv("SMM_API_KEY", "").strip()


def _ensure_config():
    if not PROVIDER_URL or not PROVIDER_KEY:
        raise HTTPException(
            status_code=500,
            detail="Provider API is not configured. Set SMM_API_URL and SMM_API_KEY on Heroku."
        )


async def _call_provider(action: str, extra: dict | None = None):
    """
    يستدعي KD1S وفق وثائق /api/v2 عبر POST form-data:
      key=<API KEY>, action=<action>, ...extra
    """
    _ensure_config()
    payload = {"key": PROVIDER_KEY, "action": action}
    if extra:
        payload.update(extra)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                PROVIDER_URL,
                data=payload,                      # مهم: form-data وليس JSON
                headers={"Accept": "application/json"}
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Provider connection error: {e!s}")

    raw = r.text
    # نحاول JSON أولاً
    try:
        j = r.json()
        return j, raw
    except Exception:
        # بعض اللوحات قد ترجع نصاً بسيطاً؛ نعيده كـ raw
        return None, raw


@router.get("/balance")
async def provider_balance():
    """
    يعيد: {"balance": "...", "currency": "...", "provider_raw": "..."}
    مطابق لوثائق KD1S (action=balance)
    """
    j, raw = await _call_provider("balance")
    if j:
        return {
            "balance": j.get("balance"),
            "currency": j.get("currency"),
            "provider_raw": raw
        }

    # fallback parsing لو عاد نص
    low = raw.lower()
    bal = None
    cur = None
    m = re.search(r"balance[^0-9]*([0-9]+(?:\.[0-9]+)?)", low)
    if m:
        bal = m.group(1)
    m2 = re.search(r"\b(usd|eur|try|sar|iqd)\b", low)
    if m2:
        cur = m2.group(1).upper()

    if bal:
        return {"balance": bal, "currency": cur, "provider_raw": raw}

    raise HTTPException(
        status_code=502,
        detail="Unexpected provider response for balance",
        headers={"x-provider-raw": raw[:200]}
    )


@router.get("/order/status")
async def provider_order_status(order_id: str = Query(..., alias="order_id")):
    """
    يعيد: {"ok": true, "data": {...}, "provider_raw": "..."}
    يأخذ رقم الطلب عبر ?order_id=123  ويستدعي KD1S (action=status, order=<id>)
    """
    j, raw = await _call_provider("status", {"order": order_id})
    if j:
        return {"ok": True, "data": j, "provider_raw": raw}

    raise HTTPException(
        status_code=502,
        detail="Unexpected provider response for status",
        headers={"x-provider-raw": raw[:200]}
    )


@router.get("/services")
async def provider_services():
    """
    يعيد قائمة الخدمات من KD1S (action=services)
    """
    j, raw = await _call_provider("services")
    if j:
        return {"ok": True, "services": j, "provider_raw": raw}

    raise HTTPException(
        status_code=502,
        detail="Unexpected provider response for services",
        headers={"x-provider-raw": raw[:200]}
        )

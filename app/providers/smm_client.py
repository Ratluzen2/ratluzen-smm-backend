# app/providers/smm_client.py
import httpx
from typing import Dict, Any
from ..config import settings

TIMEOUT = 15.0

def _base_params() -> Dict[str, Any]:
    return {
        "key": settings.PROVIDER_API_KEY or "",
    }

def provider_add_order(service_id: int, link: str, quantity: int) -> Dict[str, Any]:
    """
    يرسل الطلب إلى مزود SMM قياسي:
    params: key, action=add, service, link, quantity
    """
    if not settings.PROVIDER_API_URL or not settings.PROVIDER_API_KEY:
        return {"ok": False, "error": "provider not configured (set PROVIDER_API_URL & PROVIDER_API_KEY)"}
    url = settings.PROVIDER_API_URL
    params = _base_params()
    params.update({
        "action": "add",
        "service": int(service_id),
        "link": link,
        "quantity": int(quantity),
    })
    try:
        r = httpx.post(url, data=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json() if "application/json" in r.headers.get("Content-Type", "") else {}
        # بعض الـ panels ترجع {"order": 12345}
        oid = data.get("order") or data.get("orderId") or data.get("id")
        if oid:
            return {"ok": True, "orderId": str(oid)}
        # لو لم يكن JSON واضحًا، جرّب قراءة النص
        txt = r.text.strip()
        if txt.isdigit():
            return {"ok": True, "orderId": txt}
        return {"ok": False, "error": data.get("error") or "unknown provider response"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def provider_balance() -> Dict[str, Any]:
    if not settings.PROVIDER_API_URL or not settings.PROVIDER_API_KEY:
        return {"ok": False, "error": "provider not configured"}
    url = settings.PROVIDER_API_URL
    params = _base_params()
    params.update({"action": "balance"})
    try:
        r = httpx.post(url, data=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json() if "application/json" in r.headers.get("Content-Type", "") else {}
        bal = data.get("balance") or (data.get("data") or {}).get("balance")
        if bal is not None:
            return {"ok": True, "balance": float(bal)}
        return {"ok": False, "error": data.get("error") or "unknown provider response"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def provider_status(order_id: str) -> Dict[str, Any]:
    if not settings.PROVIDER_API_URL or not settings.PROVIDER_API_KEY:
        return {"ok": False, "error": "provider not configured"}
    url = settings.PROVIDER_API_URL
    params = _base_params()
    params.update({"action": "status", "order": str(order_id)})
    try:
        r = httpx.post(url, data=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json() if "application/json" in r.headers.get("Content-Type", "") else {}
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}

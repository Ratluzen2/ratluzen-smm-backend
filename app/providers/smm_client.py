import httpx
from ..config import settings

def _err(msg: str):
    return {"ok": False, "error": msg}

def provider_balance():
    if not settings.PROVIDER_BASE_URL or not settings.PROVIDER_KEY:
        return _err("provider not configured")
    try:
        r = httpx.get(
            f"{settings.PROVIDER_BASE_URL}/balance",
            params={"key": settings.PROVIDER_KEY},
            timeout=10.0,
        )
        return {"ok": True, "raw": r.json()}
    except Exception as e:
        return _err(str(e))

def provider_status(order_id: str):
    if not settings.PROVIDER_BASE_URL or not settings.PROVIDER_KEY:
        return _err("provider not configured")
    try:
        r = httpx.get(
            f"{settings.PROVIDER_BASE_URL}/status",
            params={"key": settings.PROVIDER_KEY, "order": order_id},
            timeout=10.0,
        )
        return {"ok": True, "raw": r.json()}
    except Exception as e:
        return _err(str(e))

def provider_add_order(service_key: str, link: str, qty: int):
    if not settings.PROVIDER_BASE_URL or not settings.PROVIDER_KEY:
        return _err("provider not configured")
    try:
        r = httpx.post(
            f"{settings.PROVIDER_BASE_URL}/order",
            json={"key": settings.PROVIDER_KEY, "service": service_key, "link": link, "quantity": qty},
            timeout=15.0,
        )
        j = r.json()
        if r.status_code >= 400:
            return _err(j.get("error", "provider error"))
        # عدل حسب هيكل مزودك
        return {"ok": True, "orderId": str(j.get("order") or j.get("order_id") or j.get("id"))}
    except Exception as e:
        return _err(str(e))

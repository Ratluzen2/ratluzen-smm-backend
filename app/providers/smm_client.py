import httpx
from ..config import settings
from ..provider_map import SERVICE_MAP

TIMEOUT = httpx.Timeout(12.0)

def _base_payload() -> dict:
    if not settings.SMM_API_URL or not settings.SMM_API_KEY:
        raise RuntimeError("SMM_API_URL / SMM_API_KEY not set")
    return {"key": settings.SMM_API_KEY}

def provider_add_order(service_key: str, link: str, quantity: int) -> dict:
    service = SERVICE_MAP.get(service_key)
    if not service:
        return {"ok": False, "error": "unknown service key"}
    payload = _base_payload() | {
        "action": "add",
        "service": service,
        "link": link,
        "quantity": quantity,
    }
    try:
        r = httpx.post(settings.SMM_API_URL, data=payload, timeout=TIMEOUT)
        data = r.json()
        if "order" in data:
            return {"ok": True, "orderId": str(data["order"])}
        return {"ok": False, "error": data.get("error") or "provider error"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def provider_balance() -> dict:
    try:
        r = httpx.post(settings.SMM_API_URL, data=_base_payload() | {"action": "balance"}, timeout=TIMEOUT)
        data = r.json()
        return {"ok": True, "balance": data.get("balance"), "currency": data.get("currency")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def provider_status(order_id: str) -> dict:
    try:
        r = httpx.post(settings.SMM_API_URL, data=_base_payload() | {"action": "status", "order": order_id}, timeout=TIMEOUT)
        return {"ok": True, "data": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

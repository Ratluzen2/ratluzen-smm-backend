import httpx
from .config import settings

def _api_post(payload: dict) -> dict:
    data = {"key": settings.KD1S_API_KEY, **payload}
    try:
        r = httpx.post(settings.KD1S_API_URL, data=data, timeout=15.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def provider_balance() -> dict:
    res = _api_post({"action": "balance"})
    if "error" in res:
        return {"ok": False, "error": res["error"]}
    # صيغ SMM الشائعة: {"balance":"12.34","currency":"USD"}
    try:
        bal = float(res.get("balance", 0))
    except Exception:
        bal = 0.0
    return {"ok": True, "balance": bal, "raw": res}

def provider_add_order(service_id: int, link: str, quantity: int) -> dict:
    res = _api_post({"action": "add", "service": service_id, "link": link, "quantity": quantity})
    # {"order":123456} أو {"error": "..."}
    if "error" in res:
        return {"ok": False, "error": res["error"]}
    oid = str(res.get("order") or res.get("order_id") or "")
    if not oid:
        return {"ok": False, "error": "no order id"}
    return {"ok": True, "orderId": oid, "raw": res}

def provider_status(order_id: str) -> dict:
    res = _api_post({"action": "status", "order": order_id})
    if "error" in res:
        return {"ok": False, "error": res["error"]}
    return {"ok": True, "raw": res}

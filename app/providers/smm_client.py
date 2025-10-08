import os
import httpx

KD1S_BASE = os.getenv("KD1S_BASE", "https://kd1s.com/api/v2").rstrip("/")
KD1S_KEY  = os.getenv("KD1S_API_KEY", "").strip()

def _ensure_key():
    if not KD1S_KEY:
        return {"ok": False, "error": "KD1S_API_KEY not set"}
    return None

def _post(data: dict, timeout: float = 20.0):
    miss = _ensure_key()
    if miss:
        return miss
    payload = {"key": KD1S_KEY}
    payload.update(data)
    try:
        r = httpx.post(KD1S_BASE, data=payload, timeout=timeout)
        r.raise_for_status()
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text}
        return {"ok": True, "data": j}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"http error: {e}"}

def provider_balance():
    return _post({"action": "balance"})

def provider_services():
    return _post({"action": "services"})

def provider_add_order(service_id: int, link: str, quantity: int, **extra):
    data = {
        "action": "add",
        "service": int(service_id),
        "link": link,
        "quantity": int(quantity),
    }
    data.update({k: v for k, v in extra.items() if v is not None})
    res = _post(data)
    if not res["ok"]:
        return res
    j = res["data"]
    if isinstance(j, dict) and "order" in j:
        return {"ok": True, "orderId": str(j["order"]), "raw": j}
    return {"ok": False, "error": str(j)}

def provider_status(order_id: str):
    res = _post({"action": "status", "order": str(order_id)})
    if not res["ok"]:
        return res
    return {"ok": True, "raw": res["data"]}

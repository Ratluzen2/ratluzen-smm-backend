# app/providers/smm_client.py
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
        # بعض المزودين يرجّعون JSON، وبعضهم نص -> نحاول JSON ثم fallback
        try:
            j = r.json()
        except Exception:
            j = {"raw": r.text}
        return {"ok": True, "data": j}
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"http error: {e}"}

# =========== عمليات القياسية v2 ===========
def provider_balance():
    """
    POST key, action=balance
    مثال قياسي للنتيجة: {"balance":"12.34","currency":"USD"}
    """
    return _post({"action": "balance"})

def provider_services():
    """
    POST key, action=services
    نتيجة: قائمة خدمات تحوي service/name/rate/min/max/...
    """
    return _post({"action": "services"})

def provider_add_order(service_id: int, link: str, quantity: int, **extra):
    """
    POST key, action=add, service, link, quantity, (اختياري: runs, interval, comments, username,...)
    نتيجة قياسية: {"order": 123456}
    """
    data = {
        "action": "add",
        "service": int(service_id),
        "link": link,
        "quantity": int(quantity),
    }
    # تمرير أي حقول إضافية حسب نوع الخدمة (إن لزم)
    data.update({k: v for k, v in extra.items() if v is not None})
    res = _post(data)
    if not res["ok"]:
        return res
    j = res["data"]
    # توحيد الإخراج
    if isinstance(j, dict) and "order" in j:
        return {"ok": True, "orderId": str(j["order"]), "raw": j}
    # بعض اللوحات ترجع حقول أخرى عند الخطأ
    return {"ok": False, "error": str(j)}

def provider_status(order_id: str):
    """
    POST key, action=status, order
    نتيجة قياسية: {"status":"Completed","charge":"0.50","start_count":"...","remains":"..."}
    """
    res = _post({"action": "status", "order": str(order_id)})
    if not res["ok"]:
        return res
    return {"ok": True, "raw": res["data"]}

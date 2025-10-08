from . .config import settings
import httpx

def _fail(msg: str):
    return {"ok": False, "error": msg}

def provider_add_order(service_key: str, link: str, quantity: int):
    """
    استدعاء مزوّد الخدمات (SMM) لإضافة طلب.
    يتوقع أن يكون لدى المزوّد endpoints مثل:
      POST {PROVIDER_URL}/add  json: {key, service, link, quantity}
    عدّل حسب مزوّدك الحقيقي.
    """
    if not settings.PROVIDER_URL or not settings.PROVIDER_KEY:
        # للعمل بدون مزود — وضع تجريبي
        return {"ok": True, "orderId": f"SIM-{service_key}-{quantity}"}

    try:
        with httpx.Client(timeout=20.0) as c:
            resp = c.post(
                f"{settings.PROVIDER_URL.rstrip('/')}/add",
                json={
                    "key": settings.PROVIDER_KEY,
                    "service": service_key,  # بعض المزودين يتوقعون رقم خدمة، إن لزم عدّل
                    "link": link,
                    "quantity": quantity,
                }
            )
            if resp.status_code // 100 != 2:
                return _fail(f"provider http {resp.status_code}")
            data = resp.json()
            # عدّل حسب شكل استجابة مزودك:
            if "order" in data:
                return {"ok": True, "orderId": str(data["order"])}
            if "orderId" in data:
                return {"ok": True, "orderId": str(data["orderId"])}
            return _fail("unknown provider response")
    except Exception as e:
        return _fail(str(e))

def provider_balance():
    if not settings.PROVIDER_URL or not settings.PROVIDER_KEY:
        return {"ok": True, "balance": 0.0}
    try:
        with httpx.Client(timeout=15.0) as c:
            resp = c.get(
                f"{settings.PROVIDER_URL.rstrip('/')}/balance",
                params={"key": settings.PROVIDER_KEY}
            )
            if resp.status_code // 100 != 2:
                return _fail(f"provider http {resp.status_code}")
            data = resp.json()
            bal = data.get("balance") or data.get("Balance") or 0.0
            try:
                bal = float(bal)
            except Exception:
                bal = 0.0
            return {"ok": True, "balance": bal}
    except Exception as e:
        return _fail(str(e))

def provider_status(order_id: str):
    if not settings.PROVIDER_URL or not settings.PROVIDER_KEY:
        # وضع تجريبي
        return {"ok": True, "status": "processing"}
    try:
        with httpx.Client(timeout=15.0) as c:
            resp = c.get(
                f"{settings.PROVIDER_URL.rstrip('/')}/status",
                params={"key": settings.PROVIDER_KEY, "order": order_id}
            )
            if resp.status_code // 100 != 2:
                return _fail(f"provider http {resp.status_code}")
            data = resp.json()
            # عدّل حسب استجابة مزودك
            return {"ok": True, "raw": data}
    except Exception as e:
        return _fail(str(e))

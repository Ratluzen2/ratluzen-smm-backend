# app/routers/routes_provider.py
from fastapi import APIRouter, HTTPException, Query
import os
import httpx

router = APIRouter(prefix="/api/provider", tags=["provider"])

# أسماء المتغيرات في هيروكو (اختر أي زوج تحبه)
API_URL = os.getenv("SMM_API_URL") or os.getenv("PROVIDER_API_URL")
API_KEY = os.getenv("SMM_API_KEY") or os.getenv("PROVIDER_API_KEY")


async def _call_provider(payload: dict) -> dict:
    """
    يستدعي API المزود وفق صيغة SMM Panel التقليدية (api/v2)
    - balance:  POST {key, action=balance}
    - status:   POST {key, action=status, order=<id>}
    يرجع JSON موحد قدر الإمكان.
    """
    if not API_URL or not API_KEY:
        raise HTTPException(status_code=500, detail="Provider API is not configured")

    data = {"key": API_KEY}
    data.update(payload)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(API_URL, data=data)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider connection error: {e}")

    text = resp.text
    try:
        parsed = resp.json()
    except Exception:
        # المزود قد يرجع نصاً بسيطاً؛ أعده كما هو
        parsed = {"raw": text}

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=parsed)

    return parsed


@router.get("/balance")
async def get_balance():
    """
    يرجع رصيد المزود.
    الرد المتوقع من مزودات SMM الشائعة:
    {"balance":"12.34","currency":"USD"}
    """
    data = await _call_provider({"action": "balance"})
    # توحيد الحقول قدر الإمكان
    return {
        "ok": True,
        "balance": data.get("balance") or data.get("balance_amount") or data.get("raw"),
        "currency": data.get("currency"),
        "provider_raw": data,
    }


@router.get("/order/status")
async def order_status(order_id: str = Query(..., alias="order_id")):
    """
    يفحص حالة طلب رقم order_id.
    أمثلة رد المزود: {"status":"Completed","remains":"0"}
    """
    data = await _call_provider({"action": "status", "order": order_id})
    return {"ok": True, "order_id": order_id, "provider_raw": data}

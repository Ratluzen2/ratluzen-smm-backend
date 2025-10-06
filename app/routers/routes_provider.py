from fastapi import APIRouter, HTTPException, Query
import os, httpx

router = APIRouter(prefix="/api/admin", tags=["admin"])

# وفّر هذه المتغيرات في إعدادات هيروكو:
# PROVIDER_BASE_URL: مثال "https://panel.example.com/api/v2"
# PROVIDER_API_KEY : مفتاح الـ API للمزوّد
PROVIDER_BASE_URL = os.getenv("PROVIDER_BASE_URL")
PROVIDER_API_KEY  = os.getenv("PROVIDER_API_KEY")

def _check_env():
    if not PROVIDER_BASE_URL or not PROVIDER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Provider config is missing (PROVIDER_BASE_URL / PROVIDER_API_KEY).",
        )

@router.get("/balance")
async def balance():
    """
    فحص رصيد مزوّد الخدمات.
    أغلب الألواح تستخدم POST form:
      key=<KEY>&action=balance
    """
    _check_env()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                PROVIDER_BASE_URL,
                data={"key": PROVIDER_API_KEY, "action": "balance"},
                headers={"Accept": "application/json"},
            )
        # بعض المزودين يعيدون نص خام:
        try:
            return r.json()
        except Exception:
            return {"raw": r.text, "status_code": r.status_code}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider balance error: {e}")

@router.get("/order-status")
async def order_status(order_id: str = Query(..., alias="order_id")):
    """
    فحص حالة طلب:
      key=<KEY>&action=status&order=<order_id>
    """
    _check_env()
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(
                PROVIDER_BASE_URL,
                data={"key": PROVIDER_API_KEY, "action": "status", "order": order_id},
                headers={"Accept": "application/json"},
            )
        try:
            return r.json()
        except Exception:
            return {"raw": r.text, "status_code": r.status_code}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider status error: {e}")

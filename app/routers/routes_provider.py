# app/routers/routes_provider.py
from fastapi import APIRouter, HTTPException, Query

from ..providers.smm_client import SmmClient

router = APIRouter(prefix="/api/provider", tags=["provider"])


def _client() -> SmmClient:
    # نبني العميل عند كل طلب لضمان تحميل متغيرات البيئة الجديدة إن تغيّرت
    try:
        return SmmClient()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balance")
async def get_balance():
    client = _client()
    return await client.get_balance()


@router.get("/order/status")
async def order_status(order_id: str = Query(..., alias="order_id")):
    client = _client()
    return await client.get_order_status(order_id)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..providers.smm import SMMProvider

router = APIRouter()
provider = SMMProvider()

class OrderStatusIn(BaseModel):
    order_id: str

@router.get("/balance")
async def balance():
    """
    يُستخدم من التطبيق: GET /api/provider/balance
    """
    res = await provider.get_balance()
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "failed"))
    return {"result": res}

@router.post("/order-status")
async def order_status(body: OrderStatusIn):
    """
    يُستخدم من التطبيق: POST /api/provider/order-status
    { "order_id": "123456" }
    """
    res = await provider.get_order_status(body.order_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "failed"))
    return {"result": res}

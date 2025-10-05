# app/routers/smm.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List

from app.providers.smm_client import SmmClient

router = APIRouter()

class OrderCreate(BaseModel):
    uid: str = Field(..., description="UID الخاص بالمستخدم")
    service_id: int = Field(..., description="ID الخدمة في مزود SMM")
    link: str = Field(..., description="الرابط/المعرف المطلوب")
    quantity: int = Field(..., ge=1)

@router.get("/balance")
async def smm_balance() -> Dict[str, Any]:
    c = SmmClient()
    return await c.get_balance()

@router.get("/services")
async def smm_services() -> List[Dict[str, Any]]:
    c = SmmClient()
    return await c.get_services()

@router.post("/order")
async def smm_order(body: OrderCreate) -> Dict[str, Any]:
    c = SmmClient()
    j = await c.add_order(service_id=body.service_id, link=body.link, quantity=body.quantity)
    # المتوقع: {"order": 123456} أو {"error":"..."}
    if "order" not in j:
        raise HTTPException(status_code=400, detail=j)
    return {"provider_order_id": str(j["order"])}

@router.get("/status/{provider_order_id}")
async def smm_status(provider_order_id: str) -> Dict[str, Any]:
    c = SmmClient()
    return await c.get_status(provider_order_id)

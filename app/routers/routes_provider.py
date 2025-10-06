from math import ceil
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from ..db import get_db
from ..models import User, Order, Notice
from ..config import get_settings
from ..providers.smm_client import place_order as provider_place
from ..provider_map import PRICE_PER_K

router = APIRouter()
_settings = get_settings()

# --------- نماذج ---------
class OrderIn(BaseModel):
    service_key: str = Field(min_length=1)
    link: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    uid: Optional[str] = None  # لو لم يصل من التطبيق، نقبله من الهيدر

# --------- المستخدم يرسل طلب خدمة (يُحفظ معلّق) ---------
@router.post("/api/provider/order")
def create_service_order(
    payload: OrderIn,
    db: Session = Depends(get_db),
    x_uid: Optional[str] = Header(None, alias="X-UID"),
):
    uid = payload.uid or x_uid
    if not uid:
        uid = "anonymous"

    user = db.get(User, uid)
    if not user:
        # إنشاء تلقائي إن لم يكن موجودًا (يتماشى مع upsert)
        user = User(uid=uid, balance_usd=0)
        db.add(user)
        db.commit()

    # تقدير السعر سيرفريًا أيضًا (للتوثيق/الاسترجاع)
    ppk = PRICE_PER_K.get(payload.service_key, 0.0)
    est_price = ceil((payload.quantity / 1000.0) * ppk * 100) / 100.0

    order = Order(
        uid=uid,
        service_key=payload.service_key,
        link=payload.link,
        quantity=payload.quantity,
        price_usd=est_price,
        status="PENDING",
    )
    db.add(order)
    db.add(Notice(uid=None, for_owner=True,
                  title="طلب خدمات معلق",
                  body=f"طلب {payload.service_key} من UID={uid} بكمية {payload.quantity} وسعر {est_price}$"))
    db.commit()
    db.refresh(order)
    return {"ok": True, "order_id": order.id}

# --------- لوحة المالك: عرض المعلّق ---------
@router.get("/api/admin/pending/services")
def admin_pending_services(password: str = Query(...), db: Session = Depends(get_db)):
    if password != _settings.ADMIN_PASSWORD:
        raise HTTPException(401, "bad password")
    rows = db.query(Order).filter(Order.status == "PENDING").order_by(Order.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "uid": r.uid,
            "service_key": r.service_key,
            "quantity": r.quantity,
            "price_usd": float(r.price_usd or 0),
            "created_at": r.created_at.isoformat(),
            "link": r.link,
        } for r in rows
    ]

# --------- رفض الطلب (مع استرجاع رصيد المستخدم) ---------
class RejectIn(BaseModel):
    reason: Optional[str] = None

@router.post("/api/admin/orders/{order_id}/reject")
def admin_reject_order(order_id: int, payload: RejectIn, password: str = Query(...), db: Session = Depends(get_db)):
    if password != _settings.ADMIN_PASSWORD:
        raise HTTPException(401, "bad password")
    order = db.get(Order, order_id)
    if not order or order.status != "PENDING":
        raise HTTPException(404, "order not found or not pending")

    user = db.get(User, order.uid)
    if user:
        user.balance_usd = (user.balance_usd or 0) + float(order.price_usd or 0)

    order.status = "REJECTED"
    db.add(Notice(uid=order.uid, for_owner=False, title="رفض الطلب",
                  body=f"تم رفض طلبك #{order.id} ({order.service_key}). تم إرجاع {float(order.price_usd or 0)}$ إلى رصيدك."))
    db.commit()
    return {"ok": True}

# --------- تنفيذ الطلب (يرسل للمزوّد) ---------
@router.post("/api/admin/orders/{order_id}/approve")
def admin_approve_order(order_id: int, password: str = Query(...), db: Session = Depends(get_db)):
    if password != _settings.ADMIN_PASSWORD:
        raise HTTPException(401, "bad password")
    order = db.get(Order, order_id)
    if not order or order.status != "PENDING":
        raise HTTPException(404, "order not found or not pending")

    # إرسال للمزوّد
    res = provider_place(order.service_key, order.link, order.quantity)
    if "error" in res:
        raise HTTPException(400, res["error"])

    # بعض مزوّدين يرجعون {"order": 12345}
    provider_id = str(res.get("order") or res.get("order_id") or "")
    order.provider_order_id = provider_id
    order.status = "PROCESSED"

    db.add(Notice(uid=order.uid, for_owner=False, title="تم تنفيذ الطلب",
                  body=f"تم تنفيذ طلبك #{order.id} ({order.service_key}). رقم مزوّد: {provider_id}"))
    db.add(Notice(uid=None, for_owner=True, title="طلب نُفّذ", body=f"order_id={order.id} -> provider={provider_id}"))
    db.commit()
    return {"ok": True, "provider_order_id": provider_id}

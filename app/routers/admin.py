from fastapi import APIRouter, Depends, Header, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from ..config import settings
from ..database import get_db
from ..models import User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup, PubgOrder, LudoOrder, Notice
from ..providers.kd1s_client import provider_add_order, provider_balance, provider_status

r = APIRouter()

# -------- Helpers ----------
def _row(obj):
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    return out

def _guard(x_admin_pass: Optional[str] = Header(default=None, alias="x-admin-pass")):
    pwd = (x_admin_pass or "").strip()
    if pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

# ---------- فحص سريع لكلمة المرور ----------
@r.get("/admin/check", dependencies=[Depends(_guard)])
def admin_check():
    return {"ok": True}

# ---------- الخدمات المعلّقة ----------
@r.get("/admin/pending/services", dependencies=[Depends(_guard)])
def pending_services(db: Session = Depends(get_db)):
    lst = (
        db.query(ServiceOrder)
        .filter_by(status="pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    # يعيد {"list":[...]} ليتوافق مع التطبيق
    return {"list": [
        {
            "id": o.id,
            "uid": o.uid,
            "service_key": o.service_key,
            "service_code": o.service_code,
            "link": o.link,
            "quantity": o.quantity,
            "price": o.price,
            "status": o.status
        } for o in lst
    ]}

# (نسخة بديلة متوافقة مع بعض إصدارات التطبيق)
@r.post("/admin/orders/approve", dependencies=[Depends(_guard)])
def approve_service_compat(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    return approve_service(order_id, db)

@r.post("/admin/orders/reject", dependencies=[Depends(_guard)])
def reject_service_compat(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    return reject_service(order_id, db)

@r.post("/admin/orders/refund", dependencies=[Depends(_guard)])
def refund_service_compat(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    return refund_service(order_id, db)

@r.post("/admin/pending/services/{order_id}/approve", dependencies=[Depends(_guard)])
def approve_service(order_id: int, db: Session = Depends(get_db)):
    o = db.get(ServiceOrder, order_id)
    if not o or o.status != "pending":
        raise HTTPException(404, "order not found or not pending")

    # إرسال فعلي إلى KD1S
    send = provider_add_order(o.service_code, o.link, o.quantity)
    if not send.get("ok"):
        raise HTTPException(502,

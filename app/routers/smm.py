# app/routers/smm.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from ..database import get_db
from ..models import User, ServiceOrder, WalletCard, Notice

r = APIRouter(prefix="/api", tags=["app"])

# --------- Helpers ---------
def _now_ts() -> int:
    return int(datetime.utcnow().timestamp() * 1000)

def _ensure_user(db: Session, uid: str) -> User:
    u = db.query(User).filter_by(uid=uid).first()
    if u is None:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.commit()
        db.refresh(u)
    return u

# --------- Schemas ---------
class UpsertReq(BaseModel):
    uid: str = Field(min_length=1)

class BalanceResp(BaseModel):
    balance: float

class ProviderOrderReq(BaseModel):
    uid: str
    service_id: int
    service_name: str
    link: Optional[str] = None
    quantity: Optional[int] = None
    price: float

class ManualOrderReq(BaseModel):
    uid: str
    title: str

class AsiacellReq(BaseModel):
    uid: str
    card: str

class OrderItemResp(BaseModel):
    id: str
    title: str
    quantity: int
    price: float
    payload: str
    status: str
    created_at: int

# --------- Endpoints ---------

@r.post("/users/upsert")
def upsert_user(payload: UpsertReq, db: Session = Depends(get_db)):
    _ensure_user(db, payload.uid)
    return {"ok": True}

@r.get("/wallet/balance", response_model=BalanceResp)
def wallet_balance(uid: str, db: Session = Depends(get_db)):
    u = _ensure_user(db, uid)
    return BalanceResp(balance=round(u.balance or 0.0, 2))

@r.post("/orders/create/provider")
def create_provider_order(req: ProviderOrderReq, db: Session = Depends(get_db)):
    u = _ensure_user(db, req.uid)
    if u.is_banned:
        raise HTTPException(403, "banned")
    if (u.balance or 0.0) < req.price:
        raise HTTPException(400, "insufficient_balance")

    # خصم الرصيد وإنشاء الطلب كـ pending
    u.balance = round((u.balance or 0.0) - float(req.price), 2)
    db.add(u)

    order = ServiceOrder(
        uid=req.uid,
        service_key=req.service_name,
        service_code=int(req.service_id),
        link=req.link or "",
        quantity=req.quantity or 0,
        unit_price_per_k=None,   # اختياري
        price=float(req.price),
        status="pending",
        provider_order_id=None,
    )
    db.add(order)

    # إشعار للمستخدم + المالك
    db.add(Notice(title="طلب جديد", body=f"طلب {req.service_name} قيد المراجعة.", for_owner=False, uid=req.uid))
    db.add(Notice(title="طلب خدمات معلّق", body=f"UID={req.uid} | {req.service_name} | qty={req.quantity}", for_owner=True, uid=None))

    db.commit()
    return {"ok": True, "order_id": order.id}

@r.post("/orders/create/manual")
def create_manual_order(req: ManualOrderReq, db: Session = Depends(get_db)):
    u = _ensure_user(db, req.uid)
    if u.is_banned:
        raise HTTPException(403, "banned")

    order = ServiceOrder(
        uid=req.uid,
        service_key=req.title,     # عنوان الطلب اليدوي
        service_code=None,
        link=None,
        quantity=None,
        unit_price_per_k=None,
        price=0.0,
        status="pending",
    )
    db.add(order)
    db.add(Notice(title="طلب معلّق", body=f"تم استلام طلبك: {req.title}", for_owner=False, uid=req.uid))
    db.add(Notice(title="طلب يدوي جديد", body=f"UID={req.uid} | {req.title}", for_owner=True, uid=None))
    db.commit()
    return {"ok": True, "order_id": order.id}

@r.get("/orders/my", response_model=List[OrderItemResp])
def my_orders(uid: str, db: Session = Depends(get_db)):
    _ensure_user(db, uid)
    lst = (
        db.query(ServiceOrder)
        .filter_by(uid=uid)
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )

    def map_status(s: str) -> str:
        s = (s or "").lower()
        if s == "done": return "Done"
        if s == "rejected": return "Rejected"
        if s == "refunded": return "Refunded"
        if s == "processing": return "Processing"
        return "Pending"

    out: list[OrderItemResp] = []
    for o in lst:
        out.append(
            OrderItemResp(
                id=str(o.id),
                title=o.service_key,
                quantity=int(o.quantity or 0),
                price=float(o.price or 0.0),
                payload=o.link or "",
                status=map_status(o.status),
                created_at=int(o.created_at.timestamp() * 1000) if o.created_at else _now_ts(),
            )
        )
    return out

@r.post("/wallet/asiacell/submit")
def submit_asiacell(req: AsiacellReq, db: Session = Depends(get_db)):
    digits = "".join([c for c in req.card if c.isdigit()])
    if len(digits) not in (14, 16):
        raise HTTPException(400, "card_must_be_14_or_16_digits")

    _ensure_user(db, req.uid)
    card = WalletCard(uid=req.uid, card_number=digits, status="pending")
    db.add(card)

    # إشعار المالك هلدى لوحة التحكم + إشعار المستخدم
    db.add(Notice(title="كارت أسيا سيل جديد", body=f"UID={req.uid} | CARD={digits}", for_owner=True, uid=None))
    db.add(Notice(title="تم استلام كارتك", body=f"سيتم مراجعته من المالك: ****{digits[-4:]}", for_owner=False, uid=req.uid))
    db.commit()

    return {"ok": True, "card_id": card.id}

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice, Token
)
from ..providers.smm_client import provider_add_order, provider_balance, provider_status
import httpx

r = APIRouter(prefix="/admin")

# ---------- Pydantic payloads ----------
class AmountReq(BaseModel):
    uid: Optional[str] = None
    amount: float

class AcceptCardReq(BaseModel):
    amount_usd: float
    reviewed_by: Optional[str] = None

class GiftCodeReq(BaseModel):
    gift_code: str

class CodeReq(BaseModel):
    code: str

# -------- Helpers --------
def _row(obj):
    if obj is None:
        return None
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    return out

def _rows(lst):
    return [_row(o) for o in lst]

# -------- Guard (owner password) --------
def guard(
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_alt: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None)
):
    pwd = (x_admin_pass or x_admin_pass_alt or key or "").strip()
    if pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

# فحص سريع
@r.get("/check", dependencies=[Depends(guard)])
def check_ok():
    return {"ok": True}

# ---------- الخدمات المعلّقة (ترجيع مصفوفة مباشرة) ----------
@r.get("/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)):
    lst = (
        db.query(ServiceOrder)
        .filter_by(status="pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    # يعيد مصفوفة فقط لأن التطبيق يتوقع JSONArray
    return _rows(lst)

# alias للمسارات التي يتوقعها التطبيق
@r.get("/pending/topups", dependencies=[Depends(guard)])
def pending_topups_alias(db: Session = Depends(get_db)):
    lst = (
        db.query(WalletCard)
        .filter_by(status="pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    return _rows(lst)

@r.get("/pending/cards", dependencies=[Depends(guard)])
def pending_cards(db: Session = Depends(get_db)):
    lst = (
        db.query(WalletCard)
        .filter_by(status="pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    return _rows(lst)

@r.get("/pending/itunes", dependencies=[Depends(guard)])
def pending_itunes(db: Session = Depends(get_db)):
    lst = (
        db.query(ItunesOrder)
        .filter_by(status="pending")
        .order_by(ItunesOrder.created_at.desc())
        .all()
    )
    return _rows(lst)

@r.get("/pending/phone", dependencies=[Depends(guard)])
def pending_phone(db: Session = Depends(get_db)):
    lst = (
        db.query(PhoneTopup)
        .filter_by(status="pending")
        .order_by(PhoneTopup.created_at.desc())
        .all()
    )
    return _rows(lst)

@r.get("/pending/pubg", dependencies=[Depends(guard)])
def pending_pubg(db: Session = Depends(get_db)):
    lst = (
        db.query(PubgOrder)
        .filter_by(status="pending")
        .order_by(PubgOrder.created_at.desc())
        .all()
    )
    return _rows(lst)

@r.get("/pending/ludo", dependencies=[Depends(guard)])
def pending_ludo(db: Session = Depends(get_db)):
    lst = (
        db.query(LudoOrder)
        .filter_by(status="pending")
        .order_by(LudoOrder.created_at.desc())
        .all()
    )
    return _rows(lst)

# ---------- إجراءات الخدمات (تنفيذ/رفض/رد) ----------
@r.post("/orders/approve", dependencies=[Depends(guard)])
def orders_approve(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    order = db.get(ServiceOrder, order_id)
    if not order or order.status != "pending":
        raise HTTPException(404, "order not found or not pending")

    send = provider_add_order(str(order.service_code), order.link, order.quantity)
    if not send.get("ok"):
        raise HTTPException(502, send.get("error", "provider error"))

    order.status = "processing"
    order.provider_order_id = send["orderId"]
    db.add(order)
    db.add(Notice(title="تم تنفيذ طلبك", body=f"أُرسل للمزوّد | رقم: {order.provider_order_id}", for_owner=False, uid=order.uid))
    db.commit()
    return {"ok": True}

@r.post("/orders/reject", dependencies=[Depends(guard)])
def orders_reject(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    order = db.get(ServiceOrder, order_id)
    if not order or order.status != "pending":
        raise HTTPException(404, "order not found or not pending")
    order.status = "rejected"
    u = db.query(User).filter_by(uid=order.uid).first()
    if u:
        u.balance = round(u.balance + order.price, 2)
        db.add(u)
    db.add(order)
    db.add(Notice(title="تم رفض الطلب", body="تم ردّ الرصيد لحسابك.", for_owner=False, uid=order.uid))
    db.commit()
    return {"ok": True}

@r.post("/orders/refund", dependencies=[Depends(guard)])
def orders_refund(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    order = db.get(ServiceOrder, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    u = db.query(User).filter_by(uid=order.uid).first()
    if u:
        u.balance = round(u.balance + order.price, 2)
        db.add(u)
    order.status = "rejected"
    db.add(order)
    db.commit()
    return {"ok": True}

# ---------- كارتات أسيا سيل ----------
@r.post("/cards/accept", dependencies=[Depends(guard)])
def accept_card(
    card_id: int = Body(..., embed=True),
    amount_usd: float = Body(..., embed=True),
    reviewed_by: Optional[str] = Body(default="owner", embed=True),
    db: Session = Depends(get_db)
):
    card = db.get(WalletCard, card_id)
    if not card or card.status != "pending":
        raise HTTPException(404, "card not found or not pending")
    card.status = "accepted"
    card.amount_usd = float(amount_usd)
    card.reviewed_by = reviewed_by or "owner"
    u = db.query(User).filter_by(uid=card.uid).first()
    if not u:
        u = User(uid=card.uid, balance=0.0)
    u.balance = round(u.balance + float(amount_usd), 2)
    db.add(u)
    db.add(card)
    db.add(Notice(title="تم شحن رصيدك", body=f"+${amount_usd} عبر بطاقة أسيا سيل", for_owner=False, uid=card.uid))
    db.commit()
    return {"ok": True}

@r.post("/cards/reject", dependencies=[Depends(guard)])
def reject_card(card_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    card = db.get(WalletCard, card_id)
    if not card or card.status != "pending":
        raise HTTPException(404, "card not found or not pending")
    card.status = "rejected"
    db.add(card)
    db.add(Notice(title="تم رفض الكارت", body="يرجى التأكد من الرقم والمحاولة مجددًا.", for_owner=False, uid=card.uid))
    db.commit()
    return {"ok": True}

# ---------- آيتونز ----------
@r.post("/itunes/deliver", dependencies=[Depends(guard)])
def deliver_itunes(oid: int = Body(..., embed=True), gift_code: str = Body(..., embed=True), db: Session = Depends(get_db)):
    o = db.get(ItunesOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"
    o.gift_code = gift_code
    db.add(o)
    db.add(Notice(title="كود آيتونز", body=f"الكود: {gift_code}", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

@r.post("/itunes/reject", dependencies=[Depends(guard)])
def reject_itunes(oid: int = Body(..., embed=True), db: Session = Depends(get_db)):
    o = db.get(ItunesOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "rejected"
    db.add(o)
    db.add(Notice(title="رفض آيتونز", body="تم رفض طلبك.", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

# ---------- أرصدة الهاتف ----------
@r.post("/phone/deliver", dependencies=[Depends(guard)])
def deliver_phone(oid: int = Body(..., embed=True), code: str = Body(..., embed=True), db: Session = Depends(get_db

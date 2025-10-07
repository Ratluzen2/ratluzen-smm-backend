# app/routers/admin.py
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

r = APIRouter()

# ---------- helpers ----------
def _row(obj):
    if obj is None:
        return None
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    return out

def guard(
    x_admin_pass_hdr: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_hdr_low: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None),
    x_admin_pass_q: Optional[str] = Query(default=None, alias="X-Admin-Pass"),
):
    pwd = (x_admin_pass_hdr or x_admin_pass_hdr_low or key or x_admin_pass_q or "").strip()
    if pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

# ---------- admin misc ----------
@r.get("/admin/check", dependencies=[Depends(guard)])
def check_ok():
    return {"ok": True}

@r.get("/admin/users/count", dependencies=[Depends(guard)])
def users_count(db: Session = Depends(get_db)):
    return {"ok": True, "count": db.query(User).count()}

@r.get("/admin/users/balances", dependencies=[Depends(guard)])
def users_balances(db: Session = Depends(get_db)):
    lst = db.query(User).order_by(User.balance.desc()).limit(500).all()
    return {"ok": True, "list": [{"uid": u.uid, "balance": u.balance, "is_banned": u.is_banned} for u in lst]}

# ---------- balance operations ----------
class AmountReq(BaseModel):
    amount: float

@r.post("/admin/users/{uid}/topup", dependencies=[Depends(guard)])
def user_topup(
    uid: str,
    amount: Optional[float] = Query(default=None),
    payload: Optional[AmountReq] = Body(default=None),
    db: Session = Depends(get_db),
):
    if payload and payload.amount is not None:
        amount = payload.amount
    if amount is None:
        raise HTTPException(400, "amount required")
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0, is_banned=False)
    u.balance = round(u.balance + float(amount), 2)
    db.add(u)
    db.add(Notice(title="تم إضافة رصيد", body=f"+${amount}", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "balance": u.balance}

@r.post("/admin/users/{uid}/deduct", dependencies=[Depends(guard)])
def user_deduct(
    uid: str,
    amount: Optional[float] = Query(default=None),
    payload: Optional[AmountReq] = Body(default=None),
    db: Session = Depends(get_db),
):
    if payload and payload.amount is not None:
        amount = payload.amount
    if amount is None:
        raise HTTPException(400, "amount required")
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0, is_banned=False)
    u.balance = max(0.0, round(u.balance - float(amount), 2))
    db.add(u)
    db.add(Notice(title="تم خصم رصيد", body=f"-${amount}", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "balance": u.balance}

# ---- compatibility aliases for the Android app ----
class WalletBody(BaseModel):
    uid: str
    amount: float

@r.post("/admin/wallet/topup", dependencies=[Depends(guard)])
def wallet_topup(body: WalletBody, db: Session = Depends(get_db)):
    return user_topup(uid=body.uid, payload=AmountReq(amount=body.amount), db=db)

@r.post("/admin/wallet/deduct", dependencies=[Depends(guard)])
def wallet_deduct(body: WalletBody, db: Session = Depends(get_db)):
    return user_deduct(uid=body.uid, payload=AmountReq(amount=body.amount), db=db)

# ---------- Asiacell cards ----------
class AcceptCardReq(BaseModel):
    amount_usd: float
    reviewed_by: Optional[str] = None

@r.get("/admin/pending/cards", dependencies=[Depends(guard)])
def pending_cards(db: Session = Depends(get_db)):
    lst = db.query(WalletCard).filter_by(status="pending").order_by(WalletCard.created_at.desc()).all()
    return {"ok": True, "list": [_row(x) for x in lst]}

# alias to match app label "topups"
@r.get("/admin/pending/topups", dependencies=[Depends(guard)])
def pending_topups(db: Session = Depends(get_db)):
    return pending_cards(db)

@r.post("/admin/pending/cards/{card_id}/accept", dependencies=[Depends(guard)])
def accept_card(
    card_id: int,
    amount_usd: Optional[float] = Query(default=None),
    reviewed_by: Optional[str] = Query(default="owner"),
    payload: Optional[AcceptCardReq] = Body(default=None),
    db: Session = Depends(get_db),
):
    if payload:
        amount_usd = payload.amount_usd if payload.amount_usd is not None else amount_usd
        if payload.reviewed_by:
            reviewed_by = payload.reviewed_by
    if amount_usd is None:
        raise HTTPException(400, "amount_usd required")

    card = db.get(WalletCard, card_id)
    if not card or card.status != "pending":
        raise HTTPException(404, "card not found or not pending")

    card.status = "accepted"
    card.amount_usd = float(amount_usd)
    card.reviewed_by = reviewed_by or "owner"

    u = db.query(User).filter_by(uid=card.uid).first()
    if not u:
        u = User(uid=card.uid, balance=0.0, is_banned=False)
    u.balance = round(u.balance + float(amount_usd), 2)
    db.add(u); db.add(card)
    db.add(Notice(title="تم شحن رصيدك", body=f"+${amount_usd} عبر بطاقة أسيا سيل", for_owner=False, uid=card.uid))
    db.commit()
    return {"ok": True}

@r.post("/admin/pending/cards/{card_id}/reject", dependencies=[Depends(guard)])
def reject_card(card_id: int, db: Session = Depends(get_db)):
    card = db.get(WalletCard, card_id)
    if not card or card.status != "pending":
        raise HTTPException(404, "card not found or not pending")
    card.status = "rejected"
    db.add(card)
    db.add(Notice(title="تم رفض الكارت", body="يرجى التأكد من الرقم والمحاولة مجددًا.", for_owner=False, uid=card.uid))
    db.commit()
    return {"ok": True}

# ---------- provider (optional) ----------
@r.get("/admin/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    return provider_balance()

@r.get("/admin/provider/order-status/{ext_order_id}", dependencies=[Depends(guard)])
def provider_order_status(ext_order_id: str):
    return provider_status(ext_order_id)

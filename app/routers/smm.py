# app/routers/smm.py
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from ..database import get_db
from ..models import User, WalletCard, Notice

r = APIRouter()

# --------- نماذج طلبات ----------
class UpsertReq(BaseModel):
    uid: str

class AsiacellCardReq(BaseModel):
    uid: str
    card_number: str

# --------- أدوات مساعدة ----------
def _row(obj):
    if obj is None:
        return None
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    return out

# --------- تهيئة/إنشاء مستخدم إن لم يوجد ----------
@r.post("/users/upsert")
def users_upsert(payload: UpsertReq, db: Session = Depends(get_db)):
    uid = payload.uid.strip()
    if not uid:
        raise HTTPException(400, "uid required")

    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.commit()
    return {"ok": True, "user": {"uid": u.uid, "balance": u.balance, "is_banned": u.is_banned}}

@r.get("/users/{uid}")
def users_get(uid: str, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        raise HTTPException(404, "user not found")
    return {"ok": True, "user": {"uid": u.uid, "balance": u.balance, "is_banned": u.is_banned}}

# --------- شحن عبر أسيا سيل (إرسال الكارت) ----------
@r.post("/wallet/asiacell/submit")
def asiacell_submit(payload: AsiacellCardReq = Body(...), db: Session = Depends(get_db)):
    uid = (payload.uid or "").strip()
    card = (payload.card_number or "").strip().replace(" ", "").replace("-", "")

    if not uid:
        raise HTTPException(400, "uid required")

    # تحقّق رقم الكارت: أرقام فقط وطول 14 أو 16
    if not card.isdigit() or len(card) not in (14, 16):
        raise HTTPException(400, "card_number must be 14 or 16 digits")

    # أنشئ المستخدم لو غير موجود
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.commit()

    # امنع ازدواجية نفس الكارت بحالة pending
    exists = (
        db.query(WalletCard)
        .filter(WalletCard.card_number == card, WalletCard.status == "pending")
        .first()
    )
    if exists:
        raise HTTPException(409, "card already submitted and pending")

    wc = WalletCard(uid=uid, card_number=card, status="pending")
    db.add(wc)

    # إشعار (مخزّن) للمالك
    db.add(
        Notice(
            title="طلب كارت أسيا سيل جديد",
            body=f"UID: {uid}\nCard: {card}",
            for_owner=True,
            uid=None
        )
    )
    db.commit()
    return {"ok": True, "wallet_card": _row(wc)}

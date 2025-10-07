# app/routers/smm.py
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)

r = APIRouter()  # سيتم تضمينه في main بـ prefix="/api"


# =========================
# Payloads
# =========================
class UpsertUserReq(BaseModel):
    uid: str = Field(..., min_length=2, max_length=64)

class ProviderOrderReq(BaseModel):
    uid: str
    service_id: int
    service_name: str
    link: str
    quantity: int
    price: float  # السعر النهائي المحسوب في التطبيق

class ManualOrderReq(BaseModel):
    uid: str
    title: str  # اسم الخدمة اليدوية (آيتونز/كارت هاتف/ببجي/لودو…)

class AsiacellCardReq(BaseModel):
    uid: str
    card: str   # 14 أو 16 رقم


# =========================
# Helpers
# =========================
def _row_service(o: ServiceOrder) -> dict:
    return {
        "id": str(o.id),
        "title": o.service_key,
        "quantity": o.quantity,
        "price": float(o.price),
        "payload": o.link,
        "status": o.status.capitalize(),
        "created_at": int(o.created_at.timestamp() * 1000) if o.created_at else 0
    }


# =========================
# Public endpoints (app)
# =========================

@r.post("/users/upsert")
def upsert_user(payload: UpsertUserReq, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=payload.uid).first()
    if not u:
        u = User(uid=payload.uid, balance=0.0)
        db.add(u)
        # إشعار ترحيبي بسيط
        db.add(Notice(title="مرحبًا", body="تم تفعيل حسابك.", uid=payload.uid, for_owner=False))
        # إشعار للمالك بوجود مستخدم جديد
        db.add(Notice(title="مستخدم جديد", body=f"UID={payload.uid}", uid=None, for_owner=True))
    db.commit()
    return {"ok": True}


@r.get("/wallet/balance")
def wallet_balance(uid: str = Query(..., min_length=2, max_length=64), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    bal = float(u.balance) if u else 0.0
    return {"ok": True, "balance": bal}


@r.post("/orders/create/provider")
def create_provider_order(payload: ProviderOrderReq, db: Session = Depends(get_db)):
    # تحقق وجود المستخدم
    u = db.query(User).filter_by(uid=payload.uid).first()
    if not u:
        u = User(uid=payload.uid, balance=0.0)
        db.add(u)
        db.flush()

    # تحقق الكمية والسعر
    if payload.quantity <= 0 or payload.price <= 0:
        raise HTTPException(400, "invalid quantity/price")

    # تحقق الرصيد
    if u.balance < payload.price:
        raise HTTPException(400, "insufficient balance")

    # حساب سعر لكل 1000 من السعر القادم من التطبيق (لتعبئة الحقل الإجباري)
    unit_per_k = round((payload.price * 1000.0) / max(payload.quantity, 1), 4)

    # خصم الرصيد وإنشاء الطلب (pending)
    u.balance = round(float(u.balance) - float(payload.price), 2)
    order = ServiceOrder(
        uid=payload.uid,
        service_key=payload.service_name,
        service_code=int(payload.service_id),
        link=payload.link,
        quantity=int(payload.quantity),
        unit_price_per_k=float(unit_per_k),
        price=float(payload.price),
        status="pending",
    )
    db.add(u)
    db.add(order)

    # إشعارات
    db.add(Notice(
        title="طلب خدمات معلّق",
        body=f"{payload.service_name} | كمية: {payload.quantity} | UID={payload.uid}",
        uid=None,
        for_owner=True
    ))
    db.add(Notice(
        title="تم استلام طلبك",
        body=f"سيتم تنفيذ طلب {payload.service_name} قريبًا.",
        uid=payload.uid,
        for_owner=False
    ))

    db.commit()
    return {"ok": True, "order_id": order.id}


@r.post("/orders/create/manual")
def create_manual_order(payload: ManualOrderReq, db: Session = Depends(get_db)):
    """إنشاء قيود للطلبات اليدوية بحسب العنوان المرسل من التطبيق."""
    title = payload.title.strip()

    if title == "شراء رصيد ايتونز":
        o = ItunesOrder(uid=payload.uid, amount=0, status="pending")
        db.add(o)
    elif title in ("شراء رصيد اثير", "شراء رصيد اسياسيل", "شراء رصيد كورك"):
        operator = "atheir" if "اثير" in title else ("asiacell" if "اسياسيل" in title else "korek")
        o = PhoneTopup(uid=payload.uid, operator=operator, amount=0, status="pending")
        db.add(o)
    elif title == "شحن شدات ببجي":
        # لا نملك الحقول من الواجهة (pkg/pubg_id)، نسجل قيدًا placeholder للمراجعة اليدوية
        o = PubgOrder(uid=payload.uid, pkg=0, pubg_id="", status="pending")
        db.add(o)
    elif title in ("شراء الماسات لودو", "شراء ذهب لودو"):
        kind = "diamonds" if "الماس" in title else "gold"
        o = LudoOrder(uid=payload.uid, kind=kind, pack=0, ludo_id="", status="pending")
        db.add(o)
    else:
        # طلب عام يُسجَّل كإشعار للمالك فقط
        db.add(Notice(title="طلب يدوي", body=f"{title} | UID={payload.uid}", uid=None, for_owner=True))

    db.add(Notice(title="طلب معلّق", body=f"تم إرسال طلب: {title}", uid=payload.uid, for_owner=False))
    db.add(Notice(title="طلب يدوي جديد", body=f"{title} من UID={payload.uid}", uid=None, for_owner=True))
    db.commit()
    return {"ok": True}


@r.post("/wallet/asiacell/submit")
def submit_asiacell_card(payload: AsiacellCardReq, db: Session = Depends(get_db)):
    digits = "".join(ch for ch in payload.card if ch.isdigit())
    if len(digits) not in (14, 16):
        raise HTTPException(400, "card must be 14 or 16 digits")

    w = WalletCard(uid=payload.uid, card_number=digits, status="pending")
    db.add(w)

    # إشعارات
    db.add(Notice(
        title="كارت أسيا سيل جديد",
        body=f"UID={payload.uid} | كارت: {digits}",
        uid=None,
        for_owner=True
    ))
    db.add(Notice(
        title="تم استلام كارتك",
        body="أُرسل كارت أسيا سيل للمالك للمراجعة.",
        uid=payload.uid,
        for_owner=False
    ))

    db.commit()
    return {"ok": True}


@r.get("/orders/my")
def my_orders(uid: str = Query(..., min_length=2, max_length=64), db: Session = Depends(get_db)) -> List[dict]:
    """يرجع قائمة الطلبات (حاليًا طلبات الخدمات المربوطة بالمزوّد)."""
    lst = (
        db.query(ServiceOrder)
        .filter_by(uid=uid)
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    return [_row_service(o) for o in lst]

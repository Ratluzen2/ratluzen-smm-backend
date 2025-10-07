# app/routers/smm.py
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)

r = APIRouter()

# ---------- نماذج ----------
class UpsertUserReq(BaseModel):
    uid: str

class ProviderOrderReq(BaseModel):
    uid: str
    service_id: int
    service_name: str
    link: str
    quantity: int
    price: float

class ManualReq(BaseModel):
    uid: str
    title: str

class AsiacellReq(BaseModel):
    uid: str
    card: str

# ---------- أدوات ----------
def _now():
    return datetime.now(timezone.utc)

# ---------- المستخدم ----------
@r.post("/users/upsert")
def upsert_user(p: UpsertUserReq, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=p.uid).first()
    if not u:
        u = User(uid=p.uid, balance=0.0)
        db.add(u)
    # لو لديك last_seen أضف تحديثه:
    if hasattr(u, "last_seen"):
        setattr(u, "last_seen", _now())
    db.commit()
    return {"ok": True}

# ---------- المحفظة ----------
@r.get("/wallet/balance")
def wallet_balance(uid: str = Query(...), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    bal = float(u.balance) if u else 0.0
    return {"balance": bal}

@r.post("/wallet/asiacell/submit")
def wallet_asiacell_submit(p: AsiacellReq, db: Session = Depends(get_db)):
    digits = "".join(ch for ch in p.card if ch.isdigit())
    if len(digits) not in (14,16):
        raise HTTPException(400, "INVALID_CARD")

    card = WalletCard(
        uid=p.uid,
        card_number=digits,
        status="pending",
        created_at=_now(),
    )
    db.add(card)

    # إشعار للمالك + للمستخدم
    db.add(Notice(
        title="كارت أسيا سيل جديد",
        body=f"UID={p.uid} | CARD={digits}",
        for_owner=True, uid=None
    ))
    db.add(Notice(
        title="تم استلام كارتك",
        body="تم إرسال الكارت للمراجعة، سيتم إضافة الرصيد بعد القبول.",
        for_owner=False, uid=p.uid
    ))
    db.commit()
    return {"ok": True}

# ---------- إنشاء طلب موفّر (مرتبط API) ----------
@r.post("/orders/create/provider")
def create_provider_order(p: ProviderOrderReq, db: Session = Depends(get_db)):
    # تحقق الرصيد
    u = db.query(User).filter_by(uid=p.uid).first()
    if not u:
        u = User(uid=p.uid, balance=0.0)
        db.add(u)
        db.flush()

    if float(u.balance) < float(p.price):
        raise HTTPException(400, "INSUFFICIENT_BALANCE")

    # خصم السعر
    u.balance = round(float(u.balance) - float(p.price), 2)
    db.add(u)

    # خزّن الطلب Pending
    o = ServiceOrder(
        uid=p.uid,
        service_key=p.service_name,     # اسم الخدمة الظاهر
        service_code=int(p.service_id), # معرف المزود
        link=p.link,
        quantity=int(p.quantity),
        unit_price_per_k=float(p.price) if p.quantity <= 1000 else float(p.price) / (p.quantity / 1000.0),
        price=float(p.price),
        status="pending",
        provider_order_id=None,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(o)

    # إشعارات
    db.add(Notice(
        title="طلب جديد قيد المراجعة",
        body=f"{p.service_name} | كمية={p.quantity} | UID={p.uid}",
        for_owner=True, uid=None
    ))
    db.add(Notice(
        title="تم استلام طلبك",
        body="سيتم تنفيذ طلبك قريبًا، ويمكنك متابعة الحالة من (طلباتي).",
        for_owner=False, uid=p.uid
    ))
    db.commit()
    return {"ok": True, "order_id": o.id}

# ---------- إنشاء طلب يدوي عام ----------
@r.post("/orders/create/manual")
def create_manual_order(p: ManualReq, db: Session = Depends(get_db)):
    # لأغراض العرض فقط: نرسل إشعارين (للمالك/المستخدم) من دون إنشاء سجل في جداول خاصة
    db.add(Notice(
        title="طلب يدوي جديد",
        body=f"{p.title} | UID={p.uid}",
        for_owner=True, uid=None
    ))
    db.add(Notice(
        title="تم استلام طلبك",
        body=f"لقد أرسلنا طلب ({p.title}) إلى المالك لمراجعته.",
        for_owner=False, uid=p.uid
    ))
    db.commit()
    return {"ok": True}

# ---------- طلبات المستخدم ----------
@r.get("/orders/my")
def my_orders(uid: str = Query(...), db: Session = Depends(get_db)):
    out = []

    # Service orders
    serv = (
        db.query(ServiceOrder)
        .filter_by(uid=uid)
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    for s in serv:
        out.append({
            "id": str(s.id),
            "title": s.service_key,
            "quantity": int(s.quantity or 0),
            "price": float(s.price or 0),
            "payload": s.link,
            "status": s.status.capitalize() if s.status else "Pending",
            "created_at": int(s.created_at.timestamp() * 1000) if s.created_at else 0
        })

    # Wallet cards (تظهر ضمن الطلبات كذلك ليتتبعها المستخدم)
    cards = (
        db.query(WalletCard)
        .filter_by(uid=uid)
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    for c in cards:
        out.append({
            "id": f"card-{c.id}",
            "title": "كارت أسيا سيل",
            "quantity": 1,
            "price": float(c.amount_usd or 0),
            "payload": c.card_number,
            "status": c.status.capitalize() if c.status else "Pending",
            "created_at": int(c.created_at.timestamp() * 1000) if c.created_at else 0
        })

    return out

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from ..database import get_db
from ..models import (
    User, Notice, ServiceOrder, WalletCard, ItunesOrder,
    PhoneTopup, PubgOrder, LudoOrder
)

r = APIRouter()

# ---- مساعدات ----
def _row(o):
    if o is None: return None
    out = {}
    for c in o.__table__.columns:
        v = getattr(o, c.name)
        if isinstance(v, datetime): v = v.isoformat()
        out[c.name] = v
    return out

# ---- Health ----
@r.get("/health")
def health():
    return {"ok": True}

# ---- Users Upsert ----
@r.post("/users/upsert")
def upsert_user(uid: str = Body(embed=True), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.add(Notice(title="مرحبًا", body="تم إنشاء حسابك.", for_owner=False, uid=uid))
        db.add(Notice(title="مستخدم جديد", body=f"UID={uid}", for_owner=True, uid=None))
    db.commit()
    return {"ok": True}

# ---- Wallet balance ----
@r.get("/wallet/balance")
def wallet_balance(uid: str, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    return {"ok": True, "balance": float(u.balance) if u else 0.0}

# ---- Submit Asiacell Card ----
@r.post("/wallet/asiacell/submit")
def wallet_asiacell_submit(uid: str = Body(embed=True), card: str = Body(embed=True), db: Session = Depends(get_db)):
    if not card.isdigit() or len(card) not in (14, 16):
        raise HTTPException(400, "invalid card")
    db.add(WalletCard(uid=uid, card_number=card, status="pending"))
    db.add(Notice(title="كارت أسيا سيل جديد", body=f"UID={uid} | Card={card}", for_owner=True, uid=None))
    db.add(Notice(title="تم استلام الكارت", body="سيقوم المالك بمراجعته قريبًا", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True}

# ---- Create Provider Order (خصم رصيد + طلب معلّق) ----
@r.post("/orders/create/provider")
def create_provider_order(
    uid: str = Body(embed=True),
    service_id: int = Body(embed=True),
    service_name: str = Body(embed=True),
    link: str = Body(embed=True),
    quantity: int = Body(embed=True),
    price: float = Body(embed=True),
    db: Session = Depends(get_db)
):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.flush()

    if float(u.balance) < float(price):
        raise HTTPException(400, "insufficient balance")

    u.balance = round(float(u.balance) - float(price), 2)
    order = ServiceOrder(
        uid=uid,
        service_key=service_name,
        service_code=int(service_id),
        link=link,
        quantity=int(quantity),
        unit_price_per_k=0.0,
        price=float(price),
        status="pending"
    )
    db.add(order)
    db.add(Notice(title="طلب خدمة جديد", body=f"{service_name} | {quantity} | ${price}", for_owner=True, uid=None))
    db.add(Notice(title="تم استلام طلبك", body="سيقوم المالك بتنفيذ الطلب قريبًا", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "order_id": order.id}

# ---- Create Manual Order (اختصرت: فقط آيتونز/الهاتف تخزين كامل؛ الباقي إشعار للمالك) ----
@r.post("/orders/create/manual")
def create_manual_order(uid: str = Body(embed=True), title: str = Body(embed=True), db: Session = Depends(get_db)):
    t = title.strip()
    if "ايتونز" in t:
        db.add(ItunesOrder(uid=uid, amount=0, status="pending"))
    elif "اثير" in t:
        db.add(PhoneTopup(uid=uid, operator="atheir", amount=0, status="pending"))
    elif "اسياسيل" in t:
        db.add(PhoneTopup(uid=uid, operator="asiacell", amount=0, status="pending"))
    elif "كورك" in t:
        db.add(PhoneTopup(uid=uid, operator="korek", amount=0, status="pending"))
    else:
        # إشعار فقط لباقي الخدمات اليدوية (ببجي/لودو) لتفادي حقول ناقصة
        db.add(Notice(title="طلب يدوي", body=f"{t} | UID={uid}", for_owner=True, uid=None))
    db.add(Notice(title="طلبك قيد المراجعة", body=f"{t}", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True}

# ---- My Orders (ترجيع مصفوفة فقط كما يتوقع التطبيق) ----
@r.get("/orders/my")
def orders_my(uid: str, db: Session = Depends(get_db)):
    out = []

    def push(title, oid, qty, price, payload, status, created):
        out.append({
            "id": str(oid),
            "title": title,
            "quantity": qty,
            "price": float(price or 0.0),
            "payload": payload or "",
            "status": status,
            "created_at": int(created.timestamp()) if isinstance(created, datetime) else created
        })

    for o in db.query(ServiceOrder).filter_by(uid=uid).order_by(ServiceOrder.created_at.desc()).all():
        push(o.service_key, o.id, o.quantity, o.price, o.link, o.status.capitalize(), o.created_at)

    for o in db.query(WalletCard).filter_by(uid=uid).order_by(WalletCard.created_at.desc()).all():
        push("كارت أسيا سيل", o.id, 1, o.amount_usd or 0.0, o.card_number, o.status.capitalize(), o.created_at)

    for o in db.query(ItunesOrder).filter_by(uid=uid).order_by(ItunesOrder.created_at.desc()).all():
        push("آيتونز", o.id, o.amount, 0.0, o.gift_code, o.status.capitalize(), o.created_at)

    for o in db.query(PhoneTopup).filter_by(uid=uid).order_by(PhoneTopup.created_at.desc()).all():
        push(f"شحن هاتف {o.operator}", o.id, o.amount, 0.0, o.code, o.status.capitalize(), o.created_at)

    for o in db.query(PubgOrder).filter_by(uid=uid).order_by(PubgOrder.created_at.desc()).all():
        push("شدات ببجي", o.id, o.pkg, 0.0, o.pubg_id or "", o.status.capitalize(), o.created_at)

    for o in db.query(LudoOrder).filter_by(uid=uid).order_by(LudoOrder.created_at.desc()).all():
        push(f"لودو {o.kind}", o.id, o.pack, 0.0, o.ludo_id or "", o.status.capitalize(), o.created_at)

    return out

# app/routers/smm.py
from fastapi import APIRouter, HTTPException, Depends, Body, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List

from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)

r = APIRouter()

def _now_ts() -> int:
    return int(datetime.utcnow().timestamp() * 1000)

# ---- Helpers ----
def _ensure_user(db: Session, uid: str) -> User:
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.commit()
        db.refresh(u)
    return u

# ====== USERS ======
@r.post("/users/upsert")
def api_upsert_user(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    if not uid:
        raise HTTPException(400, "uid required")
    _ensure_user(db, uid)
    return {"ok": True}

# ====== WALLET ======
@r.get("/wallet/balance")
def api_wallet_balance(uid: str, db: Session = Depends(get_db)):
    u = _ensure_user(db, uid)
    return {"ok": True, "balance": round(u.balance or 0.0, 2)}

@r.post("/wallet/asiacell/submit")
def api_wallet_asiacell_submit(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    card = (payload.get("card") or "").strip()
    if not uid or not card:
        raise HTTPException(400, "uid & card required")
    if not (card.isdigit() and len(card) in (14, 16)):
        raise HTTPException(400, "invalid card")
    _ensure_user(db, uid)

    rec = WalletCard(uid=uid, card_number=card, status="pending")
    db.add(rec)
    # إشعار للمستخدم + للمالك
    db.add(Notice(title="استقبال كارت أسيا سيل", body=f"تم استلام الكارت للمراجعة.", for_owner=False, uid=uid))
    db.add(Notice(title="كارت أسيا سيل جديد", body=f"UID={uid} | CARD={card}", for_owner=True, uid=None))
    db.commit()
    return {"ok": True, "id": rec.id}

# ====== ORDERS ======

# طلبات مزوّد (خصم تلقائي والطلب يذهب للمعلّقة لدى المالك للتنفيذ)
@r.post("/orders/create/provider")
def api_orders_create_provider(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    service_id = payload.get("service_id")
    service_name = (payload.get("service_name") or "").strip()
    link = (payload.get("link") or "").strip()
    quantity = int(payload.get("quantity") or 0)
    price = float(payload.get("price") or 0.0)

    if not uid or not service_id or not service_name or not link or quantity <= 0 or price <= 0:
        raise HTTPException(400, "invalid payload")

    u = _ensure_user(db, uid)
    if (u.balance or 0.0) < price:
        raise HTTPException(402, "insufficient_balance")

    u.balance = round((u.balance or 0.0) - price, 2)
    order = ServiceOrder(
        uid=uid,
        service_key=service_name,
        service_code=int(service_id),
        link=link,
        quantity=int(quantity),
        unit_price_per_k=0.0,
        price=price,
        status="pending",
    )
    db.add(u)
    db.add(order)
    db.add(Notice(title="طلبك قيد المراجعة", body=f"{service_name} | الكمية: {quantity}", for_owner=False, uid=uid))
    db.add(Notice(title="طلب خدمات معلّق", body=f"{service_name} | UID={uid} | QTY={quantity}", for_owner=True, uid=None))
    db.commit()
    return {"ok": True, "id": order.id}

# طلب يدوي (يُحفظ حسب العنوان)
@r.post("/orders/create/manual")
def api_orders_create_manual(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    title = (payload.get("title") or "").strip()
    if not uid or not title:
        raise HTTPException(400, "invalid payload")

    _ensure_user(db, uid)
    created_id = None

    # توجيه حسب العنوان
    if "ايتونز" in title:
        o = ItunesOrder(uid=uid, amount=0, status="pending")
        db.add(o); db.commit(); created_id = o.id
    elif "ببجي" in title:
        o = PubgOrder(uid=uid, pkg=0, pubg_id="", status="pending")
        db.add(o); db.commit(); created_id = o.id
    elif "لودو" in title:
        o = LudoOrder(uid=uid, kind="diamonds", pack=0, ludo_id="", status="pending")
        db.add(o); db.commit(); created_id = o.id
    else:
        # PhoneTopup كمثال لـ “كارت هاتف” يدوي
        o = PhoneTopup(uid=uid, operator="asiacell", amount=0, status="pending")
        db.add(o); db.commit(); created_id = o.id

    db.add(Notice(title="طلب يدوي قيد المراجعة", body=title, for_owner=False, uid=uid))
    db.add(Notice(title="طلب يدوي جديد", body=f"{title} | UID={uid}", for_owner=True, uid=None))
    db.commit()

    return {"ok": True, "id": created_id}

# طلباتي (دمج مبسّط)
@r.get("/orders/my")
def api_orders_my(uid: str, db: Session = Depends(get_db)):
    _ensure_user(db, uid)
    out = []

    def add(id_, title, qty, price, payload, status, created_at):
        out.append({
            "id": str(id_),
            "title": title,
            "quantity": int(qty),
            "price": float(price),
            "payload": payload or "",
            "status": status,
            "created_at": int(created_at.timestamp() * 1000)
        })

    for o in db.query(ServiceOrder).filter_by(uid=uid).order_by(ServiceOrder.created_at.desc()).all():
        add(o.id, o.service_key, o.quantity, o.price, o.link, o.status.capitalize(), o.created_at)
    for o in db.query(WalletCard).filter_by(uid=uid).order_by(WalletCard.created_at.desc()).all():
        add(o.id, "كارت أسيا سيل", 1, float(o.amount_usd or 0), o.card_number, o.status.capitalize(), o.created_at)
    for o in db.query(ItunesOrder).filter_by(uid=uid).order_by(ItunesOrder.created_at.desc()).all():
        add(o.id, "آيتونز", o.amount, 0.0, o.gift_code, o.status.capitalize(), o.created_at)
    for o in db.query(PhoneTopup).filter_by(uid=uid).order_by(PhoneTopup.created_at.desc()).all():
        add(o.id, f"كارت هاتف ({o.operator})", 1, float(o.amount or 0), o.code, o.status.capitalize(), o.created_at)
    for o in db.query(PubgOrder).filter_by(uid=uid).order_by(PubgOrder.created_at.desc()).all():
        add(o.id, f"ببجي {o.pkg}UC", 1, 0.0, o.pubg_id, o.status.capitalize(), o.created_at)
    for o in db.query(LudoOrder).filter_by(uid=uid).order_by(LudoOrder.created_at.desc()).all():
        add(o.id, f"لودو {o.kind} {o.pack}", 1, 0.0, o.ludo_id, o.status.capitalize(), o.created_at)

    return out

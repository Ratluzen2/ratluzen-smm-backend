# app/routers/smm.py
from fastapi import APIRouter, Body, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)

r = APIRouter(tags=["public"])


# ------------ أدوات مساعدة ------------
def _ensure_user(db: Session, uid: str) -> User:
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.commit()
        db.refresh(u)
    return u


# ------------ صحة + upsert ------------
@r.post("/users/upsert")
def upsert_user(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = str(payload.get("uid", "")).strip()
    if not uid:
        raise HTTPException(400, "uid required")
    _ensure_user(db, uid)
    return {"ok": True}


# ------------ رصيد العميل ------------
@r.get("/wallet/balance")
def wallet_balance(uid: str = Query(...), db: Session = Depends(get_db)):
    u = _ensure_user(db, uid)
    return {"ok": True, "balance": float(u.balance or 0.0)}


# ------------ إنشاء طلب مربوط بالمزوّد ------------
@r.post("/orders/create/provider")
def create_provider_order(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = str(payload.get("uid", "")).strip()
    service_id = payload.get("service_id")
    service_name = str(payload.get("service_name", "")).strip()
    link = str(payload.get("link", "")).strip()
    quantity = int(payload.get("quantity", 0))
    price = float(payload.get("price", 0.0))

    if not uid or not service_id or not service_name or not link or quantity <= 0 or price <= 0:
        raise HTTPException(400, "invalid payload")

    u = _ensure_user(db, uid)
    if (u.balance or 0.0) < price:
        raise HTTPException(400, "insufficient balance")

    # خصم الرصيد وإنشاء الطلب كـ pending، التنفيذ الفعلي من لوحة المالك
    u.balance = round(float(u.balance or 0.0) - price, 2)
    db.add(u)

    o = ServiceOrder(
        uid=uid,
        service_key=str(service_id),
        service_name=service_name,
        link=link,
        quantity=quantity,
        price=price,
        status="pending"
    )
    db.add(o)

    # إشعارات
    db.add(Notice(title="طلب خدمات جديد", body=f"{service_name} - {quantity}", for_owner=True, uid=None))
    db.add(Notice(title="تم استلام طلبك", body=f"{service_name} - {quantity}", for_owner=False, uid=uid))

    db.commit()
    return {"ok": True, "order_id": o.id}


# ------------ طلب يدوي عام (للبطاقات/لودو/ببجي.. عبر الواجهة) ------------
@r.post("/orders/create/manual")
def create_manual(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = str(payload.get("uid", "")).strip()
    title = str(payload.get("title", "")).strip()
    if not uid or not title:
        raise HTTPException(400, "uid/title required")

    _ensure_user(db, uid)
    db.add(Notice(title=f"طلب يدوي جديد", body=f"{title} من UID={uid}", for_owner=True, uid=None))
    db.add(Notice(title="تم استلام طلبك", body=title, for_owner=False, uid=uid))
    db.commit()
    return {"ok": True}


# ------------ كارت أسيا سيل من المستخدم ------------
@r.post("/wallet/asiacell/submit")
def submit_asiacell(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = str(payload.get("uid", "")).strip()
    card = str(payload.get("card", "")).strip()
    if not uid or not card or len(card) not in (14, 16) or not card.isdigit():
        raise HTTPException(400, "invalid card")

    _ensure_user(db, uid)
    w = WalletCard(uid=uid, card_number=card, status="pending")
    db.add(w)
    db.add(Notice(title="كارت أسيا سيل جديد", body=f"UID={uid} | كارت: {card}", for_owner=True, uid=None))
    db.add(Notice(title="تم استلام كارتك", body="سيتم مراجعته من المالك", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "card_id": w.id}


# ------------ طلباتي (يُجمع من عدّة جداول) ------------
@r.get("/orders/my")
def my_orders(uid: str = Query(...), db: Session = Depends(get_db)):
    _ensure_user(db, uid)

    out: List[Dict[str, Any]] = []

    for o in db.query(ServiceOrder).filter_by(uid=uid).order_by(ServiceOrder.created_at.desc()).all():
        out.append({
            "id": str(o.id),
            "title": o.service_name,
            "quantity": o.quantity,
            "price": float(o.price),
            "payload": o.link,
            "status": o.status.capitalize(),
            "created_at": int(o.created_at.timestamp() * 1000)
        })

    for i in db.query(ItunesOrder).filter_by(uid=uid).order_by(ItunesOrder.created_at.desc()).all():
        out.append({
            "id": f"itunes:{i.id}",
            "title": "طلب آيتونز",
            "quantity": 1, "price": 0.0,
            "payload": i.gift_code or "",
            "status": i.status.capitalize(),
            "created_at": int(i.created_at.timestamp() * 1000)
        })

    for t in db.query(PhoneTopup).filter_by(uid=uid).order_by(PhoneTopup.created_at.desc()).all():
        out.append({
            "id": f"phone:{t.id}",
            "title": "رصيد هاتف",
            "quantity": 1, "price": 0.0,
            "payload": t.code or "",
            "status": t.status.capitalize(),
            "created_at": int(t.created_at.timestamp() * 1000)
        })

    for p in db.query(PubgOrder).filter_by(uid=uid).order_by(PubgOrder.created_at.desc()).all():
        out.append({
            "id": f"pubg:{p.id}",
            "title": f"شدات ببجي ({p.pkg})",
            "quantity": p.pkg, "price": 0.0,
            "payload": "",
            "status": p.status.capitalize(),
            "created_at": int(p.created_at.timestamp() * 1000)
        })

    for l in db.query(LudoOrder).filter_by(uid=uid).order_by(LudoOrder.created_at.desc()).all():
        out.append({
            "id": f"ludo:{l.id}",
            "title": f"لودو: {l.kind} - {l.pack}",
            "quantity": 1, "price": 0.0,
            "payload": "",
            "status": l.status.capitalize(),
            "created_at": int(l.created_at.timestamp() * 1000)
        })

    # يمكن ترتيب الناتج حسب التاريخ
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return out

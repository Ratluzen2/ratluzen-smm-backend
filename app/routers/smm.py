from fastapi import APIRouter, HTTPException, Body, Query, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder
)

r = APIRouter()

def _ensure_user(db: Session, uid: str) -> User:
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.commit()
        db.refresh(u)
    return u

@r.post("/users/upsert")
def upsert_uid(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    if not uid:
        raise HTTPException(400, "uid required")
    _ensure_user(db, uid)
    return {"ok": True}

@r.get("/wallet/balance")
def wallet_balance(uid: str, db: Session = Depends(get_db)):
    u = _ensure_user(db, uid)
    return {"ok": True, "balance": round(u.balance, 2)}

@r.post("/wallet/asiacell/submit")
def submit_asiacell_card(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    card = (payload.get("card") or "").strip()
    if not uid or not card:
        raise HTTPException(400, "uid/card required")
    if not (len(card) in (14, 16) and card.isdigit()):
        raise HTTPException(400, "card must be 14 or 16 digits")
    _ensure_user(db, uid)
    wc = WalletCard(uid=uid, card_number=card, status="pending")
    db.add(wc)
    db.commit()
    return {"ok": True}

@r.post("/orders/create/provider")
def create_provider_order(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    service_id = int(payload.get("service_id") or 0)
    service_name = (payload.get("service_name") or "SERVICE").strip()
    link = (payload.get("link") or "").strip()
    quantity = int(payload.get("quantity") or 0)
    price = float(payload.get("price") or 0.0)
    unit_per_k = float(payload.get("unit_price_per_k") or 0.0) or (price * 1000.0 / max(1, quantity))

    if not uid or not service_id or not link or quantity <= 0 or price <= 0:
        raise HTTPException(400, "invalid payload")

    u = _ensure_user(db, uid)
    if u.balance < price:
        raise HTTPException(400, "insufficient balance")

    # خصم الرصيد الآن، التنفيذ فعليًا سيتم عند موافقة المالك
    u.balance = round(u.balance - price, 2)
    order = ServiceOrder(
        uid=uid, service_key=service_name, service_code=service_id,
        link=link, quantity=quantity, unit_price_per_k=unit_per_k,
        price=price, status="pending"
    )
    db.add(u)
    db.add(order)
    db.commit()
    return {"ok": True, "order_id": order.id}

@r.post("/orders/create/manual")
def create_manual(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    title = (payload.get("title") or "").strip()
    if not uid or not title:
        raise HTTPException(400, "uid/title required")
    _ensure_user(db, uid)

    t = title.replace(" ", "")
    if "ايتونز" in t or "itunes" in t.lower():
        db.add(ItunesOrder(uid=uid, amount=0))
    elif "اسياسيل" in t:
        db.add(PhoneTopup(uid=uid, operator="asiacell", amount=0))
    elif "اتير" in t or "اثير" in t:
        db.add(PhoneTopup(uid=uid, operator="atheir", amount=0))
    elif "كورك" in t:
        db.add(PhoneTopup(uid=uid, operator="korek", amount=0))
    elif "ببجي" in t:
        db.add(PubgOrder(uid=uid, pkg=0, pubg_id=""))
    elif "لudo" in t.lower() or "لودو" in t:
        db.add(LudoOrder(uid=uid, kind="diamonds", pack=0, ludo_id=""))
    else:
        # كطلب عام: نخزّنه كطلب خدمة اسم فقط بدون مزوّد
        db.add(ServiceOrder(uid=uid, service_key=title, service_code=0, link="", quantity=0,
                            unit_price_per_k=0.0, price=0.0, status="pending"))
    db.commit()
    return {"ok": True}

@r.get("/orders/my")
def my_orders(uid: str, db: Session = Depends(get_db)):
    out = []

    for o in db.query(ServiceOrder).filter_by(uid=uid).order_by(ServiceOrder.created_at.desc()).limit(200):
        out.append({
            "id": f"svc:{o.id}",
            "title": o.service_key,
            "quantity": o.quantity,
            "price": o.price,
            "payload": o.link,
            "status": o.status.capitalize(),
            "created_at": int(o.created_at.timestamp()*1000) if o.created_at else 0
        })
    for c in db.query(WalletCard).filter_by(uid=uid).order_by(WalletCard.created_at.desc()).limit(200):
        out.append({
            "id": f"card:{c.id}",
            "title": "Asiacell Card",
            "quantity": 1,
            "price": 0.0,
            "payload": c.card_number,
            "status": c.status.capitalize(),
            "created_at": int(c.created_at.timestamp()*1000) if c.created_at else 0
        })
    for it in db.query(ItunesOrder).filter_by(uid=uid).order_by(ItunesOrder.created_at.desc()).limit(200):
        out.append({
            "id": f"itunes:{it.id}",
            "title": "iTunes",
            "quantity": 1,
            "price": float(it.amount or 0),
            "payload": it.gift_code or "",
            "status": it.status.capitalize(),
            "created_at": int(it.created_at.timestamp()*1000) if it.created_at else 0
        })
    for ph in db.query(PhoneTopup).filter_by(uid=uid).order_by(PhoneTopup.created_at.desc()).limit(200):
        out.append({
            "id": f"phone:{ph.id}",
            "title": f"Phone {ph.operator}",
            "quantity": 1,
            "price": float(ph.amount or 0),
            "payload": ph.code or "",
            "status": ph.status.capitalize(),
            "created_at": int(ph.created_at.timestamp()*1000) if ph.created_at else 0
        })
    for pb in db.query(PubgOrder).filter_by(uid=uid).order_by(PubgOrder.created_at.desc()).limit(200):
        out.append({
            "id": f"pubg:{pb.id}",
            "title": "PUBG UC",
            "quantity": pb.pkg,
            "price": 0.0,
            "payload": pb.pubg_id,
            "status": pb.status.capitalize(),
            "created_at": int(pb.created_at.timestamp()*1000) if pb.created_at else 0
        })
    for ld in db.query(LudoOrder).filter_by(uid=uid).order_by(LudoOrder.created_at.desc()).limit(200):
        out.append({
            "id": f"ludo:{ld.id}",
            "title": f"Ludo {ld.kind}",
            "quantity": ld.pack,
            "price": 0.0,
            "payload": ld.ludo_id,
            "status": ld.status.capitalize(),
            "created_at": int(ld.created_at.timestamp()*1000) if ld.created_at else 0
        })

    # الأحدث أولًا
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return out

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List

from ..database import get_db
from ..models import User, ServiceOrder, WalletCard, Notice, ItunesOrder, PhoneTopup, PubgOrder, LudoOrder

r = APIRouter()

def _row(obj):
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    return out

@r.post("/users/upsert")
def upsert_user(uid: str = Body(..., embed=True), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.add(Notice(title="مرحبًا", body="تم إنشاء حسابك.", for_owner=False, uid=uid))
        db.add(Notice(title="مستخدم جديد", body=f"UID={uid} اشترك للتو.", for_owner=True))
        db.commit()
    return {"ok": True}

@r.get("/wallet/balance")
def wallet_balance(uid: str, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u); db.commit()
    return {"balance": u.balance}

@r.post("/wallet/asiacell/submit")
def asiacell_submit(uid: str = Body(...), card: str = Body(...), db: Session = Depends(get_db)):
    digits = "".join([d for d in card if d.isdigit()])
    if len(digits) not in (14, 16):
        raise HTTPException(400, "invalid card")
    wc = WalletCard(uid=uid, card_number=digits, status="pending")
    db.add(wc)
    db.add(Notice(
        title="كارت أسيا سيل جديد",
        body=f"UID={uid} | كارت={digits}",
        for_owner=True
    ))
    db.add(Notice(
        title="استلمنا كارتك",
        body=f"تم إرسال كارت أسيا سيل للمراجعة",
        for_owner=False,
        uid=uid
    ))
    db.commit()
    return {"ok": True, "id": wc.id}

@r.post("/orders/create/provider")
def create_provider_order(
    uid: str = Body(...),
    service_id: int = Body(...),
    service_name: str = Body(...),
    link: str = Body(...),
    quantity: int = Body(...),
    price: float = Body(...),
    db: Session = Depends(get_db)
):
    u = db.query(User).filter_by(uid=uid).first()
    if not u: u = User(uid=uid, balance=0.0)
    if u.balance < price:
        raise HTTPException(400, "insufficient balance")

    # نخصم السعر الآن، وإن رُفض الطلب من لوحة المالك نردّه
    u.balance = round(u.balance - float(price), 2)
    order = ServiceOrder(
        uid=uid,
        service_key=service_name,
        service_code=service_id,
        link=link,
        quantity=quantity,
        unit_price_per_k=price * 1000.0 / max(quantity, 1),
        price=price,
        status="pending"
    )
    db.add(u); db.add(order)
    db.add(Notice(title="طلب خدمات معلّق", body=f"{service_name} | {quantity}", for_owner=True))
    db.add(Notice(title="طلبك قيد المراجعة", body=f"{service_name} | {quantity}", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "id": order.id}

@r.post("/orders/create/manual")
def create_manual(uid: str = Body(...), title: str = Body(...), db: Session = Depends(get_db)):
    t = title.strip()
    created_id = None
    if "ايتونز" in t or "itunes" in t.lower():
        it = ItunesOrder(uid=uid, amount=0, status="pending")
        db.add(it); db.commit(); created_id = it.id
    elif any(k in t for k in ["أثير", "اثير", "asiacell", "اسياسيل", "زين", "korek", "كورك"]):
        op = "asiacell" if any(k in t for k in ["اسياسيل","asiacell"]) else ("atheir" if any(k in t for k in ["أثير","اثير"]) else "korek")
        ph = PhoneTopup(uid=uid, operator=op, amount=0, status="pending")
        db.add(ph); db.commit(); created_id = ph.id
    elif "ببجي" in t or "pubg" in t.lower():
        o = PubgOrder(uid=uid, pkg=60, pubg_id="0", status="pending")
        db.add(o); db.commit(); created_id = o.id
    elif "لودو" in t or "ludo" in t.lower():
        o = LudoOrder(uid=uid, kind="diamonds", pack=100, ludo_id="0", status="pending")
        db.add(o); db.commit(); created_id = o.id
    else:
        db.add(Notice(title="طلب يدوي", body=f"{t} | UID={uid}", for_owner=True)); db.commit()
    db.add(Notice(title="طلبك قيد المراجعة", body=t, for_owner=False, uid=uid)); db.commit()
    return {"ok": True, "id": created_id}

@r.get("/orders/my")
def my_orders(uid: str, db: Session = Depends(get_db)) -> list[dict]:
    out: list[dict] = []

    for o in db.query(ServiceOrder).filter_by(uid=uid).order_by(ServiceOrder.created_at.desc()).all():
        out.append({
            "id": str(o.id),
            "title": o.service_key,
            "quantity": o.quantity,
            "price": o.price,
            "payload": o.link,
            "status": o.status.capitalize(),
            "created_at": int(o.created_at.timestamp() * 1000)
        })

    for it in db.query(ItunesOrder).filter_by(uid=uid).order_by(ItunesOrder.created_at.desc()).all():
        out.append({
            "id": f"itunes-{it.id}",
            "title": "طلب آيتونز",
            "quantity": it.amount,
            "price": 0.0,
            "payload": it.gift_code or "",
            "status": it.status.capitalize(),
            "created_at": int(it.created_at.timestamp() * 1000)
        })

    for ph in db.query(PhoneTopup).filter_by(uid=uid).order_by(PhoneTopup.created_at.desc()).all():
        out.append({
            "id": f"phone-{ph.id}",
            "title": f"شحن هاتف ({ph.operator})",
            "quantity": ph.amount,
            "price": 0.0,
            "payload": ph.code or "",
            "status": ph.status.capitalize(),
            "created_at": int(ph.created_at.timestamp() * 1000)
        })

    for pb in db.query(PubgOrder).filter_by(uid=uid).order_by(PubgOrder.created_at.desc()).all():
        out.append({
            "id": f"pubg-{pb.id}",
            "title": f"شدات ببجي {pb.pkg}",
            "quantity": pb.pkg,
            "price": 0.0,
            "payload": pb.pubg_id,
            "status": pb.status.capitalize(),
            "created_at": int(pb.created_at.timestamp() * 1000)
        })

    for ld in db.query(LudoOrder).filter_by(uid=uid).order_by(LudoOrder.created_at.desc()).all():
        out.append({
            "id": f"ludo-{ld.id}",
            "title": f"لودو {ld.kind} {ld.pack}",
            "quantity": ld.pack,
            "price": 0.0,
            "payload": ld.ludo_id,
            "status": ld.status.capitalize(),
            "created_at": int(ld.created_at.timestamp() * 1000)
        })

    return out

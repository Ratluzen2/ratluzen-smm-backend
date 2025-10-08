import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Order, CardSubmission, ItunesOrder, PubgOrder, LudoOrder
from ..providers.smm_client import SMMClient

router = APIRouter(prefix="/api", tags=["public"])

# /health
@router.get("/health")
def health():
    return {"ok": True}

# --- users ---
@router.post("/users/upsert")
def users_upsert(payload: dict, db: Session = Depends(get_db)):
    uid = str(payload.get("uid", "")).strip()
    if not uid: raise HTTPException(400, "uid required")
    u = db.query(User).filter(User.uid == uid).first()
    if not u:
        u = User(uid=uid, balance=0.0, is_banned=False)
        db.add(u); db.commit()
    return {"ok": True, "uid": uid}

# --- wallet ---
@router.get("/wallet/balance")
def wallet_balance(uid: str = Query(...), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.uid == uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u); db.commit()
    return {"balance": float(u.balance or 0.0)}

@router.post("/wallet/asiacell/submit")
def wallet_asiacell_submit(payload: dict, db: Session = Depends(get_db)):
    uid = str(payload.get("uid", "")).strip()
    card = str(payload.get("card", "")).strip()
    if not uid or not card: raise HTTPException(400, "uid/card required")
    sub = CardSubmission(uid=uid, card_number=card)
    db.add(sub); db.commit()
    return {"ok": True, "id": sub.id}

# --- orders ---
@router.post("/orders/create/provider")
async def create_provider_order(payload: dict, db: Session = Depends(get_db)):
    uid = str(payload.get("uid", "")).strip()
    service_id = int(payload.get("service_id", 0))
    service_name = str(payload.get("service_name", ""))
    link = str(payload.get("link", ""))
    quantity = int(payload.get("quantity", 0))
    price = float(payload.get("price", 0.0))
    if not uid or service_id <= 0 or quantity <= 0: raise HTTPException(400, "bad request")

    u = db.query(User).filter(User.uid == uid).first()
    if not u:
        u = User(uid=uid, balance=0.0); db.add(u); db.commit()
    if (u.balance or 0.0) < price:
        raise HTTPException(402, "insufficient balance")

    # اطلب من مزود SMM (يمكنك تعطيل هذه الخطوة لو أردت)
    panel_id = None
    try:
        created = await SMMClient().add_order(service=service_id, link=link, quantity=quantity)
        panel_id = int(created.get("order"))
    except Exception:
        panel_id = None  # لا توقف التطبيق لو فشل المزود

    u.balance = (u.balance or 0.0) - price  # خصم السعر
    oid = str(uuid.uuid4())
    order = Order(
        id=oid, uid=uid, title=service_name or f"Service {service_id}", quantity=quantity,
        price=price, payload=link, status="Pending", kind="provider", panel_order_id=panel_id
    )
    db.add(order); db.commit()
    return {"ok": True, "order_id": oid}

@router.post("/orders/create/manual")
def create_manual_order(payload: dict, db: Session = Depends(get_db)):
    uid = str(payload.get("uid", "")).strip()
    title = str(payload.get("title", "")).strip()
    if not uid or not title: raise HTTPException(400, "uid/title required")

    # نحاول تصنيف الطلب اليدوي إلى جداول خاصة إن أمكن
    low = title.lower()
    if "ايتونز" in title or "itunes" in low:
        it = ItunesOrder(uid=uid, amount=0, status="Pending")
        db.add(it); db.commit()
    elif "ببجي" in title or "pubg" in low:
        it = PubgOrder(uid=uid, pkg=0, pubg_id="", status="Pending")
        db.add(it); db.commit()
    elif "لودو" in title or "ludo" in low:
        it = LudoOrder(uid=uid, kind="diamonds", pack=0, ludo_id="", status="Pending")
        db.add(it); db.commit()

    # أيضاً سجّل كـOrder للعرض في /orders/my
    oid = str(uuid.uuid4())
    o = Order(id=oid, uid=uid, title=title, quantity=0, price=0.0, payload="", status="Pending", kind="manual")
    db.add(o); db.commit()
    return {"ok": True, "order_id": oid}

@router.get("/orders/my")
def my_orders(uid: str = "", db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.uid==uid).order_by(Order.created_at.desc()).limit(200).all()
    return [
        {
            "id": o.id, "title": o.title, "quantity": o.quantity, "price": o.price,
            "payload": o.payload or "", "status": o.status, "created_at": int(o.created_at.timestamp()*1000)
        } for o in q
    ]

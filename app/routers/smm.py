from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ..database import SessionLocal
from ..models import User, Order
from datetime import datetime, timezone

r = APIRouter(tags=["public"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UpsertUserIn(BaseModel):
    uid: str = Field(min_length=1, max_length=32)

@r.post("/users/upsert")
def upsert_user(p: UpsertUserIn, db: Session = Depends(get_db)):
    u = db.get(User, p.uid)
    if not u:
        u = User(uid=p.uid, balance=0)
        db.add(u)
    u.last_seen = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}

@r.get("/wallet/balance")
def wallet_balance(uid: str, db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        u = User(uid=uid, balance=0)
        db.add(u)
        db.commit()
        db.refresh(u)
    return {"balance": float(u.balance or 0)}

class ProviderOrderIn(BaseModel):
    uid: str
    service_id: int
    service_name: str
    link: str
    quantity: int
    price: float

@r.post("/orders/create/provider")
def create_provider_order(p: ProviderOrderIn, db: Session = Depends(get_db)):
    u = db.get(User, p.uid)
    if not u:
        u = User(uid=p.uid, balance=0)
        db.add(u)
        db.flush()
    # التحقق والخصم الذري
    bal = float(u.balance or 0)
    if bal < p.price:
        raise HTTPException(400, "INSUFFICIENT_BALANCE")
    u.balance = bal - float(p.price)
    o = Order(
        uid=p.uid,
        type="provider",
        title=p.service_name,
        service_id=p.service_id,
        service_name=p.service_name,
        link=p.link,
        quantity=p.quantity,
        price=p.price,
        status="Pending",
    )
    db.add(o)
    db.commit()
    return {"ok": True, "id": str(o.id)}

class ManualOrderIn(BaseModel):
    uid: str
    title: str

@r.post("/orders/create/manual")
def create_manual_order(p: ManualOrderIn, db: Session = Depends(get_db)):
    if not db.get(User, p.uid):
        db.add(User(uid=p.uid, balance=0))
        db.flush()
    o = Order(uid=p.uid, type="manual", title=p.title, price=0, status="Pending")
    db.add(o)
    db.commit()
    return {"ok": True, "id": str(o.id)}

class AsiacellCardIn(BaseModel):
    uid: str
    card: str

@r.post("/wallet/asiacell/submit")
def submit_asiacell_card(p: AsiacellCardIn, db: Session = Depends(get_db)):
    if len("".join([c for c in p.card if c.isdigit()])) not in (14, 16):
        raise HTTPException(400, "INVALID_CARD")
    if not db.get(User, p.uid):
        db.add(User(uid=p.uid, balance=0))
        db.flush()
    o = Order(uid=p.uid, type="card", title="كارت أسيا سيل", payload=p.card, price=0, status="Pending")
    db.add(o)
    db.commit()
    return {"ok": True, "id": str(o.id)}

@r.get("/orders/my")
def my_orders(uid: str, db: Session = Depends(get_db)):
    q = db.execute(select(Order).where(Order.uid == uid).order_by(Order.created_at.desc())).scalars().all()
    res = []
    for o in q:
        res.append({
            "id": str(o.id),
            "title": o.title,
            "quantity": o.quantity,
            "price": float(o.price or 0),
            "payload": o.payload or (o.link or ""),
            "status": o.status,
            "created_at": int(o.created_at.timestamp() * 1000),
        })
    return res

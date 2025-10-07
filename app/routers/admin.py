import os
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ..database import SessionLocal
from ..models import User, Order
from uuid import UUID

r = APIRouter(tags=["admin"])

ADMIN_PASS = os.getenv("ADMIN_PASS", "2000")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_admin(x_admin_pass: str | None):
    if not x_admin_pass or x_admin_pass != ADMIN_PASS:
        raise HTTPException(401, "UNAUTHORIZED")

# ======== PENDING LISTS ========
def pending_list(db: Session, typ: str):
    rows = db.execute(
        select(Order).where(Order.type == typ, Order.status == "Pending").order_by(Order.created_at.desc())
    ).scalars().all()
    return [
        {
            "id": str(o.id),
            "uid": o.uid,
            "title": o.title,
            "quantity": o.quantity,
            "price": float(o.price or 0),
            "link": o.link,
            "card": o.payload if typ == "card" else None,
            "gift_code": o.payload if typ == "itunes" else None,
            "created_at": int(o.created_at.timestamp() * 1000),
        } for o in rows
    ]

@r.get("/admin/pending/services")
def admin_pending_services(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass); return pending_list(db, "provider")

@r.get("/admin/pending/cards")
def admin_pending_cards(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass); return pending_list(db, "card")

@r.get("/admin/pending/itunes")
def admin_pending_itunes(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass); return pending_list(db, "itunes")

@r.get("/admin/pending/pubg")
def admin_pending_pubg(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass); return pending_list(db, "pubg")

@r.get("/admin/pending/ludo")
def admin_pending_ludo(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass); return pending_list(db, "ludo")

# ======== ACTIONS ========
@r.post("/admin/pending/services/{oid}/approve")
def services_approve(oid: UUID, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    o = db.get(Order, oid);  _404_if(o, "ORDER_NOT_FOUND")
    if o.type != "provider" or o.status != "Pending": _400("INVALID_STATE")
    o.status = "Done"
    db.commit()
    return {"ok": True}

@r.post("/admin/pending/services/{oid}/reject")
def services_reject(oid: UUID, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    o = db.get(Order, oid);  _404_if(o, "ORDER_NOT_FOUND")
    if o.type != "provider" or o.status != "Pending": _400("INVALID_STATE")
    # رد المبلغ للمستخدم
    u = db.get(User, o.uid)
    u.balance = float(u.balance or 0) + float(o.price or 0)
    o.status = "Rejected"
    db.commit()
    return {"ok": True}

class AmountIn(BaseModel):
    amount_usd: float

@r.post("/admin/pending/cards/{oid}/accept")
def cards_accept(oid: UUID, p: AmountIn, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    o = db.get(Order, oid);  _404_if(o, "ORDER_NOT_FOUND")
    if o.type != "card" or o.status != "Pending": _400("INVALID_STATE")
    u = db.get(User, o.uid)
    u.balance = float(u.balance or 0) + float(p.amount_usd)
    o.price = float(p.amount_usd)
    o.status = "Done"
    db.commit()
    return {"ok": True}

@r.post("/admin/pending/cards/{oid}/reject")
def cards_reject(oid: UUID, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    o = db.get(Order, oid);  _404_if(o, "ORDER_NOT_FOUND")
    if o.type != "card" or o.status != "Pending": _400("INVALID_STATE")
    o.status = "Rejected"
    db.commit()
    return {"ok": True}

class GiftIn(BaseModel):
    gift_code: str

@r.post("/admin/pending/itunes/{oid}/deliver")
def itunes_deliver(oid: UUID, p: GiftIn, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    o = db.get(Order, oid);  _404_if(o, "ORDER_NOT_FOUND")
    if o.type != "itunes" or o.status != "Pending": _400("INVALID_STATE")
    o.payload = p.gift_code
    o.status = "Done"
    db.commit()
    return {"ok": True}

@r.post("/admin/pending/itunes/{oid}/reject")
def itunes_reject(oid: UUID, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    o = db.get(Order, oid);  _404_if(o, "ORDER_NOT_FOUND")
    if o.type != "itunes" or o.status != "Pending": _400("INVALID_STATE")
    o.status = "Rejected"
    db.commit()
    return {"ok": True}

@r.post("/admin/pending/pubg/{oid}/deliver")
def pubg_deliver(oid: UUID, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    _mark_done(db, oid, expect="pubg"); return {"ok": True}

@r.post("/admin/pending/pubg/{oid}/reject")
def pubg_reject(oid: UUID, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    _mark_reject(db, oid, expect="pubg"); return {"ok": True}

@r.post("/admin/pending/ludo/{oid}/deliver")
def ludo_deliver(oid: UUID, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    _mark_done(db, oid, expect="ludo"); return {"ok": True}

@r.post("/admin/pending/ludo/{oid}/reject")
def ludo_reject(oid: UUID, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    _mark_reject(db, oid, expect="ludo"); return {"ok": True}

def _mark_done(db: Session, oid: UUID, expect: str):
    o = db.get(Order, oid);  _404_if(o, "ORDER_NOT_FOUND")
    if o.type != expect or o.status != "Pending": _400("INVALID_STATE")
    o.status = "Done"; db.commit()

def _mark_reject(db: Session, oid: UUID, expect: str):
    o = db.get(Order, oid);  _404_if(o, "ORDER_NOT_FOUND")
    if o.type != expect or o.status != "Pending": _400("INVALID_STATE")
    o.status = "Rejected"; db.commit()

def _404_if(obj, msg):
    if not obj:
        raise HTTPException(404, msg)

def _400(msg):
    raise HTTPException(400, msg)

# ======== WALLET OPS ========
class WalletIn(BaseModel):
    amount: float

@r.post("/admin/users/{uid}/topup")
def admin_topup(uid: str, p: WalletIn, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    u = db.get(User, uid)
    if not u: u = User(uid=uid, balance=0); db.add(u); db.flush()
    u.balance = float(u.balance or 0) + float(p.amount)
    db.commit()
    return {"ok": True, "balance": float(u.balance)}

@r.post("/admin/users/{uid}/deduct")
def admin_deduct(uid: str, p: WalletIn, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    u = db.get(User, uid)
    if not u: _400("USER_NOT_FOUND")
    bal = float(u.balance or 0)
    if bal < p.amount: _400("INSUFFICIENT_BALANCE")
    u.balance = bal - float(p.amount)
    db.commit()
    return {"ok": True, "balance": float(u.balance)}

# ======== STATS / PROVIDER ========
@r.get("/admin/users/count")
def admin_users_count(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    total = db.execute(select(func.count(User.uid))).scalar() or 0
    # نشط خلال ساعة: last_seen >= now-1h
    from datetime import datetime, timezone, timedelta
    active = db.execute(
        select(func.count(User.uid)).where(User.last_seen >= datetime.now(timezone.utc) - timedelta(hours=1))
    ).scalar() or 0
    return {"count": int(total), "active_hour": int(active)}

@r.get("/admin/users/balances")
def admin_users_balances(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    rows = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    total = sum(float(r.balance or 0) for r in rows)
    return {
        "total": float(total),
        "list": [{"uid": r.uid, "balance": float(r.balance or 0), "is_banned": bool(r.is_banned)} for r in rows]
    }

@r.get("/admin/provider/balance")
def admin_provider_balance(x_admin_pass: str | None = Header(default=None)):
    check_admin(x_admin_pass)
    # Stub ثابت — اربطه بمزوّدك لاحقًا
    return {"balance": 0.0}

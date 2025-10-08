# app/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)
from ..providers.smm_client import provider_add_order, provider_balance

r = APIRouter(prefix="/admin")

# ---------- Helpers ----------
def _ms(ts: Optional[datetime]) -> int:
    if not ts: return int(datetime.utcnow().timestamp() * 1000)
    try: return int(ts.timestamp() * 1000)
    except: return int(datetime.utcnow().timestamp() * 1000)

def _add_owner_notice(db: Session, title: str, body: str):
    db.add(Notice(title=title, body=body, for_owner=True, uid=None))

def _add_user_notice(db: Session, uid: str, title: str, body: str):
    db.add(Notice(title=title, body=body, for_owner=False, uid=uid))

def _guard_accepts(p: Optional[str]) -> bool:
    # يقبل دومًا 2000 كحلّ طوارئ + المتغير ADMIN_PASSWORD من الإعدادات
    return (p or "").strip() in {str(settings.ADMIN_PASSWORD or ""), "2000"}

def guard(
    x1: Optional[str] = Header(default=None, alias="x-admin-pass"),
    x2: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    key: Optional[str] = Query(default=None),
):
    if not _guard_accepts(x1 or x2 or key):
        raise HTTPException(401, "unauthorized")

# ---------- Login ----------
@r.post("/login")
def admin_login(
    password: Optional[str] = Body(default=None),
    x1: Optional[str] = Header(default=None, alias="x-admin-pass"),
    x2: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    key: Optional[str] = Query(default=None),
):
    pwd = (password or x1 or x2 or key or "").strip()
    if not _guard_accepts(pwd):
        raise HTTPException(401, "unauthorized")
    return {"token": pwd}

# ---------- Pending lists (Array مباشرة) ----------
@r.get("/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)):
    lst = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.status == "pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(o.id),
            "title": f"{o.service_key or 'خدمة'} (#{o.service_code})",
            "quantity": int(o.quantity or 0),
            "price": float(o.price or 0.0),
            "payload": o.link,
            "status": "Pending",
            "created_at": _ms(o.created_at),
        } for o in lst
    ]

@r.get("/pending/itunes", dependencies=[Depends(guard)])
def pending_itunes(db: Session = Depends(get_db)):
    lst = (
        db.query(ItunesOrder)
        .filter(ItunesOrder.status == "pending")
        .order_by(ItunesOrder.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(o.id),
            "title": f"iTunes ${o.amount}",
            "quantity": int(o.amount or 0),
            "price": float(o.amount or 0.0),
            "payload": "",
            "status": "Pending",
            "created_at": _ms(o.created_at),
        } for o in lst
    ]

@r.get("/pending/topups", dependencies=[Depends(guard)])
def pending_topups(db: Session = Depends(get_db)):
    lst = (
        db.query(WalletCard)
        .filter(WalletCard.status == "pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(o.id),
            "title": f"Asiacell Card • UID={o.uid}",
            "quantity": 1,
            "price": 0.0,
            "payload": o.card_number,  # يظهر للمالك للنسخ
            "status": "Pending",
            "created_at": _ms(o.created_at),
        } for o in lst
    ]

# Alias لأسماء قديمة محتملة داخل APK قديم
@r.get("/pending/cards", dependencies=[Depends(guard)])
def pending_cards_alias(db: Session = Depends(get_db)):
    return pending_topups(db)

@r.get("/pending/pubg", dependencies=[Depends(guard)])
def pending_pubg(db: Session = Depends(get_db)):
    lst = (
        db.query(PubgOrder)
        .filter(PubgOrder.status == "pending")
        .order_by(PubgOrder.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(o.id),
            "title": f"PUBG {o.pkg} UC • {o.pubg_id}",
            "quantity": int(o.pkg or 0),
            "price": 0.0,
            "payload": o.pubg_id,
            "status": "Pending",
            "created_at": _ms(o.created_at),
        } for o in lst
    ]

@r.get("/pending/ludo", dependencies=[Depends(guard)])
def pending_ludo(db: Session = Depends(get_db)):
    lst = (
        db.query(LudoOrder)
        .filter(LudoOrder.status == "pending")
        .order_by(LudoOrder.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(o.id),
            "title": f"Ludo {o.kind} {o.pack} • {o.ludo_id}",
            "quantity": int(o.pack or 0),
            "price": 0.0,
            "payload": o.ludo_id,
            "status": "Pending",
            "created_at": _ms(o.created_at),
        } for o in lst
    ]

# ---------- Actions ----------
def _find_any_pending(db: Session, oid: int):
    x = db.get(ServiceOrder, oid)
    if x and x.status == "pending": return ("service", x)
    x = db.get(WalletCard, oid)
    if x and x.status == "pending": return ("wallet", x)
    x = db.get(ItunesOrder, oid)
    if x and x.status == "pending": return ("itunes", x)
    x = db.get(PhoneTopup, oid)
    if x and x.status == "pending": return ("phone", x)
    x = db.get(PubgOrder, oid)
    if x and x.status == "pending": return ("pubg", x)
    x = db.get(LudoOrder, oid)
    if x and x.status == "pending": return ("ludo", x)
    return (None, None)

@r.post("/orders/approve", dependencies=[Depends(guard)])
def orders_approve(payload: dict = Body(...), db: Session = Depends(get_db)):
    oid = int(str(payload.get("order_id", "0")))
    kind, obj = _find_any_pending(db, oid)
    if not kind: raise HTTPException(404, "order not found or not pending")

    if kind == "service":
        # إرسال فعلي للمزوّد
        resp = provider_add_order(obj.service_key, obj.link, obj.quantity)
        if not resp.get("ok"):
            raise HTTPException(502, resp.get("error", "provider error"))
        obj.status = "processing"
        obj.provider_order_id = resp["orderId"]
        db.add(obj)
        _add_user_notice(db, obj.uid, "تم تنفيذ طلبك", f"أُرسل للمزوّد. رقم المزود: {obj.provider_order_id}")
        _add_owner_notice(db, "تنفيذ خدمة", f"Order #{obj.id} -> Provider {obj.provider_order_id}")
        db.commit()
        return {"ok": True, "id": obj.id, "provider_order_id": obj.provider_order_id}

    if kind == "wallet":
        obj.status = "accepted"
        db.add(obj)
        _add_user_notice(db, obj.uid, "تم استلام كارتك", "سيتم شحن رصيدك قريبًا.")
        _add_owner_notice(db, "قبول كارت", f"UID={obj.uid} | Card={obj.card_number}")
        db.commit()
        return {"ok": True, "id": obj.id}

    # بقية الأنواع: تسليم بسيط
    obj.status = "delivered"
    db.add(obj)
    uid = getattr(obj, "uid", None)
    if uid:
        _add_user_notice(db, uid, "تم التنفيذ", "اكتمل طلبك.")
    db.commit()
    return {"ok": True, "id": oid}

@r.post("/orders/reject", dependencies=[Depends(guard)])
def orders_reject(payload: dict = Body(...), db: Session = Depends(get_db)):
    oid = int(str(payload.get("order_id", "0")))
    kind, obj = _find_any_pending(db, oid)
    if not kind: raise HTTPException(404, "order not found or not pending")

    if kind == "service":
        u = db.query(User).filter_by(uid=obj.uid).first()
        if u:
            u.balance = round((u.balance or 0.0) + float(obj.price or 0.0), 2)
            db.add(u)
    obj.status = "rejected"
    db.add(obj)
    uid = getattr(obj, "uid", None)
    if uid: _add_user_notice(db, uid, "تم رفض الطلب", "تم رفض طلبك.")
    db.commit()
    return {"ok": True, "id": oid}

@r.post("/orders/refund", dependencies=[Depends(guard)])
def orders_refund(payload: dict = Body(...), db: Session = Depends(get_db)):
    oid = int(str(payload.get("order_id", "0")))
    obj = db.get(ServiceOrder, oid)
    if not obj: raise HTTPException(404, "order not found")
    u = db.query(User).filter_by(uid=obj.uid).first()
    if u:
        u.balance = round((u.balance or 0.0) + float(obj.price or 0.0), 2)
        db.add(u)
    obj.status = "refunded"
    db.add(obj)
    _add_user_notice(db, obj.uid, "تم رد رصيدك", f"+${obj.price}")
    db.commit()
    return {"ok": True, "id": obj.id}

# ---------- Wallet (يدعم Body أو Query) ----------
@r.post("/wallet/topup", dependencies=[Depends(guard)])
def wallet_topup(
    uid: Optional[str] = Body(default=None),
    amount: Optional[float] = Body(default=None),
    uid_q: Optional[str] = Query(default=None, alias="uid"),
    amount_q: Optional[float] = Query(default=None, alias="amount"),
    db: Session = Depends(get_db),
):
    uid = uid or uid_q
    amount = amount if amount is not None else amount_q
    if not uid or amount is None:
        raise HTTPException(400, "uid and amount required")
    u = db.query(User).filter_by(uid=uid).first()
    if not u: u = User(uid=uid, balance=0.0)
    u.balance = round((u.balance or 0.0) + float(amount), 2)
    db.add(u)
    _add_user_notice(db, uid, "تم إضافة رصيد", f"+${amount}")
    db.commit()
    return {"ok": True, "balance": u.balance}

@r.post("/wallet/deduct", dependencies=[Depends(guard)])
def wallet_deduct(
    uid: Optional[str] = Body(default=None),
    amount: Optional[float] = Body(default=None),
    uid_q: Optional[str] = Query(default=None, alias="uid"),
    amount_q: Optional[float] = Query(default=None, alias="amount"),
    db: Session = Depends(get_db),
):
    uid = uid or uid_q
    amount = amount if amount is not None else amount_q
    if not uid or amount is None:
        raise HTTPException(400, "uid and amount required")
    u = db.query(User).filter_by(uid=uid).first()
    if not u: u = User(uid=uid, balance=0.0)
    u.balance = max(0.0, round((u.balance or 0.0) - float(amount), 2))
    db.add(u)
    _add_user_notice(db, uid, "تم خصم رصيد", f"-${amount}")
    db.commit()
    return {"ok": True, "balance": u.balance}

# ---------- Stats ----------
@r.get("/stats/users-count", dependencies=[Depends(guard)])
def stats_users_count(db: Session = Depends(get_db)):
    return {"count": db.query(User).count()}

@r.get("/stats/users-balances", dependencies=[Depends(guard)])
def stats_users_balances(db: Session = Depends(get_db)):
    users = db.query(User).all()
    total = float(sum((u.balance or 0.0) for u in users))
    return {"total": total, "list": [{"uid": u.uid, "balance": float(u.balance or 0.0)} for u in users]}

@r.get("/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    try:
        info = provider_balance()
        return {"balance": float(info.get("balance", 0.0))}
    except Exception:
        return {"balance": 0.0}

@r.get("/check", dependencies=[Depends(guard)])
def check_ok():
    return {"ok": True}

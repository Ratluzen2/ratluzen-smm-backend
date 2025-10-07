# app/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Body, Form
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pydantic import BaseModel

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice, Token
)
from ..providers.smm_client import provider_add_order, provider_balance, provider_status
import httpx

r = APIRouter(prefix="/admin")

# ---------- Pydantic payloads ----------
class AmountReq(BaseModel):
    amount: float

class AcceptCardReq(BaseModel):
    amount_usd: float
    reviewed_by: Optional[str] = None

class GiftCodeReq(BaseModel):
    gift_code: str

class CodeReq(BaseModel):
    code: str

# -------- Helpers --------
def _row(obj):
    if obj is None:
        return None
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    return out

def _rows(lst):
    return [_row(o) for o in lst]

# -------- Guard (owner password) --------
def guard(
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_alt: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None)
):
    pwd = (x_admin_pass or x_admin_pass_alt or key or "").strip()
    if pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

@r.get("/check", dependencies=[Depends(guard)])
def check_ok():
    return {"ok": True}

# ---------- الخدمات المعلّقة ----------
@r.get("/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)):
    lst = (
        db.query(ServiceOrder)
        .filter_by(status="pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    return {"ok": True, "list": _rows(lst)}

@r.post("/pending/services/{order_id}/approve", dependencies=[Depends(guard)])
def approve_service(order_id: int, db: Session = Depends(get_db)):
    order = db.get(ServiceOrder, order_id)
    if not order or order.status != "pending":
        raise HTTPException(404, "order not found or not pending")

    send = provider_add_order(order.service_key, order.link, order.quantity)
    if not send.get("ok"):
        raise HTTPException(502, send.get("error", "provider error"))

    order.status = "processing"
    order.provider_order_id = send["orderId"]
    db.add(order)

    db.add(
        Notice(
            title="تم تنفيذ طلبك",
            body=f"أُرسل طلبك للمزوّد. رقم المزود: {order.provider_order_id}",
            for_owner=False,
            uid=order.uid,
        )
    )
    db.commit()
    return {"ok": True, "order": _row(order)}

@r.post("/pending/services/{order_id}/reject", dependencies=[Depends(guard)])
def reject_service(order_id: int, db: Session = Depends(get_db)):
    order = db.get(ServiceOrder, order_id)
    if not order or order.status != "pending":
        raise HTTPException(404, "order not found or not pending")

    order.status = "rejected"
    u = db.query(User).filter_by(uid=order.uid).first()
    if u:
        u.balance = round((u.balance or 0.0) + order.price, 2)
        db.add(u)

    db.add(order)
    db.add(Notice(title="تم رفض الطلب", body="تم رفض طلبك وتم ردّ الرصيد.", for_owner=False, uid=order.uid))
    db.commit()
    return {"ok": True}

# ---------- مزوّد ----------
@r.get("/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    return provider_balance()

@r.get("/provider/order-status/{ext_order_id}", dependencies=[Depends(guard)])
def provider_order_status(ext_order_id: str):
    return provider_status(ext_order_id)

# ---------- كارتات أسيا سيل ----------
@r.get("/pending/cards", dependencies=[Depends(guard)])
def pending_cards(db: Session = Depends(get_db)):
    lst = (
        db.query(WalletCard)
        .filter_by(status="pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    return {"ok": True, "list": _rows(lst)}

@r.post("/pending/cards/{card_id}/accept", dependencies=[Depends(guard)])
def accept_card(
    card_id: int,
    # Query
    amount_usd_q: Optional[float] = Query(default=None, alias="amount_usd"),
    reviewed_by_q: Optional[str] = Query(default="owner", alias="reviewed_by"),
    # JSON
    payload: Optional[AcceptCardReq] = Body(default=None),
    # Form
    amount_usd_f: Optional[float] = Form(default=None),
    reviewed_by_f: Optional[str] = Form(default=None),
    db: Session = Depends(get_db)
):
    # دمج المصادر
    amount_usd = amount_usd_q
    reviewed_by = reviewed_by_q
    if payload:
        amount_usd = payload.amount_usd if payload.amount_usd is not None else amount_usd
        if payload.reviewed_by: reviewed_by = payload.reviewed_by
    if amount_usd_f is not None:
        amount_usd = amount_usd_f
    if reviewed_by_f:
        reviewed_by = reviewed_by_f

    if amount_usd is None:
        raise HTTPException(400, "amount_usd required")

    card = db.get(WalletCard, card_id)
    if not card or card.status != "pending":
        raise HTTPException(404, "card not found or not pending")

    card.status = "accepted"
    card.amount_usd = float(amount_usd)
    card.reviewed_by = reviewed_by or "owner"

    u = db.query(User).filter_by(uid=card.uid).first()
    if not u:
        u = User(uid=card.uid, balance=0.0)
    u.balance = round((u.balance or 0.0) + float(amount_usd), 2)
    db.add(u)

    db.add(card)
    db.add(Notice(title="تم شحن رصيدك", body=f"+${amount_usd} عبر بطاقة أسيا سيل", for_owner=False, uid=card.uid))
    db.commit()
    return {"ok": True}

@r.post("/pending/cards/{card_id}/reject", dependencies=[Depends(guard)])
def reject_card(card_id: int, db: Session = Depends(get_db)):
    card = db.get(WalletCard, card_id)
    if not card or card.status != "pending":
        raise HTTPException(404, "card not found or not pending")
    card.status = "rejected"
    db.add(card)
    db.add(Notice(title="تم رفض الكارت", body="يرجى التأكد من الرقم والمحاولة مجددًا.", for_owner=False, uid=card.uid))
    db.commit()
    return {"ok": True}

# ---------- آيتونز ----------
@r.get("/pending/itunes", dependencies=[Depends(guard)])
def pending_itunes(db: Session = Depends(get_db)):
    lst = (
        db.query(ItunesOrder)
        .filter_by(status="pending")
        .order_by(ItunesOrder.created_at.desc())
        .all()
    )
    return {"ok": True, "list": _rows(lst)}

@r.post("/pending/itunes/{oid}/deliver", dependencies=[Depends(guard)])
def deliver_itunes(
    oid: int,
    gift_code_q: Optional[str] = Query(default=None, alias="gift_code"),
    payload: Optional[GiftCodeReq] = Body(default=None),
    gift_code_f: Optional[str] = Form(default=None),
    db: Session = Depends(get_db)
):
    gift_code = gift_code_q or (payload.gift_code if payload else None) or gift_code_f
    if not gift_code:
        raise HTTPException(400, "gift_code required")

    o = db.get(ItunesOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"
    o.gift_code = gift_code
    db.add(o)
    db.add(Notice(title="كود آيتونز", body=f"الكود: {gift_code}", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

@r.post("/pending/itunes/{oid}/reject", dependencies=[Depends(guard)])
def reject_itunes(oid: int, db: Session = Depends(get_db)):
    o = db.get(ItunesOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "rejected"
    db.add(o)
    db.add(Notice(title="رفض آيتونز", body="تم رفض طلبك.", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

# ---------- أرصدة الهاتف ----------
@r.get("/pending/phone", dependencies=[Depends(guard)])
def pending_phone(db: Session = Depends(get_db)):
    lst = (
        db.query(PhoneTopup)
        .filter_by(status="pending")
        .order_by(PhoneTopup.created_at.desc())
        .all()
    )
    return {"ok": True, "list": _rows(lst)}

@r.post("/pending/phone/{oid}/deliver", dependencies=[Depends(guard)])
def deliver_phone(
    oid: int,
    code_q: Optional[str] = Query(default=None, alias="code"),
    payload: Optional[CodeReq] = Body(default=None),
    code_f: Optional[str] = Form(default=None),
    db: Session = Depends(get_db)
):
    code = code_q or (payload.code if payload else None) or code_f
    if not code:
        raise HTTPException(400, "code required")

    o = db.get(PhoneTopup, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"
    o.code = code
    db.add(o)
    db.add(Notice(title="كارت الهاتف", body=f"الكود: {code}", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

@r.post("/pending/phone/{oid}/reject", dependencies=[Depends(guard)])
def reject_phone(oid: int, db: Session = Depends(get_db)):
    o = db.get(PhoneTopup, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "rejected"
    db.add(o)
    db.add(Notice(title="رفض رصيد الهاتف", body="تم رفض الطلب.", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

# ---------- PUBG ----------
@r.get("/pending/pubg", dependencies=[Depends(guard)])
def pending_pubg(db: Session = Depends(get_db)):
    lst = (
        db.query(PubgOrder)
        .filter_by(status="pending")
        .order_by(PubgOrder.created_at.desc())
        .all()
    )
    return {"ok": True, "list": _rows(lst)}

@r.post("/pending/pubg/{oid}/deliver", dependencies=[Depends(guard)])
def deliver_pubg(oid: int, db: Session = Depends(get_db)):
    o = db.get(PubgOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"
    db.add(o)
    db.add(Notice(title="تم شحن شداتك", body=f"حزمة {o.pkg} UC", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

@r.post("/pending/pubg/{oid}/reject", dependencies=[Depends(guard)])
def reject_pubg(oid: int, db: Session = Depends(get_db)):
    o = db.get(PubgOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "rejected"
    db.add(o)
    db.add(Notice(title="رفض شدات ببجي", body="تم رفض طلبك.", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

# ---------- لودو ----------
@r.get("/pending/ludo", dependencies=[Depends(guard)])
def pending_ludo(db: Session = Depends(get_db)):
    lst = (
        db.query(LudoOrder)
        .filter_by(status="pending")
        .order_by(LudoOrder.created_at.desc())
        .all()
    )
    return {"ok": True, "list": _rows(lst)}

@r.post("/pending/ludo/{oid}/deliver", dependencies=[Depends(guard)])
def deliver_ludo(oid: int, db: Session = Depends(get_db)):
    o = db.get(LudoOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"
    db.add(o)
    db.add(Notice(title="تم تنفيذ لودو", body=f"{o.kind} {o.pack}", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

@r.post("/pending/ludo/{oid}/reject", dependencies=[Depends(guard)])
def reject_ludo(oid: int, db: Session = Depends(get_db)):
    o = db.get(LudoOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "rejected"
    db.add(o)
    db.add(Notice(title="رفض طلب لودو", body="تم رفض طلبك.", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

# ---------- إدارة المستخدمين ----------
@r.get("/users/count", dependencies=[Depends(guard)])
def users_count(db: Session = Depends(get_db)):
    return {"ok": True, "count": db.query(User).count()}

@r.get("/users/balances", dependencies=[Depends(guard)])
def users_balances(db: Session = Depends(get_db)):
    lst = db.query(User).order_by(User.balance.desc()).limit(500).all()
    return {
        "ok": True,
        "list": [{"uid": u.uid, "balance": u.balance, "is_banned": u.is_banned} for u in lst],
    }

@r.post("/users/{uid}/topup", dependencies=[Depends(guard)])
def user_topup(
    uid: str,
    amount_q: Optional[float] = Query(default=None, alias="amount"),
    payload: Optional[AmountReq] = Body(default=None),
    amount_f: Optional[float] = Form(default=None),
    db: Session = Depends(get_db)
):
    amount = amount_q
    if payload and payload.amount is not None:
        amount = payload.amount
    if amount_f is not None:
        amount = amount_f
    if amount is None:
        raise HTTPException(400, "amount required")

    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
    u.balance = round((u.balance or 0.0) + float(amount), 2)
    db.add(u)
    db.add(Notice(title="تم إضافة رصيد", body=f"+${amount}", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "balance": u.balance}

@r.post("/users/{uid}/deduct", dependencies=[Depends(guard)])
def user_deduct(
    uid: str,
    amount_q: Optional[float] = Query(default=None, alias="amount"),
    payload: Optional[AmountReq] = Body(default=None),
    amount_f: Optional[float] = Form(default=None),
    db: Session = Depends(get_db)
):
    amount = amount_q
    if payload and payload.amount is not None:
        amount = payload.amount
    if amount_f is not None:
        amount = amount_f
    if amount is None:
        raise HTTPException(400, "amount required")

    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
    u.balance = max(0.0, round((u.balance or 0.0) - float(amount), 2))
    db.add(u)
    db.add(Notice(title="تم خصم رصيد", body=f"-${amount}", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "balance": u.balance}

@r.post("/users/{uid}/ban", dependencies=[Depends(guard)])
def ban(uid: str, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
    u.is_banned = True
    db.add(u)
    db.commit()
    return {"ok": True}

@r.post("/users/{uid}/unban", dependencies=[Depends(guard)])
def unban(uid: str, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
    u.is_banned = False
    db.add(u)
    db.commit()
    return {"ok": True}

# ---------- إشعار يدوي ----------
@r.post("/notify/push", dependencies=[Depends(guard)])
def push_notify(
    title: str = "تنبيه",
    body: str = "رسالة",
    target: str = "allUsers",
    db: Session = Depends(get_db)
):
    key = settings.FCM_SERVER_KEY
    if not key:
        raise HTTPException(400, "FCM_SERVER_KEY not set")

    if target == "owners":
        tokens = [t.token for t in db.query(Token).filter_by(for_owner=True).all()]
    elif target.startswith("uid:"):
        target_uid = target.split(":", 1)[1]
        tokens = [t.token for t in db.query(Token).filter_by(uid=target_uid).all()]
    else:
        tokens = [t.token for t in db.query(Token).filter_by(for_owner=False).all()]

    ok = 0
    fail = 0
    for tk in tokens:
        try:
            httpx.post(
                "https://fcm.googleapis.com/fcm/send",
                json={"to": tk, "notification": {"title": title, "body": body}},
                headers={"Authorization": f"key={key}", "Content-Type": "application/json"},
                timeout=8.0,
            )
            ok += 1
        except Exception:
            fail += 1
    return {"ok": True, "sent": ok, "failed": fail}

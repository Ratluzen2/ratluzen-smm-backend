# app/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice, Token
)
from ..providers.smm_client import provider_add_order, provider_balance, provider_status

r = APIRouter(prefix="/api/admin")

# ---------- Guard ----------
def guard(
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_alt: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None),
):
    pwd = (x_admin_pass or x_admin_pass_alt or key or "").strip()
    if pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

# ---------- helpers ----------
def _ts(dt: Optional[datetime]) -> int:
    return int(dt.timestamp()) if dt else 0

def _order_row(
    id_str: str,
    title: str,
    qty: int,
    price: float,
    payload: str,
    status: str,
    created_at: Optional[datetime],
) -> Dict[str, Any]:
    return {
        "id": id_str,
        "title": title,
        "quantity": qty,
        "price": float(price),
        "payload": payload,
        "status": status,
        "created_at": _ts(created_at),
    }

def _parse_compound_id(comp: str) -> Tuple[str, int]:
    """
    comp مثال: svc:12  / card:5 / itunes:9 / phone:7 / pubg:4 / ludo:3
    """
    try:
        kind, sid = comp.split(":", 1)
        return kind, int(sid)
    except Exception:
        raise HTTPException(400, "bad order_id")

# ---------- Pending lists (arrays, not wrapped) ----------
@r.get("/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.status == "pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    return [
        _order_row(
            id_str=f"svc:{o.id}",
            title=f"{o.service_key or 'خدمة'} (#{o.service_code})",
            qty=o.quantity,
            price=o.price,
            payload=o.link,
            status=o.status,
            created_at=o.created_at,
        )
        for o in rows
    ]

@r.get("/pending/itunes", dependencies=[Depends(guard)])
def pending_itunes(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(ItunesOrder)
        .filter(ItunesOrder.status == "pending")
        .order_by(ItunesOrder.created_at.desc())
        .all()
    )
    return [
        _order_row(
            id_str=f"itunes:{o.id}",
            title=f"iTunes ${o.amount}",
            qty=o.amount,
            price=float(o.amount),
            payload="-",
            status=o.status,
            created_at=o.created_at,
        )
        for o in rows
    ]

@r.get("/pending/topups", dependencies=[Depends(guard)])
def pending_topups(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(WalletCard)
        .filter(WalletCard.status == "pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    out: List[Dict[str, Any]] = []
    for c in rows:
        title = f"Asiacell Card from {c.uid}"
        payload = c.card_number or ""
        out.append(
            _order_row(
                id_str=f"card:{c.id}",
                title=title,
                qty=1,
                price=0.0,
                payload=payload,  # يظهر الرقم للمالك وقابل للنسخ في الواجهة
                status=c.status,
                created_at=c.created_at,
            )
        )
    return out

@r.get("/pending/pubg", dependencies=[Depends(guard)])
def pending_pubg(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(PubgOrder)
        .filter(PubgOrder.status == "pending")
        .order_by(PubgOrder.created_at.desc())
        .all()
    )
    return [
        _order_row(
            id_str=f"pubg:{o.id}",
            title=f"PUBG {o.pkg} UC | {o.pubg_id}",
            qty=o.pkg,
            price=0.0,
            payload=o.pubg_id,
            status=o.status,
            created_at=o.created_at,
        )
        for o in rows
    ]

@r.get("/pending/ludo", dependencies=[Depends(guard)])
def pending_ludo(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(LudoOrder)
        .filter(LudoOrder.status == "pending")
        .order_by(LudoOrder.created_at.desc())
        .all()
    )
    return [
        _order_row(
            id_str=f"ludo:{o.id}",
            title=f"Ludo {o.kind} x{o.pack} | {o.ludo_id}",
            qty=o.pack,
            price=0.0,
            payload=o.ludo_id,
            status=o.status,
            created_at=o.created_at,
        )
        for o in rows
    ]

# ---------- Actions (approve/reject/refund) ----------
class ApproveReq(BaseModel):
    order_id: str
    amount: Optional[float] = None  # يستخدم لقبول كارت أسيا سيل

class RejectReq(BaseModel):
    order_id: str
    reason: Optional[str] = None

class RefundReq(BaseModel):
    order_id: str

from pydantic import BaseModel

@r.post("/orders/approve", dependencies=[Depends(guard)])
def orders_approve(payload: ApproveReq, db: Session = Depends(get_db)) -> Dict[str, Any]:
    kind, oid = _parse_compound_id(payload.order_id)

    if kind == "svc":
        o = db.get(ServiceOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "order not found or not pending")

        # إرسال فعلي إلى المزود KD1S
        sent = provider_add_order(o.service_key, o.link, o.quantity)
        if not sent.get("ok"):
            raise HTTPException(502, sent.get("error", "provider error"))

        o.status = "processing"
        o.provider_order_id = sent["orderId"]
        db.add(o)

        db.add(Notice(
            title="تم تنفيذ طلبك",
            body=f"تم إرسال الطلب للمزود. رقم المزود: {o.provider_order_id}",
            for_owner=False, uid=o.uid
        ))
        db.commit()
        return {"ok": True}

    if kind == "card":
        c = db.get(WalletCard, oid)
        if not c or c.status != "pending":
            raise HTTPException(404, "card not found or not pending")
        amount = payload.amount
        if amount is None:
            raise HTTPException(400, "amount required for card approve")

        c.status = "accepted"
        c.amount_usd = float(amount)
        c.reviewed_by = "owner"

        u = db.query(User).filter_by(uid=c.uid).first()
        if not u:
            u = User(uid=c.uid, balance=0.0)
        u.balance = round((u.balance or 0.0) + float(amount), 2)
        db.add(u)
        db.add(c)
        db.add(Notice(
            title="تم شحن رصيدك",
            body=f"+${amount} عبر بطاقة أسيا سيل",
            for_owner=False, uid=c.uid
        ))
        db.commit()
        return {"ok": True}

    if kind == "itunes":
        o = db.get(ItunesOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "itunes not found or not pending")
        # هنا تستطيع تسليم كود إن رغبت، أو إبقاؤه manual
        o.status = "delivered"
        db.add(o)
        db.add(Notice(title="iTunes", body=f"تمت معالجة طلب iTunes ${o.amount}", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    if kind == "pubg":
        o = db.get(PubgOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "pubg not found or not pending")
        o.status = "delivered"
        db.add(o)
        db.add(Notice(title="PUBG", body=f"تم تنفيذ شداتك {o.pkg} UC", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    if kind == "ludo":
        o = db.get(LudoOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "ludo not found or not pending")
        o.status = "delivered"
        db.add(o)
        db.add(Notice(title="Ludo", body=f"تم تنفيذ {o.kind} {o.pack}", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    raise HTTPException(400, "unsupported kind")

@r.post("/orders/reject", dependencies=[Depends(guard)])
def orders_reject(payload: RejectReq, db: Session = Depends(get_db)) -> Dict[str, Any]:
    kind, oid = _parse_compound_id(payload.order_id)

    if kind == "svc":
        o = db.get(ServiceOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "order not found or not pending")
        o.status = "rejected"
        # رد الرصيد
        u = db.query(User).filter_by(uid=o.uid).first()
        if u:
            u.balance = round((u.balance or 0.0) + float(o.price or 0.0), 2)
            db.add(u)
        db.add(o)
        db.add(Notice(title="تم رفض الطلب", body="تم رفض طلبك وتم ردّ الرصيد.", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    if kind == "card":
        c = db.get(WalletCard, oid)
        if not c or c.status != "pending":
            raise HTTPException(404, "card not found or not pending")
        c.status = "rejected"
        db.add(c)
        db.add(Notice(title="رفض الكارت", body="تم رفض كارت أسيا سيل.", for_owner=False, uid=c.uid))
        db.commit()
        return {"ok": True}

    if kind == "itunes":
        o = db.get(ItunesOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "itunes not found or not pending")
        o.status = "rejected"
        db.add(o)
        db.add(Notice(title="رفض iTunes", body="تم رفض طلبك.", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    if kind == "pubg":
        o = db.get(PubgOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "pubg not found or not pending")
        o.status = "rejected"
        db.add(o)
        db.add(Notice(title="رفض PUBG", body="تم رفض طلبك.", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    if kind == "ludo":
        o = db.get(LudoOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "ludo not found or not pending")
        o.status = "rejected"
        db.add(o)
        db.add(Notice(title="رفض Ludo", body="تم رفض طلبك.", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    raise HTTPException(400, "unsupported kind")

@r.post("/orders/refund", dependencies=[Depends(guard)])
def orders_refund(payload: RefundReq, db: Session = Depends(get_db)) -> Dict[str, Any]:
    kind, oid = _parse_compound_id(payload.order_id)
    if kind != "svc":
        raise HTTPException(400, "refund is supported only for services orders")

    o = db.get(ServiceOrder, oid)
    if not o or o.status not in ("pending", "processing"):
        raise HTTPException(404, "order not found or not refundable")
    # اجعلها مرفوض ثم رد الرصيد
    o.status = "rejected"
    u = db.query(User).filter_by(uid=o.uid).first()
    if u:
        u.balance = round((u.balance or 0.0) + float(o.price or 0.0), 2)
        db.add(u)
    db.add(o)
    db.add(Notice(title="رد رصيد", body=f"تم رد رصيد طلبك: {o.price}$", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

# ---------- Wallet ops ----------
class WalletReq(BaseModel):
    uid: str
    amount: float

@r.post("/wallet/topup", dependencies=[Depends(guard)])
def wallet_topup(body: WalletReq, db: Session = Depends(get_db)) -> Dict[str, Any]:
    u = db.query(User).filter_by(uid=body.uid).first()
    if not u:
        u = User(uid=body.uid, balance=0.0)
    u.balance = round((u.balance or 0.0) + float(body.amount), 2)
    db.add(u)
    db.add(Notice(title="تم إضافة رصيد", body=f"+${body.amount}", for_owner=False, uid=body.uid))
    db.commit()
    return {"ok": True, "balance": u.balance}

@r.post("/wallet/deduct", dependencies=[Depends(guard)])
def wallet_deduct(body: WalletReq, db: Session = Depends(get_db)) -> Dict[str, Any]:
    u = db.query(User).filter_by(uid=body.uid).first()
    if not u:
        u = User(uid=body.uid, balance=0.0)
    u.balance = max(0.0, round((u.balance or 0.0) - float(body.amount), 2))
    db.add(u)
    db.add(Notice(title="تم خصم رصيد", body=f"-${body.amount}", for_owner=False, uid=body.uid))
    db.commit()
    return {"ok": True, "balance": u.balance}

# ---------- Stats ----------
@r.get("/stats/users-count", dependencies=[Depends(guard)])
def users_count(db: Session = Depends(get_db)) -> Dict[str, Any]:
    return {"count": db.query(User).count()}

@r.get("/stats/users-balances", dependencies=[Depends(guard)])
def users_balances(db: Session = Depends(get_db)) -> Dict[str, Any]:
    total = sum(float(u.balance or 0.0) for u in db.query(User).all())
    return {"total": round(total, 2)}

# ---------- Provider ----------
@r.get("/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    b = provider_balance()
    # توقع أن تُرجع provider_balance() dict يشمل balance أو ok/err
    if isinstance(b, dict) and "balance" in b:
        return {"balance": b["balance"]}
    return {"balance": 0.0}

@r.get("/provider/order-status/{ext_order_id}", dependencies=[Depends(guard)])
def provider_order_status(ext_order_id: str):
    return provider_status(ext_order_id)

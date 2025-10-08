# app/routers/admin.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Body, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice, Token
)
from ..providers.smm_client import provider_add_order, provider_balance, provider_status

r = APIRouter(prefix="/admin", tags=["admin"])

# --------------------------
# Helpers
# --------------------------
def _ms(dt: datetime | None) -> int:
    if not dt:
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def _ensure_user(db: Session, uid: str) -> User:
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.flush()
    return u

def _add_notice(db: Session, title: str, body: str, uid: Optional[str], for_owner: bool = False) -> None:
    db.add(Notice(title=title, body=body, uid=uid, for_owner=for_owner))

# توحيد شكل العناصر المُعادة لواجهة المالك داخل التطبيق
def _item_service(o: ServiceOrder) -> Dict[str, Any]:
    return {
        "id": f"svc-{o.id}",
        "title": f"{o.service_key or 'service'} • x{o.quantity}",
        "quantity": o.quantity,
        "price": o.price,
        "payload": o.link,
        "status": o.status,
        "created_at": _ms(o.created_at),
    }

def _item_card(c: WalletCard) -> Dict[str, Any]:
    masked = (c.card_number or "").strip()
    if len(masked) >= 4:
        masked = ("*" * (len(masked) - 4)) + masked[-4:]
    return {
        "id": f"card-{c.id}",
        "title": f"Asiacell Card • {masked}",
        "quantity": 1,
        "price": float(c.amount_usd or 0.0),
        "payload": c.card_number,
        "status": c.status,
        "created_at": _ms(c.created_at),
    }

def _item_itunes(o: ItunesOrder) -> Dict[str, Any]:
    return {
        "id": f"itn-{o.id}",
        "title": f"iTunes ${o.amount}",
        "quantity": 1,
        "price": float(o.amount),
        "payload": o.gift_code or "",
        "status": o.status,
        "created_at": _ms(o.created_at),
    }

def _item_phone(o: PhoneTopup) -> Dict[str, Any]:
    return {
        "id": f"phn-{o.id}",
        "title": f"Phone {o.operator} ${o.amount}",
        "quantity": 1,
        "price": float(o.amount),
        "payload": o.code or "",
        "status": o.status,
        "created_at": _ms(o.created_at),
    }

def _item_pubg(o: PubgOrder) -> Dict[str, Any]:
    return {
        "id": f"pubg-{o.id}",
        "title": f"PUBG UC {o.pkg}",
        "quantity": o.pkg,
        "price": 0.0,
        "payload": o.pubg_id,
        "status": o.status,
        "created_at": _ms(o.created_at),
    }

def _item_ludo(o: LudoOrder) -> Dict[str, Any]:
    return {
        "id": f"ludo-{o.id}",
        "title": f"Ludo {o.kind} {o.pack}",
        "quantity": o.pack,
        "price": 0.0,
        "payload": o.ludo_id,
        "status": o.status,
        "created_at": _ms(o.created_at),
    }

# --------------------------
# Auth guard (x-admin-pass)
# --------------------------
def guard(
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_alt: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None)
):
    pwd = (x_admin_pass or x_admin_pass_alt or key or "").strip()
    if pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="unauthorized")

# --------------------------
# Schemas
# --------------------------
class LoginReq(BaseModel):
    password: str

class ApproveReq(BaseModel):
    order_id: str
    amount: Optional[float] = None     # للبطاقات/الهاتف/الخ...
    gift_code: Optional[str] = None    # لآيتونز
    code: Optional[str] = None         # لبطاقات الهاتف

class IdReq(BaseModel):
    order_id: str

class WalletReq(BaseModel):
    uid: str
    amount: float

# --------------------------
# Login & Check
# --------------------------
@r.post("/login")
def login(payload: LoginReq):
    if payload.password != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "invalid credentials")
    # يُعيد توكنًا يستخدم كترويسة x-admin-pass (التطبيق يرسله كما هو)
    return {"ok": True, "token": payload.password}

@r.get("/check", dependencies=[Depends(guard)])
def check_ok():
    return {"ok": True}

# --------------------------
# Pending lists (raw arrays)
# --------------------------
@r.get("/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    lst = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.status == "pending")
        .order_by(ServiceOrder.created_at.desc())
        .limit(500)
        .all()
    )
    return [_item_service(o) for o in lst]

@r.get("/pending/itunes", dependencies=[Depends(guard)])
def pending_itunes(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    lst = (
        db.query(ItunesOrder)
        .filter(ItunesOrder.status == "pending")
        .order_by(ItunesOrder.created_at.desc())
        .limit(500)
        .all()
    )
    return [_item_itunes(o) for o in lst]

@r.get("/pending/topups", dependencies=[Depends(guard)])
def pending_topups(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    lst = (
        db.query(WalletCard)
        .filter(WalletCard.status == "pending")
        .order_by(WalletCard.created_at.desc())
        .limit(500)
        .all()
    )
    return [_item_card(c) for c in lst]

@r.get("/pending/pubg", dependencies=[Depends(guard)])
def pending_pubg(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    lst = (
        db.query(PubgOrder)
        .filter(PubgOrder.status == "pending")
        .order_by(PubgOrder.created_at.desc())
        .limit(500)
        .all()
    )
    return [_item_pubg(o) for o in lst]

@r.get("/pending/ludo", dependencies=[Depends(guard)])
def pending_ludo(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    lst = (
        db.query(LudoOrder)
        .filter(LudoOrder.status == "pending")
        .order_by(LudoOrder.created_at.desc())
        .limit(500)
        .all()
    )
    return [_item_ludo(o) for o in lst]

# --------------------------
# Actions: approve / reject / refund
# --------------------------
@r.post("/orders/approve", dependencies=[Depends(guard)])
def approve(payload: ApproveReq, db: Session = Depends(get_db)):
    oid = (payload.order_id or "").strip()
    if "-" not in oid:
        raise HTTPException(400, "bad order_id format")
    kind, sid = oid.split("-", 1)
    # SERVICES (مزود خارجي KD1S عبر provider_add_order)
    if kind == "svc":
        o = db.get(ServiceOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "order not found or not pending")
        send = provider_add_order(
            service_key=o.service_key or "",
            link=o.link,
            quantity=o.quantity
        )
        if not send.get("ok"):
            raise HTTPException(502, send.get("error", "provider error"))
        o.status = "processing"
        o.provider_order_id = str(send.get("orderId"))
        db.add(o)
        _add_notice(db, "تنفيذ طلبك", f"تم إرسال طلبك للمزوّد. رقم المزود: {o.provider_order_id}", o.uid, for_owner=False)
        db.commit()
        return {"ok": True, "provider_order_id": o.provider_order_id}

    # ASIACELL CARD
    if kind == "card":
        c = db.get(WalletCard, int(sid))
        if not c or c.status != "pending":
            raise HTTPException(404, "card not found or not pending")
        amount = payload.amount if payload.amount is not None else c.amount_usd
        if amount is None:
            raise HTTPException(400, "amount required")
        c.status = "accepted"
        c.amount_usd = float(amount)
        c.reviewed_by = "owner"
        u = _ensure_user(db, c.uid)
        u.balance = round((u.balance or 0.0) + float(amount), 2)
        db.add(u)
        db.add(c)
        _add_notice(db, "تم شحن رصيدك", f"+${amount} عبر كارت أسيا سيل", c.uid, for_owner=False)
        db.commit()
        return {"ok": True, "balance": u.balance}

    # ITUNES
    if kind == "itn":
        o = db.get(ItunesOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found or not pending")
        if not payload.gift_code:
            raise HTTPException(400, "gift_code required")
        o.status = "delivered"
        o.gift_code = payload.gift_code
        db.add(o)
        _add_notice(db, "كود آيتونز", f"الكود: {payload.gift_code}", o.uid, for_owner=False)
        db.commit()
        return {"ok": True}

    # PHONE
    if kind == "phn":
        o = db.get(PhoneTopup, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found or not pending")
        if not payload.code:
            raise HTTPException(400, "code required")
        o.status = "delivered"
        o.code = payload.code
        db.add(o)
        _add_notice(db, "كارت الهاتف", f"الكود: {payload.code}", o.uid, for_owner=False)
        db.commit()
        return {"ok": True}

    # PUBG
    if kind == "pubg":
        o = db.get(PubgOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found or not pending")
        o.status = "delivered"
        db.add(o)
        _add_notice(db, "تم تنفيذ طلبك", f"شحن ببجي {o.pkg} UC", o.uid, for_owner=False)
        db.commit()
        return {"ok": True}

    # LUDO
    if kind == "ludo":
        o = db.get(LudoOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found or not pending")
        o.status = "delivered"
        db.add(o)
        _add_notice(db, "تم تنفيذ طلبك", f"Ludo {o.kind} {o.pack}", o.uid, for_owner=False)
        db.commit()
        return {"ok": True}

    raise HTTPException(400, "unknown order type")

@r.post("/orders/reject", dependencies=[Depends(guard)])
def reject(payload: IdReq, db: Session = Depends(get_db)):
    oid = (payload.order_id or "").strip()
    if "-" not in oid:
        raise HTTPException(400, "bad order_id format")
    kind, sid = oid.split("-", 1)

    if kind == "svc":
        o = db.get(ServiceOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "order not found or not pending")
        o.status = "rejected"
        db.add(o)
        # ردّ الرصيد
        u = _ensure_user(db, o.uid)
        u.balance = round((u.balance or 0.0) + float(o.price or 0.0), 2)
        db.add(u)
        _add_notice(db, "رفض الطلب", "تم رفض طلبك وتم ردّ الرصيد.", o.uid, for_owner=False)
        db.commit()
        return {"ok": True}

    # بقية الأنواع: مجرد رفض وإشعار
    m: Dict[str, Any] | None = None
    if kind == "card":
        m = db.get(WalletCard, int(sid))
    elif kind == "itn":
        m = db.get(ItunesOrder, int(sid))
    elif kind == "phn":
        m = db.get(PhoneTopup, int(sid))
    elif kind == "pubg":
        m = db.get(PubgOrder, int(sid))
    elif kind == "ludo":
        m = db.get(LudoOrder, int(sid))

    if not m or getattr(m, "status", None) != "pending":
        raise HTTPException(404, "not found or not pending")

    setattr(m, "status", "rejected")
    db.add(m)
    _add_notice(db, "تم رفض الطلب", "يرجى مراجعة التفاصيل والمحاولة لاحقًا.", getattr(m, "uid", None), for_owner=False)
    db.commit()
    return {"ok": True}

@r.post("/orders/refund", dependencies=[Depends(guard)])
def refund(payload: IdReq, db: Session = Depends(get_db)):
    oid = (payload.order_id or "").strip()
    if not oid.startswith("svc-"):
        raise HTTPException(400, "refund supported for service orders only")
    o = db.get(ServiceOrder, int(oid.split("-", 1)[1]))
    if not o or o.status not in ("pending", "processing", "rejected"):
        raise HTTPException(404, "order not eligible for refund")
    u = _ensure_user(db, o.uid)
    u.balance = round((u.balance or 0.0) + float(o.price or 0.0), 2)
    o.status = "rejected"
    db.add_all([o, u])
    _add_notice(db, "ردّ الرصيد", f"تم رد ${o.price or 0.0}", o.uid, for_owner=False)
    db.commit()
    return {"ok": True, "balance": u.balance}

# --------------------------
# Wallet operations
# --------------------------
@r.post("/wallet/topup", dependencies=[Depends(guard)])
def wallet_topup(req: WalletReq, db: Session = Depends(get_db)):
    if req.amount <= 0:
        raise HTTPException(400, "amount must be > 0")
    u = _ensure_user(db, req.uid)
    u.balance = round((u.balance or 0.0) + float(req.amount), 2)
    db.add(u)
    _add_notice(db, "إضافة رصيد", f"+${req.amount}", req.uid, for_owner=False)
    db.commit()
    return {"ok": True, "balance": u.balance}

@r.post("/wallet/deduct", dependencies=[Depends(guard)])
def wallet_deduct(req: WalletReq, db: Session = Depends(get_db)):
    if req.amount <= 0:
        raise HTTPException(400, "amount must be > 0")
    u = _ensure_user(db, req.uid)
    u.balance = max(0.0, round((u.balance or 0.0) - float(req.amount), 2))
    db.add(u)
    _add_notice(db, "خصم رصيد", f"-${req.amount}", req.uid, for_owner=False)
    db.commit()
    return {"ok": True, "balance": u.balance}

# --------------------------
# Provider (KD1S) helpers
# --------------------------
@r.get("/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    # يُعيد {"balance": <float>, "ok": True} من عميل المزود
    return provider_balance()

@r.get("/provider/order-status/{ext_order_id}", dependencies=[Depends(guard)])
def provider_order_status(ext_order_id: str):
    return provider_status(ext_order_id)

# --------------------------
# Stats
# --------------------------
@r.get("/stats/users-count", dependencies=[Depends(guard)])
def users_count(db: Session = Depends(get_db)):
    total = db.query(User).count()
    # نشِط آخر ساعة (باستخدام created_at إن وجد)
    last_hour = datetime.now(timezone.utc) - timedelta(hours=1)
    try:
        active = db.query(User).filter(User.created_at >= last_hour).count()
    except Exception:
        active = 0
    return {"ok": True, "count": total, "active_last_hour": active}

@r.get("/stats/users-balances", dependencies=[Depends(guard)])
def users_balances(db: Session = Depends(get_db)):
    lst = db.query(User).order_by(User.balance.desc()).limit(1000).all()
    total = float(db.query(func.coalesce(func.sum(User.balance), 0.0)).scalar() or 0.0)
    return {
        "ok": True,
        "total": total,
        "list": [{"uid": u.uid, "balance": float(u.balance or 0.0), "is_banned": bool(u.is_banned)} for u in lst],
    }

# --------------------------
# Optional: push notification via FCM (إن رغبت)
# --------------------------
# يمكن تركه كما هو أو إزالته إذا لم تستعمله من التطبيق
# من أجل التبسيط لم أدرج الإرسال فعليًا هنا.

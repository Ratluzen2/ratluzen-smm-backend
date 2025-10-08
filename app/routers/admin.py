# app/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)
from ..providers.smm_client import provider_add_order, provider_balance, provider_status

router = APIRouter(prefix="/admin", tags=["admin"])
# للتوافق مع من يستورد r
r = router

# ======================
# Helpers
# ======================
def _epoch_ms(dt: Optional[datetime]) -> int:
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def _guard_pwd(
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_alt: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None)
):
    pwd = (x_admin_pass or x_admin_pass_alt or key or "").strip()
    if pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

def _service_row(o: ServiceOrder) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "title": f"{o.service_key} (code={o.service_code})",
        "quantity": o.quantity,
        "price": float(o.price or 0),
        "payload": o.link,
        "status": o.status,
        "created_at": _epoch_ms(o.created_at),
    }

def _card_row(c: WalletCard) -> Dict[str, Any]:
    return {
        "id": str(c.id),
        "title": "كارت أسيا سيل",
        "quantity": 1,
        "price": float(c.amount_usd or 0.0),
        "payload": c.card_number,  # يظهر رقم الكارت في التطبيق
        "status": c.status,
        "created_at": _epoch_ms(c.created_at),
    }

def _itunes_row(o: ItunesOrder) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "title": f"آيتونز {o.amount}$",
        "quantity": 1,
        "price": float(o.amount or 0),
        "payload": o.gift_code or "",
        "status": o.status,
        "created_at": _epoch_ms(o.created_at),
    }

def _phone_row(o: PhoneTopup) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "title": f"كارت هاتف ({o.operator}) {o.amount}$",
        "quantity": 1,
        "price": float(o.amount or 0),
        "payload": o.code or "",
        "status": o.status,
        "created_at": _epoch_ms(o.created_at),
    }

def _pubg_row(o: PubgOrder) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "title": f"شدات ببجي {o.pkg} UC",
        "quantity": o.pkg,
        "price": 0.0,
        "payload": o.pubg_id,
        "status": o.status,
        "created_at": _epoch_ms(o.created_at),
    }

def _ludo_row(o: LudoOrder) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "title": f"لودو ({o.kind}) {o.pack}",
        "quantity": o.pack,
        "price": 0.0,
        "payload": o.ludo_id,
        "status": o.status,
        "created_at": _epoch_ms(o.created_at),
    }

# ======================
# Login (اختياري - للتوافق)
# ======================
@router.post("/login")
def admin_login(password: str = Body(..., embed=True)):
    if password != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "invalid password")
    # التطبيق يخزن التوكن كما هو ويرسله في x-admin-pass
    return {"token": password}

# ======================
# Pending lists (ترجع Array مباشرة)
# ======================
@router.get("/pending/services", dependencies=[Depends(_guard_pwd)])
def pending_services(db: Session = Depends(get_db)):
    rows = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.status == "pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    return [_service_row(o) for o in rows]

@router.get("/pending/itunes", dependencies=[Depends(_guard_pwd)])
def pending_itunes(db: Session = Depends(get_db)):
    rows = (
        db.query(ItunesOrder)
        .filter(ItunesOrder.status == "pending")
        .order_by(ItunesOrder.created_at.desc())
        .all()
    )
    return [_itunes_row(o) for o in rows]

@router.get("/pending/topups", dependencies=[Depends(_guard_pwd)])
def pending_topups_alias(db: Session = Depends(get_db)):
    # Alias للكروت (Asiacell)
    rows = (
        db.query(WalletCard)
        .filter(WalletCard.status == "pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    return [_card_row(o) for o in rows]

@router.get("/pending/phone", dependencies=[Depends(_guard_pwd)])
def pending_phone(db: Session = Depends(get_db)):
    rows = (
        db.query(PhoneTopup)
        .filter(PhoneTopup.status == "pending")
        .order_by(PhoneTopup.created_at.desc())
        .all()
    )
    return [_phone_row(o) for o in rows]

@router.get("/pending/pubg", dependencies=[Depends(_guard_pwd)])
def pending_pubg(db: Session = Depends(get_db)):
    rows = (
        db.query(PubgOrder)
        .filter(PubgOrder.status == "pending")
        .order_by(PubgOrder.created_at.desc())
        .all()
    )
    return [_pubg_row(o) for o in rows]

@router.get("/pending/ludo", dependencies=[Depends(_guard_pwd)])
def pending_ludo(db: Session = Depends(get_db)):
    rows = (
        db.query(LudoOrder)
        .filter(LudoOrder.status == "pending")
        .order_by(LudoOrder.created_at.desc())
        .all()
    )
    return [_ludo_row(o) for o in rows]

# ======================
# Generic actions used by the app buttons
# ======================
class _OrderReq(BaseException):
    pass

@router.post("/orders/approve", dependencies=[Depends(_guard_pwd)])
def orders_approve(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    # 1) Service order => إرسال للمزوّد
    o = db.get(ServiceOrder, order_id)
    if o and o.status == "pending":
        send = provider_add_order(o.service_key, o.link, o.quantity)
        if not send.get("ok"):
            raise HTTPException(502, send.get("error", "provider error"))
        o.status = "processing"
        o.provider_order_id = send.get("orderId")
        db.add(o)
        db.add(Notice(title="تم تنفيذ طلبك", body=f"رقم المزوّد: {o.provider_order_id}", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True, "kind": "service", "id": order_id}

    # 2) WalletCard / Itunes / Phone / Pubg / Ludo => تحويلها إلى processing
    c = db.get(WalletCard, order_id)
    if c and c.status == "pending":
        c.status = "processing"
        db.add(c)
        db.add(Notice(title="جاري معالجة كارتك", body=f"الكارت: {c.card_number}", for_owner=False, uid=c.uid))
        db.commit()
        return {"ok": True, "kind": "card", "id": order_id}

    it = db.get(ItunesOrder, order_id)
    if it and it.status == "pending":
        it.status = "processing"
        db.add(it)
        db.add(Notice(title="جاري تجهيز كود آيتونز", body=f"قيمة {it.amount}$", for_owner=False, uid=it.uid))
        db.commit()
        return {"ok": True, "kind": "itunes", "id": order_id}

    ph = db.get(PhoneTopup, order_id)
    if ph and ph.status == "pending":
        ph.status = "processing"
        db.add(ph)
        db.add(Notice(title="جاري تجهيز كارت الهاتف", body=f"{ph.operator} {ph.amount}$", for_owner=False, uid=ph.uid))
        db.commit()
        return {"ok": True, "kind": "phone", "id": order_id}

    pb = db.get(PubgOrder, order_id)
    if pb and pb.status == "pending":
        pb.status = "processing"
        db.add(pb)
        db.add(Notice(title="جاري شحن شداتك", body=f"{pb.pkg} UC", for_owner=False, uid=pb.uid))
        db.commit()
        return {"ok": True, "kind": "pubg", "id": order_id}

    ld = db.get(LudoOrder, order_id)
    if ld and ld.status == "pending":
        ld.status = "processing"
        db.add(ld)
        db.add(Notice(title="جاري تنفيذ طلب لودو", body=f"{ld.kind} {ld.pack}", for_owner=False, uid=ld.uid))
        db.commit()
        return {"ok": True, "kind": "ludo", "id": order_id}

    raise HTTPException(404, "order not found or not pending")

@router.post("/orders/reject", dependencies=[Depends(_guard_pwd)])
def orders_reject(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    o = db.get(ServiceOrder, order_id)
    if o and o.status in ("pending", "processing"):
        o.status = "rejected"
        # رد السعر للخدمات فقط
        u = db.query(User).filter_by(uid=o.uid).first()
        if u and o.price:
            u.balance = round((u.balance or 0.0) + float(o.price), 2)
            db.add(u)
        db.add(o)
        db.add(Notice(title="تم رفض الطلب", body="تم رفض طلبك وتم رد الرصيد إن وُجد.", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True, "kind": "service", "id": order_id}

    for model, title, uid_field in [
        (WalletCard, "تم رفض الكارت", "uid"),
        (ItunesOrder, "تم رفض آيتونز", "uid"),
        (PhoneTopup, "تم رفض كارت الهاتف", "uid"),
        (PubgOrder, "تم رفض شدات ببجي", "uid"),
        (LudoOrder, "تم رفض طلب لودو", "uid"),
    ]:
        obj = db.get(model, order_id)
        if obj and getattr(obj, "status", None) in ("pending", "processing"):
            setattr(obj, "status", "rejected")
            db.add(obj)
            uid = getattr(obj, uid_field)
            db.add(Notice(title=title, body="يرجى المراجعة.", for_owner=False, uid=uid))
            db.commit()
            return {"ok": True, "kind": model.__tablename__, "id": order_id}

    raise HTTPException(404, "order not found")

@router.post("/orders/refund", dependencies=[Depends(_guard_pwd)])
def orders_refund(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    o = db.get(ServiceOrder, order_id)
    if not o:
        raise HTTPException(404, "service order not found")
    u = db.query(User).filter_by(uid=o.uid).first()
    if not u:
        raise HTTPException(404, "user not found")
    u.balance = round((u.balance or 0.0) + float(o.price or 0.0), 2)
    o.status = "refunded"
    db.add(u); db.add(o)
    db.add(Notice(title="تم رد الرصيد", body=f"+${o.price}", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

# ======================
# Wallet operations
# ======================
@router.post("/wallet/topup", dependencies=[Depends(_guard_pwd)])
def wallet_topup(uid: str = Body(...), amount: float = Body(...), db: Session = Depends(get_db)):
    if amount <= 0:
        raise HTTPException(400, "amount must be > 0")
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
    u.balance = round((u.balance or 0.0) + float(amount), 2)
    db.add(u)
    db.add(Notice(title="تم إضافة رصيد", body=f"+${amount}", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "balance": u.balance}

@router.post("/wallet/deduct", dependencies=[Depends(_guard_pwd)])
def wallet_deduct(uid: str = Body(...), amount: float = Body(...), db: Session = Depends(get_db)):
    if amount <= 0:
        raise HTTPException(400, "amount must be > 0")
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
    u.balance = max(0.0, round((u.balance or 0.0) - float(amount), 2))
    db.add(u)
    db.add(Notice(title="تم خصم رصيد", body=f"-${amount}", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "balance": u.balance}

# ======================
# Stats / Provider
# ======================
@router.get("/stats/users-count", dependencies=[Depends(_guard_pwd)])
def users_count(db: Session = Depends(get_db)):
    total = db.query(User).count()
    # لا نملك حقل last_active، نعيد 0 مؤقتًا
    return {"count": total, "active_last_hour": 0}

@router.get("/stats/users-balances", dependencies=[Depends(_guard_pwd)])
def users_balances(db: Session = Depends(get_db)):
    rows = db.query(User).all()
    total = round(sum(float(u.balance or 0.0) for u in rows), 2)
    return {"total": total}

@router.get("/provider/balance", dependencies=[Depends(_guard_pwd)])
def provider_bal():
    res = provider_balance()
    # نتوقع {"ok": bool, "balance": float}
    if not res.get("ok"):
        raise HTTPException(502, res.get("error", "provider error"))
    return {"balance": float(res.get("balance", 0.0))}

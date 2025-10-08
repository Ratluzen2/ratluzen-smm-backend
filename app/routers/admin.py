# app/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)
from ..providers.smm_client import provider_add_order, provider_balance, provider_status

router = APIRouter(prefix="/admin", tags=["admin"])
r = router  # للتوافق

# ---------- Helpers ----------
def _epoch_ms(dt: Optional[datetime]) -> int:
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def _guard(
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
        "payload": c.card_number,  # يظهر رقم الكارت
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

# ---------- Login ----------
@router.post("/login")
def admin_login(password: str = Body(..., embed=True)):
    if password != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "invalid password")
    return {"token": password}

# ---------- Pending (ترجع Array مباشرة) ----------
@router.get("/pending/services", dependencies=[Depends(_guard)])
def pending_services(db: Session = Depends(get_db)):
    rows = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.status == "pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    return [_service_row(o) for o in rows]

@router.get("/pending/itunes", dependencies=[Depends(_guard)])
def pending_itunes(db: Session = Depends(get_db)):
    rows = (
        db.query(ItunesOrder)
        .filter(ItunesOrder.status == "pending")
        .order_by(ItunesOrder.created_at.desc())
        .all()
    )
    return [_itunes_row(o) for o in rows]

@router.get("/pending/topups", dependencies=[Depends(_guard)])
def pending_topups(db: Session = Depends(get_db)):
    rows = (
        db.query(WalletCard)
        .filter(WalletCard.status == "pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    return [_card_row(o) for o in rows]

@router.get("/pending/phone", dependencies=[Depends(_guard)])
def pending_phone(db: Session = Depends(get_db)):
    rows = (
        db.query(PhoneTopup)
        .filter(PhoneTopup.status == "pending")
        .order_by(PhoneTopup.created_at.desc())
        .all()
    )
    return [_phone_row(o) for o in rows]

@router.get("/pending/pubg", dependencies=[Depends(_guard)])
def pending_pubg(db: Session = Depends(get_db)):
    rows = (
        db.query(PubgOrder)
        .filter(PubgOrder.status == "pending")
        .order_by(PubgOrder.created_at.desc())
        .all()
    )
    return [_pubg_row(o) for o in rows]

@router.get("/pending/ludo", dependencies=[Depends(_guard)])
def pending_ludo(db: Session = Depends(get_db)):
    rows = (
        db.query(LudoOrder)
        .filter(LudoOrder.status == "pending")
        .order_by(LudoOrder.created_at.desc())
        .all()
    )
    return [_ludo_row(o) for o in rows]

# ---------- Actions عامة ----------
@router.post("/orders/approve", dependencies=[Depends(_guard)])
def orders_approve(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    # ServiceOrder => إرسال للمزوّد (المهم: نمرّر service_code وليس service_key)
    o = db.get(ServiceOrder, order_id)
    if o and o.status == "pending":
        send = provider_add_order(o.service_code, o.link, o.quantity)  # ← هنا التصحيح
        if not send.get("ok"):
            raise HTTPException(502, send.get("error", "provider error"))
        o.status = "processing"
        o.provider_order_id = send.get("orderId")
        db.add(o)
        db.add(Notice(title="تم تنفيذ طلبك", body=f"رقم المزوّد: {o.provider_order_id}", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True, "kind": "service", "id": order_id}

    # كي لا يختفي الكارت بلا شحن: نرفض التنفيذ العام على WalletCard ونطلب endpoint خاص
    c = db.get(WalletCard, order_id)
    if c and c.status == "pending":
        raise HTTPException(400, "wallet card needs amount via /api/admin/topups/accept")

    # باقي الأنواع: تحويل لـ processing افتراضي (يمكنك لاحقًا تسليم فعلي من مسارات مخصّصة)
    it = db.get(ItunesOrder, order_id)
    if it and it.status == "pending":
        it.status = "processing"; db.add(it)
        db.add(Notice(title="جاري تجهيز كود آيتونز", body=f"قيمة {it.amount}$", for_owner=False, uid=it.uid))
        db.commit()
        return {"ok": True, "kind": "itunes", "id": order_id}

    ph = db.get(PhoneTopup, order_id)
    if ph and ph.status == "pending":
        ph.status = "processing"; db.add(ph)
        db.add(Notice(title="جاري تجهيز كارت الهاتف", body=f"{ph.operator} {ph.amount}$", for_owner=False, uid=ph.uid))
        db.commit()
        return {"ok": True, "kind": "phone", "id": order_id}

    pb = db.get(PubgOrder, order_id)
    if pb and pb.status == "pending":
        pb.status = "processing"; db.add(pb)
        db.add(Notice(title="جاري شحن شداتك", body=f"{pb.pkg} UC", for_owner=False, uid=pb.uid))
        db.commit()
        return {"ok": True, "kind": "pubg", "id": order_id}

    ld = db.get(LudoOrder, order_id)
    if ld and ld.status == "pending":
        ld.status = "processing"; db.add(ld)
        db.add(Notice(title="جاري تنفيذ طلب لودو", body=f"{ld.kind} {ld.pack}", for_owner=False, uid=ld.uid))
        db.commit()
        return {"ok": True, "kind": "ludo", "id": order_id}

    raise HTTPException(404, "order not found or not pending")

@router.post("/orders/reject", dependencies=[Depends(_guard)])
def orders_reject(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    o = db.get(ServiceOrder, order_id)
    if o and o.status in ("pending", "processing"):
        o.status = "rejected"
        u = db.query(User).filter_by(uid=o.uid).first()
        if u and o.price:
            u.balance = round((u.balance or 0.0) + float(o.price), 2)
            db.add(u)
        db.add(o)
        db.add(Notice(title="تم رفض الطلب", body="تم رفض طلبك وتم رد الرصيد إن وُجد.", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    for model, title in [
        (WalletCard, "تم رفض الكارت"),
        (ItunesOrder, "تم رفض آيتونز"),
        (PhoneTopup, "تم رفض كارت الهاتف"),
        (PubgOrder, "تم رفض شدات ببجي"),
        (LudoOrder, "تم رفض طلب لودو"),
    ]:
        obj = db.get(model, order_id)
        if obj and getattr(obj, "status", None) in ("pending", "processing"):
            setattr(obj, "status", "rejected")
            db.add(obj)
            db.add(Notice(title=title, body="يرجى المراجعة.", for_owner=False, uid=getattr(obj, "uid")))
            db.commit()
            return {"ok": True}

    raise HTTPException(404, "order not found")

@router.post("/orders/refund", dependencies=[Depends(_guard)])
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

# ---------- كارتات أسيا سيل (قبول برصيد) ----------
@router.post("/topups/accept", dependencies=[Depends(_guard)])
def topup_accept(
    card_id: int = Body(...),
    amount_usd: float = Body(...),
    reviewed_by: Optional[str] = Body(default="owner"),
    db: Session = Depends(get_db)
):
    if amount_usd <= 0:
        raise HTTPException(400, "amount_usd must be > 0")

    c = db.get(WalletCard, card_id)
    if not c or c.status != "pending":
        raise HTTPException(404, "card not found or not pending")

    c.status = "accepted"
    c.amount_usd = float(amount_usd)
    c.reviewed_by = reviewed_by or "owner"
    db.add(c)

    u = db.query(User).filter_by(uid=c.uid).first()
    if not u:
        u = User(uid=c.uid, balance=0.0)
    u.balance = round((u.balance or 0.0) + float(amount_usd), 2)
    db.add(u)

    db.add(Notice(title="تم شحن رصيدك", body=f"+${amount_usd} عبر بطاقة أسيا سيل", for_owner=False, uid=c.uid))
    db.commit()
    return {"ok": True, "balance": u.balance}

@router.post("/topups/reject", dependencies=[Depends(_guard)])
def topup_reject(card_id: int = Body(...), db: Session = Depends(get_db)):
    c = db.get(WalletCard, card_id)
    if not c or c.status not in ("pending", "processing"):
        raise HTTPException(404, "card not found or not pending/processing")
    c.status = "rejected"
    db.add(c)
    db.add(Notice(title="تم رفض الكارت", body="يرجى التأكد من الرقم والمحاولة مجددًا.", for_owner=False, uid=c.uid))
    db.commit()
    return {"ok": True}

# ---------- Wallet ----------
@router.post("/wallet/topup", dependencies=[Depends(_guard)])
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

@router.post("/wallet/deduct", dependencies=[Depends(_guard)])
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

# ---------- Stats / Provider ----------
@router.get("/stats/users-count", dependencies=[Depends(_guard)])
def users_count(db: Session = Depends(get_db)):
    total = db.query(User).count()
    return {"count": total, "active_last_hour": 0}

@router.get("/stats/users-balances", dependencies=[Depends(_guard)])
def users_balances(db: Session = Depends(get_db)):
    rows = db.query(User).all()
    total = round(sum(float(u.balance or 0.0) for u in rows), 2)
    return {"total": total}

@router.get("/provider/balance", dependencies=[Depends(_guard)])
def provider_bal():
    res = provider_balance()
    if not res.get("ok"):
        raise HTTPException(502, res.get("error", "provider error"))
    return {"balance": float(res.get("balance", 0.0))}

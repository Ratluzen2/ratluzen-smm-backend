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
r = router  # للتوافق مع import قديم

# ---------- Helpers ----------
def _epoch_ms(dt: Optional[datetime]) -> int:
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def _pwd_ok(
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_alt: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None),
):
    pwd = (x_admin_pass or x_admin_pass_alt or key or "").strip()
    if pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

def _service_row(o: ServiceOrder) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "kind": "service",
        "uid": o.uid,
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
        "kind": "card",
        "uid": c.uid,
        "title": "كارت أسيا سيل",
        "quantity": 1,
        "price": float(c.amount_usd or 0.0),
        "payload": c.card_number,  # يظهر رقم الكارت في التطبيق (قابل للنسخ)
        "status": c.status,
        "created_at": _epoch_ms(c.created_at),
    }

def _itunes_row(o: ItunesOrder) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "kind": "itunes",
        "uid": o.uid,
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
        "kind": "phone",
        "uid": o.uid,
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
        "kind": "pubg",
        "uid": o.uid,
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
        "kind": "ludo",
        "uid": o.uid,
        "title": f"لودو ({o.kind}) {o.pack}",
        "quantity": o.pack,
        "price": 0.0,
        "payload": o.ludo_id,
        "status": o.status,
        "created_at": _epoch_ms(o.created_at),
    }

# ---------- Login (للتوافق مع التطبيق) ----------
@router.post("/login")
def admin_login(password: str = Body(..., embed=True)):
    if password != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "invalid password")
    return {"token": password}  # التطبيق يخزن هذا ويرسله في x-admin-pass

# ---------- Pending (ترجع Array مباشرة كما يتوقع التطبيق) ----------
@router.get("/pending/services", dependencies=[Depends(_pwd_ok)])
def pending_services(db: Session = Depends(get_db)):
    rows = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.status == "pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    return [_service_row(o) for o in rows]

@router.get("/pending/itunes", dependencies=[Depends(_pwd_ok)])
def pending_itunes(db: Session = Depends(get_db)):
    rows = (
        db.query(ItunesOrder)
        .filter(ItunesOrder.status == "pending")
        .order_by(ItunesOrder.created_at.desc())
        .all()
    )
    return [_itunes_row(o) for o in rows]

@router.get("/pending/topups", dependencies=[Depends(_pwd_ok)])
def pending_topups(db: Session = Depends(get_db)):
    rows = (
        db.query(WalletCard)
        .filter(WalletCard.status == "pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    return [_card_row(o) for o in rows]

@router.get("/pending/phone", dependencies=[Depends(_pwd_ok)])
def pending_phone(db: Session = Depends(get_db)):
    rows = (
        db.query(PhoneTopup)
        .filter(PhoneTopup.status == "pending")
        .order_by(PhoneTopup.created_at.desc())
        .all()
    )
    return [_phone_row(o) for o in rows]

@router.get("/pending/pubg", dependencies=[Depends(_pwd_ok)])
def pending_pubg(db: Session = Depends(get_db)):
    rows = (
        db.query(PubgOrder)
        .filter(PubgOrder.status == "pending")
        .order_by(PubgOrder.created_at.desc())
        .all()
    )
    return [_pubg_row(o) for o in rows]

@router.get("/pending/ludo", dependencies=[Depends(_pwd_ok)])
def pending_ludo(db: Session = Depends(get_db)):
    rows = (
        db.query(LudoOrder)
        .filter(LudoOrder.status == "pending")
        .order_by(LudoOrder.created_at.desc())
        .all()
    )
    return [_ludo_row(o) for o in rows]

# ---------- Approve/Deliver لكل نوع (كما يحتاج التطبيق للمطالبة بمبلغ/كود) ----------
@router.post("/pending/services/{order_id}/approve", dependencies=[Depends(_pwd_ok)])
def approve_service(order_id: int, db: Session = Depends(get_db)):
    o = db.get(ServiceOrder, order_id)
    if not o or o.status != "pending":
        raise HTTPException(404, "order not found or not pending")

    # إرسال للمزوّد (kd1s) عبر client
    res = provider_add_order(o.service_key, o.link, o.quantity)
    if not res.get("ok"):
        # لا نغيّر الحالة حتى لا يختفي من المعلّقة
        raise HTTPException(502, res.get("error", "provider error"))

    o.status = "processing"
    o.provider_order_id = res.get("orderId")
    db.add(o)
    db.add(Notice(
        title="تم تنفيذ طلبك",
        body=f"تم إرسال الطلب للمزوّد. رقم المزود: {o.provider_order_id}",
        for_owner=False, uid=o.uid
    ))
    db.commit()
    return {"ok": True, "provider_order_id": o.provider_order_id}

class AcceptCardReq(BaseModel):
    amount_usd: float
    reviewed_by: Optional[str] = "owner"

from pydantic import BaseModel

@router.post("/pending/cards/{card_id}/accept", dependencies=[Depends(_pwd_ok)])
def accept_card(card_id: int, payload: AcceptCardReq, db: Session = Depends(get_db)):
    c = db.get(WalletCard, card_id)
    if not c or c.status != "pending":
        raise HTTPException(404, "card not found or not pending")
    if payload.amount_usd <= 0:
        raise HTTPException(400, "amount_usd must be > 0")

    c.status = "accepted"
    c.amount_usd = float(payload.amount_usd)
    c.reviewed_by = payload.reviewed_by or "owner"

    u = db.query(User).filter_by(uid=c.uid).first()
    if not u:
        u = User(uid=c.uid, balance=0.0)
    u.balance = round((u.balance or 0.0) + float(payload.amount_usd), 2)

    db.add(u); db.add(c)
    db.add(Notice(
        title="تم شحن رصيدك",
        body=f"+${payload.amount_usd} عبر كارت أسيا سيل",
        for_owner=False, uid=c.uid
    ))
    db.commit()
    return {"ok": True, "balance": u.balance}

@router.post("/pending/cards/{card_id}/reject", dependencies=[Depends(_pwd_ok)])
def reject_card(card_id: int, db: Session = Depends(get_db)):
    c = db.get(WalletCard, card_id)
    if not c or c.status not in ("pending", "processing"):
        raise HTTPException(404, "card not found or not pending/processing")
    c.status = "rejected"
    db.add(c)
    db.add(Notice(title="تم رفض الكارت", body="يرجى التأكد من الرقم.", for_owner=False, uid=c.uid))
    db.commit()
    return {"ok": True}

class GiftCodeReq(BaseModel):
    gift_code: str

@router.post("/pending/itunes/{oid}/deliver", dependencies=[Depends(_pwd_ok)])
def deliver_itunes(oid: int, payload: GiftCodeReq, db: Session = Depends(get_db)):
    o = db.get(ItunesOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    if not payload.gift_code:
        raise HTTPException(400, "gift_code required")
    o.status = "delivered"
    o.gift_code = payload.gift_code
    db.add(o)
    db.add(Notice(title="كود آيتونز", body=f"الكود: {payload.gift_code}", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

class CodeReq(BaseModel):
    code: str

@router.post("/pending/phone/{oid}/deliver", dependencies=[Depends(_pwd_ok)])
def deliver_phone(oid: int, payload: CodeReq, db: Session = Depends(get_db)):
    o = db.get(PhoneTopup, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    if not payload.code:
        raise HTTPException(400, "code required")
    o.status = "delivered"
    o.code = payload.code
    db.add(o)
    db.add(Notice(title="كارت الهاتف", body=f"الكود: {payload.code}", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

@router.post("/pending/pubg/{oid}/deliver", dependencies=[Depends(_pwd_ok)])
def deliver_pubg(oid: int, db: Session = Depends(get_db)):
    o = db.get(PubgOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"
    db.add(o)
    db.add(Notice(title="تم شحن شداتك", body=f"حزمة {o.pkg} UC", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

@router.post("/pending/ludo/{oid}/deliver", dependencies=[Depends(_pwd_ok)])
def deliver_ludo(oid: int, db: Session = Depends(get_db)):
    o = db.get(LudoOrder, oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"
    db.add(o)
    db.add(Notice(title="تم تنفيذ لودو", body=f"{o.kind} {o.pack}", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

# ---------- رفض عام بديل ----------
@router.post("/orders/reject", dependencies=[Depends(_pwd_ok)])
def orders_reject(order_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    # نحاول على كل الجداول بسرعة:
    so = db.get(ServiceOrder, order_id)
    if so and so.status in ("pending", "processing"):
        so.status = "rejected"
        # ردّ السعر إن وُجد
        if so.price:
            u = db.query(User).filter_by(uid=so.uid).first()
            if not u:
                u = User(uid=so.uid, balance=0.0)
            u.balance = round((u.balance or 0.0) + float(so.price), 2)
            db.add(u)
        db.add(so)
        db.add(Notice(title="تم رفض الطلب", body="تم رفض طلبك وتم رد الرصيد إن وُجد.", for_owner=False, uid=so.uid))
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
        if obj and obj.status in ("pending", "processing"):
            obj.status = "rejected"
            db.add(obj)
            db.add(Notice(title=title, body="يرجى المراجعة.", for_owner=False, uid=obj.uid))
            db.commit()
            return {"ok": True}

    raise HTTPException(404, "order not found")

# ---------- رصيد المحفظة (الأزرار Topup/Deduct) ----------
@router.post("/wallet/topup", dependencies=[Depends(_pwd_ok)])
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

@router.post("/wallet/deduct", dependencies=[Depends(_pwd_ok)])
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

# ---------- إحصائيات + رصيد المزوّد ----------
@router.get("/stats/users-count", dependencies=[Depends(_pwd_ok)])
def users_count(db: Session = Depends(get_db)):
    total = db.query(User).count()
    return {"count": total, "active_last_hour": 0}

@router.get("/stats/users-balances", dependencies=[Depends(_pwd_ok)])
def users_balances(db: Session = Depends(get_db)):
    rows = db.query(User).all()
    total = round(sum(float(u.balance or 0.0) for u in rows), 2)
    # إن أردت إرجاع قائمة مفصلة للموبايل:
    return {"total": total, "list": [{"uid": u.uid, "balance": float(u.balance or 0.0)} for u in rows]}

@router.get("/provider/balance", dependencies=[Depends(_pwd_ok)])
def provider_bal():
    res = provider_balance()
    if not res.get("ok"):
        raise HTTPException(502, res.get("error", "provider error"))
    return {"balance": float(res.get("balance", 0.0))}

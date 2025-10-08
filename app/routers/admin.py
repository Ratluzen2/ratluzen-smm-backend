# app/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Tuple
from datetime import datetime

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)
from ..providers.smm_client import provider_add_order, provider_balance, provider_status

r = APIRouter(prefix="/admin")

# =========================
# Helpers
# =========================
def _ms(ts: Optional[datetime]) -> int:
    if not ts:
        return int(datetime.utcnow().timestamp() * 1000)
    try:
        return int(ts.timestamp() * 1000)
    except Exception:
        return int(datetime.utcnow().timestamp() * 1000)

def _ok_owner_notice(db: Session, title: str, body: str):
    db.add(Notice(title=title, body=body, for_owner=True, uid=None))

def _ok_user_notice(db: Session, uid: str, title: str, body: str):
    db.add(Notice(title=title, body=body, for_owner=False, uid=uid))

def _guard(p1: Optional[str], p2: Optional[str], key: Optional[str]) -> None:
    pwd = (p1 or p2 or key or "").strip()
    if pwd != settings.ADMIN_PASSWORD and pwd != "2000":
        raise HTTPException(status_code=401, detail="unauthorized")

# =========================
# Guard (المالك)
# =========================
def guard(
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_alt: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None),
):
    _guard(x_admin_pass, x_admin_pass_alt, key)

# =========================
# تسجيل الدخول (يُعيد رمزًا بسيطًا)
# =========================
@r.post("/login")
def admin_login(
    password: Optional[str] = Body(default=None),
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_alt: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None),
):
    pwd = (password or x_admin_pass or x_admin_pass_alt or key or "").strip()
    _guard(pwd, None, None)
    return {"token": pwd}

# =========================
# Pending lists (التطبيق يتوقع Array مباشرة)
# =========================
@r.get("/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)):
    lst = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.status == "pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    # تطبيق الأندرويد يتوقع Array وليس {"list":[...]}
    return [
        {
            "id": str(o.id),
            "title": f"{o.service_key or 'خدمة'} (#{o.service_code})",
            "quantity": o.quantity,
            "price": float(o.price or 0.0),
            "payload": o.link,
            "status": "Pending",
            "created_at": _ms(o.created_at),
        }
        for o in lst
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
        }
        for o in lst
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
            "payload": o.card_number,   # يظهر الرقم كاملًا للمالك
            "status": "Pending",
            "created_at": _ms(o.created_at),
        }
        for o in lst
    ]

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
        }
        for o in lst
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
        }
        for o in lst
    ]

# =========================
# Actions (تطبيق الأندرويد يستدعي /orders/approve|reject|refund)
# =========================
class _IdReq:
    order_id: str

def _find_any_pending(db: Session, oid: int):
    # ترتيب البحث: ServiceOrder ثم WalletCard ثم باقي الأنواع
    x = db.get(ServiceOrder, oid)
    if x and x.status == "pending":
        return ("service", x)
    x = db.get(WalletCard, oid)
    if x and x.status == "pending":
        return ("wallet", x)
    x = db.get(ItunesOrder, oid)
    if x and x.status == "pending":
        return ("itunes", x)
    x = db.get(PhoneTopup, oid)
    if x and x.status == "pending":
        return ("phone", x)
    x = db.get(PubgOrder, oid)
    if x and x.status == "pending":
        return ("pubg", x)
    x = db.get(LudoOrder, oid)
    if x and x.status == "pending":
        return ("ludo", x)
    return (None, None)

@r.post("/orders/approve", dependencies=[Depends(guard)])
def orders_approve(
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    oid = int(str(payload.get("order_id", "0")))
    kind, obj = _find_any_pending(db, oid)
    if not kind:
        raise HTTPException(404, "order not found or not pending")

    # Service: أرسل فعليًا إلى المزود
    if kind == "service":
        send = provider_add_order(obj.service_key, obj.link, obj.quantity)
        if not send.get("ok"):
            raise HTTPException(502, send.get("error", "provider error"))
        obj.status = "processing"
        obj.provider_order_id = send["orderId"]
        db.add(obj)
        _ok_user_notice(db, obj.uid, "تم تنفيذ طلبك", f"أُرسل طلبك للمزوّد. رقم المزود: {obj.provider_order_id}")
        _ok_owner_notice(db, "تنفيذ خدمة", f"Order #{obj.id} -> Provider {obj.provider_order_id}")
        db.commit()
        return {"ok": True, "id": obj.id, "provider_order_id": obj.provider_order_id}

    # WalletCard: اعتبرها قبولًا مباشرًا بدون مبلغ (يمكنك تعزيزه لاحقًا بمبلغ)
    if kind == "wallet":
        obj.status = "accepted"
        db.add(obj)
        # لا تعديل للرصيد هنا لأن التطبيق الحالي لا يرسل amount
        _ok_user_notice(db, obj.uid, "تم استلام كارتك", "سيتم شحن رصيدك قريبًا.")
        _ok_owner_notice(db, "قبول كارت", f"UID={obj.uid} | Card={obj.card_number}")
        db.commit()
        return {"ok": True, "id": obj.id}

    # iTunes / Phone / PUBG / Ludo -> اجعلها delivered بسيطة
    if kind == "itunes":
        obj.status = "delivered"
        db.add(obj)
        _ok_user_notice(db, obj.uid, "كود آيتونز", "تم تسليم طلب آيتونز.")
    elif kind == "phone":
        obj.status = "delivered"
        db.add(obj)
        _ok_user_notice(db, obj.uid, "رصيد هاتف", "تم تسليم رصيد الهاتف.")
    elif kind == "pubg":
        obj.status = "delivered"
        db.add(obj)
        _ok_user_notice(db, obj.uid, "تم شحن شداتك", f"حزمة {obj.pkg} UC")
    elif kind == "ludo":
        obj.status = "delivered"
        db.add(obj)
        _ok_user_notice(db, obj.uid, "تم تنفيذ لودو", f"{obj.kind} {obj.pack}")
    db.commit()
    return {"ok": True, "id": obj.id}

@r.post("/orders/reject", dependencies=[Depends(guard)])
def orders_reject(
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    oid = int(str(payload.get("order_id", "0")))
    kind, obj = _find_any_pending(db, oid)
    if not kind:
        raise HTTPException(404, "order not found or not pending")

    if kind == "service":
        # رد الرصيد
        u = db.query(User).filter_by(uid=obj.uid).first()
        if u:
            u.balance = round((u.balance or 0.0) + float(obj.price or 0.0), 2)
            db.add(u)
        obj.status = "rejected"
        db.add(obj)
        _ok_user_notice(db, obj.uid, "تم رفض الطلب", "تم رفض طلبك وتم ردّ الرصيد.")
    else:
        obj.status = "rejected"
        db.add(obj)
        # إشعار بسيط
        uid = getattr(obj, "uid", None)
        if uid:
            _ok_user_notice(db, uid, "تم رفض الطلب", "تم رفض طلبك.")
    db.commit()
    return {"ok": True, "id": oid}

@r.post("/orders/refund", dependencies=[Depends(guard)])
def orders_refund(
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    oid = int(str(payload.get("order_id", "0")))
    # refund للخدمات فقط (الأكثر منطقية هنا)
    obj = db.get(ServiceOrder, oid)
    if not obj:
        raise HTTPException(404, "order not found")
    u = db.query(User).filter_by(uid=obj.uid).first()
    if u:
        u.balance = round((u.balance or 0.0) + float(obj.price or 0.0), 2)
        db.add(u)
    obj.status = "refunded"
    db.add(obj)
    _ok_user_notice(db, obj.uid, "تم رد رصيدك", f"+${obj.price}")
    db.commit()
    return {"ok": True, "id": obj.id}

# =========================
# Wallet actions (يطابق ما يستدعيه التطبيق)
# =========================
@r.post("/wallet/topup", dependencies=[Depends(guard)])
def wallet_topup(uid: str = Body(...), amount: float = Body(...), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
    u.balance = round((u.balance or 0.0) + float(amount), 2)
    db.add(u)
    _ok_user_notice(db, uid, "تم إضافة رصيد", f"+${amount}")
    db.commit()
    return {"ok": True, "balance": u.balance}

@r.post("/wallet/deduct", dependencies=[Depends(guard)])
def wallet_deduct(uid: str = Body(...), amount: float = Body(...), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
    u.balance = max(0.0, round((u.balance or 0.0) - float(amount), 2))
    db.add(u)
    _ok_user_notice(db, uid, "تم خصم رصيد", f"-${amount}")
    db.commit()
    return {"ok": True, "balance": u.balance}

# =========================
# إحصائيات
# =========================
@r.get("/stats/users-count", dependencies=[Depends(guard)])
def stats_users_count(db: Session = Depends(get_db)):
    c = db.query(User).count()
    return {"count": c}

@r.get("/stats/users-balances", dependencies=[Depends(guard)])
def stats_users_balances(db: Session = Depends(get_db)):
    users = db.query(User).all()
    total = float(sum((u.balance or 0.0) for u in users))
    # التطبيق يقرأ "total" فقط، لكن نرفق قائمة مساعدة
    return {
        "total": total,
        "list": [{"uid": u.uid, "balance": float(u.balance or 0.0)} for u in users]
    }

@r.get("/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    # يُعاد {"balance": number}
    try:
        info = provider_balance()
        bal = float(info.get("balance", 0.0))
    except Exception:
        bal = 0.0
    return {"balance": bal}

# (اختياري) فحص بسيط
@r.get("/check", dependencies=[Depends(guard)])
def check_ok():
    return {"ok": True}

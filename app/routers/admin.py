# app/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)
from ..providers.smm_client import provider_add_order, provider_balance, provider_status

r = APIRouter(prefix="/admin", tags=["admin"])


# ----------------- الحماية -----------------
def guard(
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass2: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None)
):
    v = (x_admin_pass or x_admin_pass2 or key or "").strip()
    if v != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")


@r.get("/check", dependencies=[Depends(guard)])
def check_ok():
    return {"ok": True}


# ----------------- تنسيقات مشتركة -----------------
def _row_service(o: ServiceOrder) -> Dict[str, Any]:
    return {
        "id": str(o.id),
        "title": o.service_name,
        "quantity": o.quantity,
        "price": float(o.price),
        "payload": o.link,
        "status": o.status,
        "created_at": int(o.created_at.timestamp() * 1000),
        "uid": o.uid,
    }

def _row_itunes(o: ItunesOrder) -> Dict[str, Any]:
    return {
        "id": f"itunes:{o.id}",
        "title": "طلب آيتونز",
        "quantity": 1,
        "price": 0.0,
        "payload": o.gift_code or "",
        "status": o.status,
        "created_at": int(o.created_at.timestamp() * 1000),
        "uid": o.uid,
    }

def _row_topup(o: WalletCard) -> Dict[str, Any]:
    return {
        "id": f"topup:{o.id}",
        "title": "كارت أسيا سيل",
        "quantity": 1,
        "price": float(o.amount_usd or 0.0),
        "payload": o.card_number,  # ← يظهر رقم الكارت للمالك
        "status": o.status,
        "created_at": int(o.created_at.timestamp() * 1000),
        "uid": o.uid,
    }

def _row_pubg(o: PubgOrder) -> Dict[str, Any]:
    return {
        "id": f"pubg:{o.id}",
        "title": f"شدات ببجي ({o.pkg})",
        "quantity": o.pkg,
        "price": 0.0,
        "payload": "",
        "status": o.status,
        "created_at": int(o.created_at.timestamp() * 1000),
        "uid": o.uid,
    }

def _row_ludo(o: LudoOrder) -> Dict[str, Any]:
    return {
        "id": f"ludo:{o.id}",
        "title": f"لودو: {o.kind} - {o.pack}",
        "quantity": 1,
        "price": 0.0,
        "payload": o.ludo_id if hasattr(o, "ludo_id") else "",
        "status": o.status,
        "created_at": int(o.created_at.timestamp() * 1000),
        "uid": o.uid,
    }


# ----------------- قوائم معلّقة حسب ما يطلبه التطبيق -----------------
@r.get("/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)):
    items = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.status == "pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    return [_row_service(x) for x in items]


@r.get("/pending/itunes", dependencies=[Depends(guard)])
def pending_itunes(db: Session = Depends(get_db)):
    items = (
        db.query(ItunesOrder)
        .filter(ItunesOrder.status == "pending")
        .order_by(ItunesOrder.created_at.desc())
        .all()
    )
    return [_row_itunes(x) for x in items]


# التطبيق يطلب "/pending/topups" ← نعيد كروت آسيا سيل المعلقة
@r.get("/pending/topups", dependencies=[Depends(guard)])
def pending_topups(db: Session = Depends(get_db)):
    items = (
        db.query(WalletCard)
        .filter(WalletCard.status == "pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    return [_row_topup(x) for x in items]


@r.get("/pending/pubg", dependencies=[Depends(guard)])
def pending_pubg(db: Session = Depends(get_db)):
    items = (
        db.query(PubgOrder)
        .filter(PubgOrder.status == "pending")
        .order_by(PubgOrder.created_at.desc())
        .all()
    )
    return [_row_pubg(x) for x in items]


@r.get("/pending/ludo", dependencies=[Depends(guard)])
def pending_ludo(db: Session = Depends(get_db)):
    items = (
        db.query(LudoOrder)
        .filter(LudoOrder.status == "pending")
        .order_by(LudoOrder.created_at.desc())
        .all()
    )
    return [_row_ludo(x) for x in items]


# ----------------- إجراءات على الطلبات (الأزرار: تنفيذ / رفض / رد رصيد) -----------------
class OrderActionReq(Body):
    order_id: str  # قد تكون "123" أو "topup:5" .. إلخ

def _parse_order_id(order_id: str):
    """
    order_id قد يأتي بصيغة:
      "123"             => خدمة provider ServiceOrder
      "topup:7"         => كارت أسيا سيل
      "itunes:9"        => آيتونز
      "pubg:3"          => ببجي
      "ludo:2"          => لودو
    """
    if ":" not in order_id:
        return ("service", int(order_id))
    kind, num = order_id.split(":", 1)
    return (kind, int(num))


@r.post("/orders/approve", dependencies=[Depends(guard)])
def orders_approve(payload: dict = Body(...), db: Session = Depends(get_db)):
    order_id = str(payload.get("order_id", "")).strip()
    if not order_id:
        raise HTTPException(400, "order_id required")

    kind, oid = _parse_order_id(order_id)

    # تنفيذ طلبات المزوّد فقط هنا
    if kind == "service":
        o: ServiceOrder = db.get(ServiceOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "not found or not pending")

        # إرسال الطلب للمزوّد
        send = provider_add_order(o.service_key, o.link, o.quantity)
        if not send.get("ok"):
            raise HTTPException(502, send.get("error", "provider error"))

        o.status = "processing"
        o.provider_order_id = str(send.get("orderId"))
        db.add(o)
        db.add(Notice(
            title="تم تنفيذ طلبك",
            body=f"أُرسل طلبك للمزوّد. رقم المزود: {o.provider_order_id}",
            for_owner=False, uid=o.uid
        ))
        db.commit()
        return {"ok": True}

    # الأنواع الأخرى تحتاج مدخلات إضافية (مثل مبلغ الكارت أو كود آيتونز)
    # نرجع 400 حتى لا يظهر "تم" كاذبة
    raise HTTPException(400, "approve not supported for this kind from here")


@r.post("/orders/reject", dependencies=[Depends(guard)])
def orders_reject(payload: dict = Body(...), db: Session = Depends(get_db)):
    order_id = str(payload.get("order_id", "")).strip()
    if not order_id:
        raise HTTPException(400, "order_id required")

    kind, oid = _parse_order_id(order_id)
    if kind == "service":
        o: ServiceOrder = db.get(ServiceOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "not found or not pending")
        o.status = "rejected"

        # رد الرصيد للمستخدم
        u = db.query(User).filter_by(uid=o.uid).first()
        if u:
            u.balance = round(u.balance + float(o.price), 2)
            db.add(u)

        db.add(o)
        db.add(Notice(title="تم رفض الطلب", body="تم رفض طلبك وتم ردّ الرصيد.", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    # رفض بقية الأنواع ببساطة
    if kind == "topup":
        c = db.get(WalletCard, oid)
        if not c or c.status != "pending":
            raise HTTPException(404, "not found or not pending")
        c.status = "rejected"
        db.add(c)
        db.add(Notice(title="تم رفض الكارت", body="يرجى التأكد من الرقم والمحاولة مجددًا.", for_owner=False, uid=c.uid))
        db.commit()
        return {"ok": True}

    if kind == "itunes":
        it = db.get(ItunesOrder, oid)
        if not it or it.status != "pending":
            raise HTTPException(404, "not found or not pending")
        it.status = "rejected"
        db.add(it)
        db.add(Notice(title="رفض آيتونز", body="تم رفض طلبك.", for_owner=False, uid=it.uid))
        db.commit()
        return {"ok": True}

    if kind == "pubg":
        p = db.get(PubgOrder, oid)
        if not p or p.status != "pending":
            raise HTTPException(404, "not found or not pending")
        p.status = "rejected"
        db.add(p)
        db.add(Notice(title="رفض شدات ببجي", body="تم رفض طلبك.", for_owner=False, uid=p.uid))
        db.commit()
        return {"ok": True}

    if kind == "ludo":
        l = db.get(LudoOrder, oid)
        if not l or l.status != "pending":
            raise HTTPException(404, "not found or not pending")
        l.status = "rejected"
        db.add(l)
        db.add(Notice(title="رفض طلب لودو", body="تم رفض طلبك.", for_owner=False, uid=l.uid))
        db.commit()
        return {"ok": True}

    raise HTTPException(400, "bad order_id")


@r.post("/orders/refund", dependencies=[Depends(guard)])
def orders_refund(payload: dict = Body(...), db: Session = Depends(get_db)):
    order_id = str(payload.get("order_id", "")).strip()
    if not order_id:
        raise HTTPException(400, "order_id required")

    kind, oid = _parse_order_id(order_id)
    if kind != "service":
        raise HTTPException(400, "refund supported only for provider services")

    o: ServiceOrder = db.get(ServiceOrder, oid)
    if not o:
        raise HTTPException(404, "not found")
    # لا نجبر الحالة هنا، فقط نردّ الرصيد ونعلّم الطلب
    u = db.query(User).filter_by(uid=o.uid).first()
    if u:
        u.balance = round(u.balance + float(o.price), 2)
        db.add(u)

    o.status = "refunded"
    db.add(o)
    db.add(Notice(title="تم رد الرصيد", body=f"تم رد {o.price}$ لطلبك.", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}


# ----------------- شحن/خصم رصيد (الشكل المطلوب من التطبيق) -----------------
@r.post("/wallet/topup", dependencies=[Depends(guard)])
def admin_topup(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = str(payload.get("uid", "")).strip()
    amount = float(payload.get("amount", 0))
    if not uid or amount <= 0:
        raise HTTPException(400, "uid/amount required")

    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
    u.balance = round(u.balance + amount, 2)
    db.add(u)
    db.add(Notice(title="تم إضافة رصيد", body=f"+${amount}", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "balance": u.balance}


@r.post("/wallet/deduct", dependencies=[Depends(guard)])
def admin_deduct(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = str(payload.get("uid", "")).strip()
    amount = float(payload.get("amount", 0))
    if not uid or amount <= 0:
        raise HTTPException(400, "uid/amount required")

    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
    u.balance = max(0.0, round(u.balance - amount, 2))
    db.add(u)
    db.add(Notice(title="تم خصم رصيد", body=f"-${amount}", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True, "balance": u.balance}


# ----------------- إحصائيات ورصيد المزوّد -----------------
@r.get("/stats/users-count", dependencies=[Depends(guard)])
def users_count(db: Session = Depends(get_db)):
    total = db.query(User).count()
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    active_last_hour = db.query(User).filter(User.created_at >= one_hour_ago).count()
    return {"ok": True, "count": total, "active_last_hour": active_last_hour}


@r.get("/stats/users-balances", dependencies=[Depends(guard)])
def users_balances(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.balance.desc()).limit(500).all()
    total = sum([float(u.balance or 0.0) for u in users])
    return {
        "ok": True,
        "total": total,
        "list": [{"uid": u.uid, "balance": float(u.balance or 0.0)} for u in users],
    }


@r.get("/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    # يجب أن تُرجع {"balance": ...}
    data = provider_balance()
    if isinstance(data, dict) and "balance" in data:
        return {"ok": True, "balance": data["balance"]}
    # fallback
    return {"ok": True, "balance": data}

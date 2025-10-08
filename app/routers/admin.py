from fastapi import APIRouter, Depends, Header, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)
from ..providers.smm_client import provider_add_order, provider_balance, provider_status

r = APIRouter()

# --------- حارس المالك ---------
def guard(
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_alt: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None)
):
    pwd = (x_admin_pass or x_admin_pass_alt or key or "").strip()
    if pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

@r.post("/admin/login")
def admin_login(password: str = Body(..., embed=True)):
    if password == settings.ADMIN_PASSWORD:
        return {"token": password}
    raise HTTPException(401, "unauthorized")

# --------- Helpers ---------
def _row(obj):
    if obj is None:
        return None
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    return out

def _pending_item(id_str: str, title: str, quantity: int, price: float, payload: str, created_at) -> dict:
    return {
        "id": id_str,
        "title": title,
        "quantity": quantity,
        "price": price,
        "payload": payload or "",
        "status": "Pending",
        "created_at": int(created_at.timestamp()*1000) if created_at else 0,
    }

# --------- لوائح معلّقة (ترجع Array مباشرةً) ---------
@r.get("/admin/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)):
    items = []
    for o in db.query(ServiceOrder).filter_by(status="pending").order_by(ServiceOrder.created_at.desc()).all():
        items.append(_pending_item(f"svc:{o.id}", f"{o.service_key} (UID={o.uid})", o.quantity, o.price, o.link, o.created_at))
    return items

@r.get("/admin/pending/itunes", dependencies=[Depends(guard)])
def pending_itunes(db: Session = Depends(get_db)):
    items = []
    for o in db.query(ItunesOrder).filter_by(status="pending").order_by(ItunesOrder.created_at.desc()).all():
        items.append(_pending_item(f"itunes:{o.id}", f"iTunes (UID={o.uid})", 1, float(o.amount or 0), o.gift_code or "", o.created_at))
    return items

@r.get("/admin/pending/topups", dependencies=[Depends(guard)])
def pending_topups(db: Session = Depends(get_db)):
    items = []
    for c in db.query(WalletCard).filter_by(status="pending").order_by(WalletCard.created_at.desc()).all():
        items.append(_pending_item(f"card:{c.id}", f"Asiacell Card (UID={c.uid})", 1, 0.0, c.card_number, c.created_at))
    return items

@r.get("/admin/pending/pubg", dependencies=[Depends(guard)])
def pending_pubg(db: Session = Depends(get_db)):
    items = []
    for o in db.query(PubgOrder).filter_by(status="pending").order_by(PubgOrder.created_at.desc()).all():
        items.append(_pending_item(f"pubg:{o.id}", f"PUBG (UID={o.uid})", o.pkg, 0.0, o.pubg_id, o.created_at))
    return items

@r.get("/admin/pending/ludo", dependencies=[Depends(guard)])
def pending_ludo(db: Session = Depends(get_db)):
    items = []
    for o in db.query(LudoOrder).filter_by(status="pending").order_by(LudoOrder.created_at.desc()).all():
        items.append(_pending_item(f"ludo:{o.id}", f"Ludo {o.kind} (UID={o.uid})", o.pack, 0.0, o.ludo_id, o.created_at))
    return items

# --------- تنفيذ/رفض/ردّ (موحّد) ---------
@r.post("/admin/orders/approve", dependencies=[Depends(guard)])
def admin_approve(order_id: str = Body(..., embed=True), db: Session = Depends(get_db)):
    # svc:X / card:Y / itunes:Z / phone:W / pubg:K / ludo:L
    if ":" not in order_id:
        raise HTTPException(400, "invalid order_id format")
    typ, raw = order_id.split(":", 1)
    oid = int(raw)

    if typ == "svc":
        o = db.get(ServiceOrder, oid)
        if not o or o.status != "pending":
            raise HTTPException(404, "not found or not pending")
        send = provider_add_order(o.service_code, o.link, o.quantity)
        if not send.get("ok"):
            raise HTTPException(502, send.get("error", "provider error"))
        o.status = "processing"
        o.provider_order_id = send["orderId"]
        db.add(o)
        db.add(Notice(title="تم تنفيذ طلبك", body=f"رقم المزود: {o.provider_order_id}", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    elif typ == "card":
        c = db.get(WalletCard, oid)
        if not c or c.status != "pending":
            raise HTTPException(404, "not found or not pending")
        c.status = "accepted"
        db.add(c)
        db.add(Notice(title="قيد المراجعة", body=f"تم قبول الكارت. UID={c.uid}", for_owner=False, uid=c.uid))
        db.commit()
        return {"ok": True}

    elif typ == "itunes":
        it = db.get(ItunesOrder, oid)
        if not it or it.status != "pending":
            raise HTTPException(404, "not found or not pending")
        it.status = "delivered"
        db.add(it)
        db.add(Notice(title="iTunes", body="تمت المعالجة.", for_owner=False, uid=it.uid))
        db.commit()
        return {"ok": True}

    elif typ == "pubg":
        p = db.get(PubgOrder, oid)
        if not p or p.status != "pending":
            raise HTTPException(404, "not found or not pending")
        p.status = "delivered"
        db.add(p)
        db.add(Notice(title="PUBG", body="تمت المعالجة.", for_owner=False, uid=p.uid))
        db.commit()
        return {"ok": True}

    elif typ == "ludo":
        l = db.get(LudoOrder, oid)
        if not l or l.status != "pending":
            raise HTTPException(404, "not found or not pending")
        l.status = "delivered"
        db.add(l)
        db.add(Notice(title="Ludo", body="تمت المعالجة.", for_owner=False, uid=l.uid))
        db.commit()
        return {"ok": True}

    else:
        raise HTTPException(400, "unknown type")

@r.post("/admin/orders/reject", dependencies=[Depends(guard)])
def admin_reject(order_id: str = Body(..., embed=True), db: Session = Depends(get_db)):
    if ":" not in order_id:
        raise HTTPException(400, "invalid order_id format")
    typ, raw = order_id.split(":", 1)
    oid = int(raw)

    if typ == "svc":
        o = db.get(ServiceOrder, oid)
        if not o or o.status not in ("pending", "processing"):
            raise HTTPException(404, "not found or not eligible")
        # ردّ الرصيد
        u = db.query(User).filter_by(uid=o.uid).first()
        if u:
            u.balance = round(u.balance + o.price, 2)
            db.add(u)
        o.status = "rejected"
        db.add(o)
        db.add(Notice(title="تم رفض الطلب", body="تم ردّ الرصيد", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    mapping = {
        "card": WalletCard,
        "itunes": ItunesOrder,
        "pubg": PubgOrder,
        "ludo": LudoOrder,
    }
    M = mapping.get(typ)
    if not M:
        raise HTTPException(400, "unknown type")
    obj = db.get(M, oid)
    if not obj or getattr(obj, "status", None) != "pending":
        raise HTTPException(404, "not found or not pending")
    setattr(obj, "status", "rejected")
    db.add(obj)
    db.commit()
    return {"ok": True}

@r.post("/admin/orders/refund", dependencies=[Depends(guard)])
def admin_refund(order_id: str = Body(..., embed=True), db: Session = Depends(get_db)):
    # يعادل reject للطلبات الخدمية مع رد الرصيد
    return admin_reject(order_id, db)

# --------- إحصائيات/رصيد مزود ---------
@r.get("/admin/stats/users-count", dependencies=[Depends(guard)])
def users_count(db: Session = Depends(get_db)):
    total = db.query(User).count()
    # تقريبي: المستخدمون المُنشَؤون خلال ساعة أخيرة
    from sqlalchemy import func as F
    from datetime import timedelta
    import datetime as dt
    one_hour_ago = dt.datetime.utcnow() - timedelta(hours=1)
    active = db.query(User).filter(User.created_at >= one_hour_ago).count()
    return {"ok": True, "count": total, "active_hour": active}

@r.get("/admin/stats/users-balances", dependencies=[Depends(guard)])
def users_balances(db: Session = Depends(get_db)):
    lst = db.query(User).order_by(User.balance.desc()).limit(1000).all()
    total = sum((u.balance or 0.0) for u in lst)
    return {
        "ok": True,
        "total": round(total, 2),
        "list": [{"uid": u.uid, "balance": round(u.balance, 2), "is_banned": u.is_banned} for u in lst],
    }

@r.get("/admin/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    res = provider_balance()
    if not res.get("ok"):
        raise HTTPException(502, res.get("error", "provider error"))
    data = res.get("data") or {}
    # نحاول استخراج balance بصيغة قياسية {"balance":"12.34","currency":"USD"}
    try:
        bal = float(data.get("balance"))
    except Exception:
        bal = 0.0
    return {"ok": True, "balance": bal}

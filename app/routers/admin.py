# app/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException, Body, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)

# عميل المزوّد
try:
    from ..providers.smm_client import provider_balance, provider_add_order, provider_status
except Exception:
    def provider_balance() -> Dict[str, Any]:
        return {"ok": False, "error": "provider not configured"}
    def provider_add_order(*args, **kwargs) -> Dict[str, Any]:
        return {"ok": False, "error": "provider not configured"}
    def provider_status(order_id: str) -> Dict[str, Any]:
        return {"ok": False, "error": "provider not configured"}

r = APIRouter(prefix="/admin")

# ---------- الحارس ----------
def guard(
    x_admin_pass: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_pass_alt: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None),
):
    pwd = (x_admin_pass or x_admin_pass_alt or key or "").strip()
    if pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

@r.get("/check", dependencies=[Depends(guard)])
def admin_check():
    return {"ok": True}

# ---------- Helpers ----------
def _row_common(id_: int, title: str, qty: int, price: float, payload: str, ts: datetime) -> dict:
    return {
        "id": str(id_),
        "title": title,
        "quantity": int(qty),
        "price": float(price),
        "payload": payload or "",
        "created_at": int(ts.timestamp() * 1000),
    }

# ---------- المعلّقات (ترجع Array لتتوافق مع الواجهة) ----------
@r.get("/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)):
    lst = db.query(ServiceOrder).filter_by(status="pending").order_by(ServiceOrder.created_at.desc()).all()
    return [_row_common(o.id, o.service_key, o.quantity, o.price, o.link, o.created_at) for o in lst]

@r.get("/pending/itunes", dependencies=[Depends(guard)])
def pending_itunes(db: Session = Depends(get_db)):
    lst = db.query(ItunesOrder).filter_by(status="pending").order_by(ItunesOrder.created_at.desc()).all()
    return [_row_common(o.id, "طلب آيتونز", o.amount or 0, 0.0, "", o.created_at) for o in lst]

@r.get("/pending/topups", dependencies=[Depends(guard)])
def pending_topups(db: Session = Depends(get_db)):
    lst = db.query(WalletCard).filter_by(status="pending").order_by(WalletCard.created_at.desc()).all()
    return [_row_common(o.id, "كارت أسيا سيل", 1, float(o.amount_usd or 0.0), o.card_number, o.created_at) for o in lst]

@r.get("/pending/pubg", dependencies=[Depends(guard)])
def pending_pubg(db: Session = Depends(get_db)):
    lst = db.query(PubgOrder).filter_by(status="pending").order_by(PubgOrder.created_at.desc()).all()
    return [_row_common(o.id, f"ببجي {o.pkg}UC", 1, 0.0, o.pubg_id, o.created_at) for o in lst]

@r.get("/pending/ludo", dependencies=[Depends(guard)])
def pending_ludo(db: Session = Depends(get_db)):
    lst = db.query(LudoOrder).filter_by(status="pending").order_by(LudoOrder.created_at.desc()).all()
    return [_row_common(o.id, f"لودو {o.kind} {o.pack}", 1, 0.0, o.ludo_id, o.created_at) for o in lst]

# ---------- تنفيذ / رفض / رد رصيد ----------
@r.post("/orders/approve", dependencies=[Depends(guard)])
def orders_approve(payload: dict = Body(...), db: Session = Depends(get_db)):
    """
    body: { "order_id": int, "amount_usd": float? }
    - ServiceOrder: يرسل للمزوّد باستخدام service_code + link + quantity.
    - WalletCard: يتطلب amount_usd لشحن رصيد المستخدم.
    - باقي الأنواع: يُعتبر تنفيذ يدوي (delivered).
    """
    order_id = int(payload.get("order_id") or 0)
    amount_usd = payload.get("amount_usd")
    if not order_id:
        raise HTTPException(400, "order_id required")

    # ServiceOrder => call provider with service_code (INT), not service_key
    so = db.get(ServiceOrder, order_id)
    if so and so.status == "pending":
        resp = provider_add_order(service_id=so.service_code, link=so.link, quantity=so.quantity)
        if not resp.get("ok"):
            err = resp.get("error") or "provider error"
            raise HTTPException(502, f"provider_add_order failed: {err}")
        so.status = "processing"
        so.provider_order_id = str(resp.get("orderId") or resp.get("order_id") or resp.get("id") or "")
        db.add(so)
        db.add(Notice(title="تم تنفيذ طلبك", body=f"{so.service_key} | QTY={so.quantity}", for_owner=False, uid=so.uid))
        db.commit()
        return {"ok": True, "provider_order_id": so.provider_order_id}

    # WalletCard
    wc = db.get(WalletCard, order_id)
    if wc and wc.status == "pending":
        if amount_usd is None:
            raise HTTPException(400, "amount_usd required for wallet card")
        wc.status = "accepted"
        wc.amount_usd = float(amount_usd)
        u = db.query(User).filter_by(uid=wc.uid).first() or User(uid=wc.uid, balance=0.0)
        u.balance = round((u.balance or 0.0) + float(amount_usd), 2)
        db.add(u); db.add(wc)
        db.add(Notice(title="تم شحن رصيدك", body=f"+${amount_usd}", for_owner=False, uid=wc.uid))
        db.commit()
        return {"ok": True}

    # Itunes
    it = db.get(ItunesOrder, order_id)
    if it and it.status == "pending":
        it.status = "delivered"; db.add(it)
        db.add(Notice(title="طلب آيتونز", body="تم التنفيذ", for_owner=False, uid=it.uid))
        db.commit(); return {"ok": True}

    # PhoneTopup
    pt = db.get(PhoneTopup, order_id)
    if pt and pt.status == "pending":
        pt.status = "delivered"; db.add(pt)
        db.add(Notice(title="طلب كارت هاتف", body="تم التنفيذ", for_owner=False, uid=pt.uid))
        db.commit(); return {"ok": True}

    # Pubg
    pb = db.get(PubgOrder, order_id)
    if pb and pb.status == "pending":
        pb.status = "delivered"; db.add(pb)
        db.add(Notice(title="تم تنفيذ شدات ببجي", body=f"حزمة {pb.pkg}", for_owner=False, uid=pb.uid))
        db.commit(); return {"ok": True}

    # Ludo
    ld = db.get(LudoOrder, order_id)
    if ld and ld.status == "pending":
        ld.status = "delivered"; db.add(ld)
        db.add(Notice(title="تم تنفيذ طلب لودو", body=f"{ld.kind} {ld.pack}", for_owner=False, uid=ld.uid))
        db.commit(); return {"ok": True}

    raise HTTPException(404, "order not found or not pending")

@r.post("/orders/reject", dependencies=[Depends(guard)])
def orders_reject(payload: dict = Body(...), db: Session = Depends(get_db)):
    order_id = int(payload.get("order_id") or 0)
    if not order_id:
        raise HTTPException(400, "order_id required")

    so = db.get(ServiceOrder, order_id)
    if so and so.status == "pending":
        so.status = "rejected"
        u = db.query(User).filter_by(uid=so.uid).first()
        if u:
            u.balance = round((u.balance or 0.0) + float(so.price or 0.0), 2)
            db.add(u)
        db.add(so)
        db.add(Notice(title="تم رفض الطلب", body="تم ردّ الرصيد", for_owner=False, uid=so.uid))
        db.commit(); return {"ok": True}

    wc = db.get(WalletCard, order_id)
    if wc and wc.status == "pending":
        wc.status = "rejected"; db.add(wc)
        db.add(Notice(title="رفض كارت أسيا سيل", body="يرجى التأكد من الرقم", for_owner=False, uid=wc.uid))
        db.commit(); return {"ok": True}

    it = db.get(ItunesOrder, order_id)
    if it and it.status == "pending":
        it.status = "rejected"; db.add(it); db.commit(); return {"ok": True}

    pt = db.get(PhoneTopup, order_id)
    if pt and pt.status == "pending":
        pt.status = "rejected"; db.add(pt); db.commit(); return {"ok": True}

    pb = db.get(PubgOrder, order_id)
    if pb and pb.status == "pending":
        pb.status = "rejected"; db.add(pb); db.commit(); return {"ok": True}

    ld = db.get(LudoOrder, order_id)
    if ld and ld.status == "pending":
        ld.status = "rejected"; db.add(ld); db.commit(); return {"ok": True}

    raise HTTPException(404, "order not found or not pending")

@r.post("/orders/refund", dependencies=[Depends(guard)])
def orders_refund(payload: dict = Body(...), db: Session = Depends(get_db)):
    order_id = int(payload.get("order_id") or 0)
    if not order_id:
        raise HTTPException(400, "order_id required")

    so = db.get(ServiceOrder, order_id)
    if so and so.status in ("pending", "processing"):
        so.status = "rejected"
        u = db.query(User).filter_by(uid=so.uid).first()
        if u:
            u.balance = round((u.balance or 0.0) + float(so.price or 0.0), 2)
            db.add(u)
        db.add(so)
        db.add(Notice(title="ردّ رصيد", body=f"+${so.price}", for_owner=False, uid=so.uid))
        db.commit(); return {"ok": True}

    raise HTTPException(404, "order not refundable")

# ---------- إحصاءات ----------
@r.get("/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    data = provider_balance()
    if isinstance(data, dict):
        if "balance" in data: return {"ok": True, "balance": float(data["balance"])}
        if "data" in data and isinstance(data["data"], dict) and "balance" in data["data"]:
            return {"ok": True, "balance": float(data["data"]["balance"])}
    return {"ok": False, "balance": 0.0}

@r.get("/stats/users-count", dependencies=[Depends(guard)])
def users_count(db: Session = Depends(get_db)):
    total = db.query(func.count(User.id)).scalar() or 0
    since = datetime.utcnow() - timedelta(hours=1)
    active_uids = set()
    for model in (ServiceOrder, WalletCard, ItunesOrder, PhoneTopup, PubgOrder, LudoOrder):
        q = db.query(model.uid).filter(model.created_at >= since).all()
        active_uids.update([u for (u,) in q])
    return {"ok": True, "count": int(total), "active_last_hour": len(active_uids)}

@r.get("/stats/users-balances", dependencies=[Depends(guard)])
def users_balances(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.balance.desc()).limit(1000).all()
    total = sum([float(u.balance or 0.0) for u in users])
    return {
        "ok": True,
        "total": round(total, 2),
        "list": [{"uid": u.uid, "balance": round(float(u.balance or 0.0), 2), "is_banned": bool(u.is_banned)} for u in users]
    }

# app/routers/admin.py
import os
from fastapi import APIRouter, Depends, Header, HTTPException, Body, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)

# (اختياري) لو عندك عميل مزوّد
try:
    from ..providers.smm_client import provider_add_order, provider_balance
except Exception:
    provider_add_order = None
    provider_balance = None

r = APIRouter()

ADMIN_PASS = os.getenv("ADMIN_PASS", "2000")

# -------------- حراسة الدخول --------------
def guard(x_admin_pass: str | None):
    if not x_admin_pass or x_admin_pass.strip() != ADMIN_PASS:
        raise HTTPException(401, "UNAUTHORIZED")

# -------------- نماذج --------------
class OrderIdReq(BaseModel):
    order_id: int

class WalletReq(BaseModel):
    uid: str
    amount: float

# -------------- تحويل صفوف لقوائم يقرأها التطبيق --------------
def _row_service(o: ServiceOrder):
    return {
        "id": str(o.id),
        "uid": o.uid,
        "title": o.service_key,
        "quantity": int(o.quantity or 0),
        "price": float(o.price or 0),
        "link": o.link,
        "payload": o.link,  # التطبيق يقرأ payload
        "status": o.status or "pending",
        "created_at": int(o.created_at.timestamp() * 1000) if o.created_at else 0
    }

def _row_card(o: WalletCard):
    return {
        "id": str(o.id),
        "uid": o.uid,
        "title": "كارت أسيا سيل",
        "quantity": 1,
        "price": float(o.amount_usd or 0),
        "link": "",
        "payload": o.card_number,   # يظهر رقم الكارت
        "status": o.status or "pending",
        "created_at": int(o.created_at.timestamp() * 1000) if o.created_at else 0
    }

# -------------- قوائم المعلّق --------------
@r.get("/admin/pending/services")
def pending_services(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)
    lst = (
        db.query(ServiceOrder)
        .filter_by(status="pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    return [_row_service(o) for o in lst]

@r.get("/admin/pending/topups")
def pending_topups(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)
    lst = (
        db.query(WalletCard)
        .filter_by(status="pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    return [_row_card(o) for o in lst]

@r.get("/admin/pending/itunes")
def pending_itunes(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)
    # إن لم تكن تستخدم جدول iTunes يمكن تركها فارغة
    lst = (
        db.query(ItunesOrder)
        .filter_by(status="pending")
        .order_by(ItunesOrder.created_at.desc())
        .all()
    )
    # عرض بسيط:
    out = []
    for o in lst:
        out.append({
            "id": str(o.id), "uid": o.uid, "title": "آيتونز",
            "quantity": 1, "price": float(o.amount or 0),
            "link": "", "payload": o.gift_code or "",
            "status": o.status or "pending",
            "created_at": int(o.created_at.timestamp() * 1000) if o.created_at else 0
        })
    return out

@r.get("/admin/pending/pubg")
def pending_pubg(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)
    lst = (
        db.query(PubgOrder)
        .filter_by(status="pending")
        .order_by(PubgOrder.created_at.desc())
        .all()
    )
    out = []
    for o in lst:
        out.append({
            "id": str(o.id), "uid": o.uid, "title": f"PUBG {o.pkg}",
            "quantity": 1, "price": 0.0,
            "link": "", "payload": o.pubg_id,
            "status": o.status or "pending",
            "created_at": int(o.created_at.timestamp() * 1000) if o.created_at else 0
        })
    return out

@r.get("/admin/pending/ludo")
def pending_ludo(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)
    lst = (
        db.query(LudoOrder)
        .filter_by(status="pending")
        .order_by(LudoOrder.created_at.desc())
        .all()
    )
    out = []
    for o in lst:
        out.append({
            "id": str(o.id), "uid": o.uid, "title": f"Ludo {o.kind} {o.pack}",
            "quantity": 1, "price": 0.0,
            "link": "", "payload": o.ludo_id,
            "status": o.status or "pending",
            "created_at": int(o.created_at.timestamp() * 1000) if o.created_at else 0
        })
    return out

# -------------- إجراءات (تنفيذ/رفض/رد رصيد) --------------
@r.post("/admin/orders/approve")
def admin_approve(p: OrderIdReq, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)

    # 1) خدمات المزوّد
    o = db.get(ServiceOrder, p.order_id)
    if o and o.status == "pending":
        # حاول إرسال الطلب للمزوّد إن توفّر العميل
        if provider_add_order:
            try:
                res = provider_add_order(o.service_key, o.link, o.quantity)
                if res.get("ok"):
                    o.status = "processing"
                    o.provider_order_id = res.get("orderId")
                else:
                    raise Exception(res.get("error", "provider error"))
            except Exception:
                # لو فشل مزوّد، نبقيها processing على الأقل لكي لا تتعطل الأزرار
                o.status = "processing"
        else:
            o.status = "processing"

        db.add(o)
        db.add(Notice(
            title="تم تنفيذ طلبك",
            body=f"تم دفع طلبك للمزوّد. الخدمة: {o.service_key}",
            for_owner=False, uid=o.uid
        ))
        db.commit()
        return {"ok": True}

    # 2) كروت أسيا سيل: نجعلها accepted فقط (المبلغ أضفه من شاشة إضافة الرصيد)
    c = db.get(WalletCard, p.order_id)
    if c and c.status == "pending":
        c.status = "accepted"
        db.add(c)
        db.add(Notice(
            title="تم قبول الكارت",
            body="سيتم إضافة الرصيد إلى محفظتك بعد المعالجة.",
            for_owner=False, uid=c.uid
        ))
        db.commit()
        return {"ok": True}

    # 3) إن لم توجد
    raise HTTPException(404, "ORDER_NOT_FOUND_OR_STATE")

@r.post("/admin/orders/reject")
def admin_reject(p: OrderIdReq, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)

    o = db.get(ServiceOrder, p.order_id)
    if o and o.status == "pending":
        # ردّ الرصيد إلى المستخدم إن كان مخصومًا
        if o.price:
            u = db.query(User).filter_by(uid=o.uid).first()
            if u:
                u.balance = round(float(u.balance or 0) + float(o.price or 0), 2)
                db.add(u)
        o.status = "rejected"
        db.add(o)
        db.add(Notice(title="تم رفض الطلب", body="تم ردّ رصيدك.", for_owner=False, uid=o.uid))
        db.commit()
        return {"ok": True}

    c = db.get(WalletCard, p.order_id)
    if c and c.status == "pending":
        c.status = "rejected"
        db.add(c)
        db.add(Notice(title="رفض كارت أسيا سيل", body="يرجى التأكد من الرقم والمحاولة مجددًا.", for_owner=False, uid=c.uid))
        db.commit()
        return {"ok": True}

    raise HTTPException(404, "ORDER_NOT_FOUND_OR_STATE")

@r.post("/admin/orders/refund")
def admin_refund(p: OrderIdReq, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)

    o = db.get(ServiceOrder, p.order_id)
    if not o:
        raise HTTPException(404, "ORDER_NOT_FOUND")
    if o.price:
        u = db.query(User).filter_by(uid=o.uid).first()
        if u:
            u.balance = round(float(u.balance or 0) + float(o.price or 0), 2)
            db.add(u)
    o.status = "refunded"
    db.add(o)
    db.add(Notice(title="ردّ رصيد", body="تم ردّ المبلغ لطلبك.", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

# -------------- رصيد/خصم رصيد --------------
@r.post("/admin/wallet/topup")
def admin_topup(p: WalletReq, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)
    u = db.query(User).filter_by(uid=p.uid).first()
    if not u:
        u = User(uid=p.uid, balance=0.0)
        db.add(u)
        db.flush()
    u.balance = round(float(u.balance or 0) + float(p.amount), 2)
    db.add(u)
    db.add(Notice(title="إضافة رصيد", body=f"+${p.amount}", for_owner=False, uid=p.uid))
    db.commit()
    return {"ok": True, "balance": float(u.balance)}

@r.post("/admin/wallet/deduct")
def admin_deduct(p: WalletReq, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)
    u = db.query(User).filter_by(uid=p.uid).first()
    if not u:
        raise HTTPException(404, "USER_NOT_FOUND")
    newb = round(max(0.0, float(u.balance or 0) - float(p.amount)), 2)
    u.balance = newb
    db.add(u)
    db.add(Notice(title="خصم رصيد", body=f"-${p.amount}", for_owner=False, uid=p.uid))
    db.commit()
    return {"ok": True, "balance": float(u.balance)}

# -------------- إحصائيات --------------
@r.get("/admin/stats/users-count")
def users_count(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)
    total = db.query(func.count(User.id)).scalar() or 0
    return {"count": int(total)}

@r.get("/admin/stats/users-balances")
def users_balances(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    guard(x_admin_pass)
    users = db.query(User).order_by(User.balance.desc()).all()
    total = sum(float(u.balance or 0) for u in users)
    return {
        "total": float(total),
        "list": [{"uid": u.uid, "balance": float(u.balance or 0), "is_banned": bool(u.is_banned)} for u in users]
    }

# -------------- رصيد المزوّد --------------
@r.get("/admin/provider/balance")
def provider_bal(x_admin_pass: str | None = Header(default=None)):
    guard(x_admin_pass)
    if provider_balance:
        try:
            res = provider_balance()
            # توقع {"balance": ...} أو {"ok": True, "balance": ...}
            if isinstance(res, dict):
                if "balance" in res:
                    return {"balance": float(res["balance"])}
                if res.get("ok") and "balance" in res:
                    return {"balance": float(res["balance"])}
        except Exception:
            pass
    return {"balance": 0.0}

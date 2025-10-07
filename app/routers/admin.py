# app/routers/admin.py
import os
from uuid import UUID
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import User, Order

r = APIRouter(tags=["admin"])

# كلمة مرور المالك (يجب أن تساوي ما تدخّله داخل التطبيق: افتراضياً 2000)
ADMIN_PASS = os.getenv("ADMIN_PASS", "2000")

# ----------------- أدوات جلسة DB -----------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_admin(x_admin_pass: str | None):
    if not x_admin_pass or x_admin_pass.strip() != ADMIN_PASS:
        raise HTTPException(401, "UNAUTHORIZED")

def _404_if(obj, msg="NOT_FOUND"):
    if not obj:
        raise HTTPException(404, msg)

def _400(msg="BAD_REQUEST"):
    raise HTTPException(400, msg)

# ----------------- نماذج الطلبات -----------------
class OrderIdReq(BaseModel):
    order_id: str

class WalletReq(BaseModel):
    uid: str
    amount: float

class GiftIn(BaseModel):
    gift_code: str

class AmountIn(BaseModel):
    amount_usd: float

# ----------------- مُخرجات موحَّدة -----------------
def _pending_rows(db: Session, typ: str):
    """يُرجع مصفوفة JSON (وليس كائن) كما يتوقع التطبيق."""
    rows = (
        db.execute(
            select(Order)
            .where(Order.type == typ, Order.status == "Pending")
            .order_by(Order.created_at.desc())
        )
        .scalars()
        .all()
    )
    out = []
    for o in rows:
        out.append({
            "id": str(o.id),
            "uid": o.uid,
            "title": o.title,
            "quantity": o.quantity,
            "price": float(o.price or 0),
            "link": o.link,
            "payload": o.payload,                    # حقل موحَّد يقرأه التطبيق
            "status": o.status,
            "created_at": int(o.created_at.timestamp() * 1000),
        })
    return out

# ----------------- قوائم المعلّق (مطابقة للتطبيق) -----------------
@r.get("/admin/pending/services")
def admin_pending_services(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    return _pending_rows(db, "provider")

@r.get("/admin/pending/topups")  # اسم المسار الذي يستخدمه التطبيق للكروت
def admin_pending_topups_alias(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    return _pending_rows(db, "card")

@r.get("/admin/pending/cards")   # احتفظنا بالمسار القديم أيضًا
def admin_pending_cards(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    return _pending_rows(db, "card")

@r.get("/admin/pending/itunes")
def admin_pending_itunes(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    return _pending_rows(db, "itunes")

@r.get("/admin/pending/pubg")
def admin_pending_pubg(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    return _pending_rows(db, "pubg")

@r.get("/admin/pending/ludo")
def admin_pending_ludo(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    return _pending_rows(db, "ludo")

# ----------------- إجراءات عامة للطلبات (مطابقة للتطبيق) -----------------
@r.post("/admin/orders/approve")
def admin_orders_approve(p: OrderIdReq, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    """يستدعيه التطبيق عند الضغط على (تنفيذ)"""
    check_admin(x_admin_pass)
    oid = UUID(p.order_id)
    o = db.get(Order, oid)
    _404_if(o, "ORDER_NOT_FOUND")
    if o.status != "Pending":
        _400("INVALID_STATE")

    # من الممكن لاحقاً تنفيذ استدعاء مزوّد فعلي هنا إذا كان o.type == "provider"
    o.status = "Done"
    db.commit()
    return {"ok": True}

@r.post("/admin/orders/reject")
def admin_orders_reject(p: OrderIdReq, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    """يستدعيه التطبيق عند الضغط على (رفض)"""
    check_admin(x_admin_pass)
    oid = UUID(p.order_id)
    o = db.get(Order, oid)
    _404_if(o, "ORDER_NOT_FOUND")
    if o.status != "Pending":
        _400("INVALID_STATE")

    # إذا كان طلب موفّر وقد تم خصم السعر من المستخدم سابقاً، نرجّع المبلغ
    if o.type == "provider" and o.price:
        u = db.get(User, o.uid)
        if u:
            u.balance = float(u.balance or 0) + float(o.price or 0)

    o.status = "Rejected"
    db.commit()
    return {"ok": True}

@r.post("/admin/orders/refund")
def admin_orders_refund(p: OrderIdReq, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    """يستدعيه التطبيق عند الضغط على (رد رصيد)"""
    check_admin(x_admin_pass)
    oid = UUID(p.order_id)
    o = db.get(Order, oid)
    _404_if(o, "ORDER_NOT_FOUND")

    # رد المبلغ إن لم يكن قد رُدّ
    if o.price and o.status != "Refunded":
        u = db.get(User, o.uid)
        if u:
            u.balance = float(u.balance or 0) + float(o.price or 0)

    o.status = "Refunded"
    db.commit()
    return {"ok": True}

# ----------------- عمليات المحفظة (مطابقة للتطبيق) -----------------
@r.post("/admin/wallet/topup")
def admin_wallet_topup(p: WalletReq, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    """التطبيق يرسل {uid, amount} هنا"""
    check_admin(x_admin_pass)
    u = db.get(User, p.uid)
    if not u:
        u = User(uid=p.uid, balance=0)
        db.add(u)
        db.flush()
    u.balance = float(u.balance or 0) + float(p.amount)
    db.commit()
    return {"ok": True, "balance": float(u.balance)}

@r.post("/admin/wallet/deduct")
def admin_wallet_deduct(p: WalletReq, x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    """التطبيق يرسل {uid, amount} هنا"""
    check_admin(x_admin_pass)
    u = db.get(User, p.uid)
    _404_if(u, "USER_NOT_FOUND")
    bal = float(u.balance or 0)
    if bal < p.amount:
        _400("INSUFFICIENT_BALANCE")
    u.balance = bal - float(p.amount)
    db.commit()
    return {"ok": True, "balance": float(u.balance)}

# ----------------- إحصائيات (مطابقة للتطبيق) -----------------
@r.get("/admin/stats/users-count")
def admin_stats_users_count(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    total = db.execute(select(func.count(User.uid))).scalar() or 0
    active = db.execute(
        select(func.count(User.uid)).where(User.last_seen >= datetime.now(timezone.utc) - timedelta(hours=1))
    ).scalar() or 0
    return {"count": int(total), "active_hour": int(active)}

@r.get("/admin/stats/users-balances")
def admin_stats_users_balances(x_admin_pass: str | None = Header(default=None), db: Session = Depends(get_db)):
    check_admin(x_admin_pass)
    rows = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    total = sum(float(r.balance or 0) for r in rows)
    return {
        "total": float(total),
        "list": [{"uid": r.uid, "balance": float(r.balance or 0), "is_banned": bool(r.is_banned)} for r in rows]
    }

# ----------------- مزوّد (اختياري) -----------------
@r.get("/admin/provider/balance")
def admin_provider_balance(x_admin_pass: str | None = Header(default=None)):
    check_admin(x_admin_pass)
    # Stub — اربطه لاحقًا بمزوّدك الحقيقي
    return {"balance": 0.0}

# ----------------- تسجيل المالك (اختياري) -----------------
class LoginIn(BaseModel):
    password: str

@r.post("/admin/login")
def admin_login(p: LoginIn):
    if p.password.strip() == ADMIN_PASS:
        return {"token": p.password.strip()}
    raise HTTPException(401, "INVALID_CREDENTIALS")

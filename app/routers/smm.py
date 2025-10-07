# app/routers/smm.py
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..database import get_db
from ..models import User, ServiceOrder, WalletCard, Notice

r = APIRouter()

def _now() -> datetime:
    return datetime.utcnow()

def _row_order(o: ServiceOrder) -> Dict[str, Any]:
    return {
        "id": o.id,
        "title": getattr(o, "service_key", None) or getattr(o, "title", None) or "طلب",
        "quantity": getattr(o, "quantity", 0) or 0,
        "price": float(getattr(o, "price", 0.0) or 0.0),
        "payload": getattr(o, "link", None) or getattr(o, "payload", None),
        "status": o.status,
        "created_at": int(o.created_at.timestamp() * 1000) if getattr(o, "created_at", None) else 0,
    }

# ---- صحة بسيطة
@r.get("/health")
def public_health(db: Session = Depends(get_db)):
    try:
        db.execute("SELECT 1")
        return {"ok": True, "db": True}
    except Exception:
        return {"ok": True, "db": False}

# ---- إنشاء/تحديث مستخدم (UID)
@r.post("/users/upsert")
def users_upsert(payload: Dict[str, str] = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    if not uid:
        raise HTTPException(400, "uid required")
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0, is_banned=False)
        db.add(u)
        db.add(Notice(title="مرحبًا", body="تم إنشاء حسابك.", for_owner=False, uid=uid))
    db.commit()
    return {"ok": True}

# ---- رصيد المحفظة
@r.get("/wallet/balance")
def wallet_balance(uid: str = Query(...), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    return {"ok": True, "balance": float(u.balance) if u else 0.0}

# ---- إنشاء طلب مربوط بالمزوّد (يقتطع السعر مباشرة)
@r.post("/orders/create/provider")
def create_provider_order(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    link = (payload.get("link") or "").strip()
    quantity = int(payload.get("quantity") or 0)
    price = float(payload.get("price") or 0.0)
    service_name = (payload.get("service_name") or payload.get("service_id") or "service")

    if not uid or not link or quantity <= 0 or price <= 0:
        raise HTTPException(400, "invalid payload")

    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0, is_banned=False)
        db.add(u)
        db.flush()

    if u.is_banned:
        raise HTTPException(403, "banned")

    if u.balance < price:
        raise HTTPException(400, "insufficient balance")

    # اخصم المبلغ وأنشئ الطلب بحالة pending (سيُنفذ من لوحة المالك)
    u.balance = round(float(u.balance) - price, 2)
    order = ServiceOrder(
        uid=uid,
        service_key=str(service_name),
        link=link,
        quantity=quantity,
        price=price,
        status="pending",
        created_at=_now(),
    )
    db.add(order)

    # إشعارات
    db.add(Notice(title="تم استلام طلبك", body=f"{service_name} | الكمية {quantity}", for_owner=False, uid=uid))
    db.add(Notice(title="طلب خدمات معلّق", body=f"UID={uid} | {service_name} | qty={quantity}", for_owner=True, uid=uid))

    db.commit()
    return {"ok": True, "order": _row_order(order)}

# ---- إنشاء طلب يدوي (يعرض ضمن المعلّقات للمالك)
@r.post("/orders/create/manual")
def create_manual_order(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    title = (payload.get("title") or "طلب يدوي").strip()
    if not uid:
        raise HTTPException(400, "uid required")

    # نسجل كطلب خدمة Pending بدون خصم رصيد
    order = ServiceOrder(
        uid=uid,
        service_key=title,
        link="manual",
        quantity=0,
        price=0.0,
        status="pending",
        created_at=_now(),
    )
    db.add(order)

    db.add(Notice(title="طلبك قيد المراجعة", body=title, for_owner=False, uid=uid))
    db.add(Notice(title="طلب يدوي جديد", body=f"{title} | UID={uid}", for_owner=True, uid=uid))
    db.commit()
    return {"ok": True, "order": _row_order(order)}

# ---- إرسال كارت أسيا سيل (يظهر في الكارتات المعلقة)
@r.post("/wallet/asiacell/submit")
def asiacell_submit(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    card = (payload.get("card") or "").strip()

    if not uid or not (len(card) in (14, 16) and card.isdigit()):
        raise HTTPException(400, "invalid card")

    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0, is_banned=False)
        db.add(u)
        db.flush()

    # نخزن طلب الكارت كـ WalletCard بحالة pending
    wc = WalletCard(
        uid=uid,
        status="pending",
        created_at=_now()
    )
    # إن كان جدولك يحوي عمودًا لرقم الكارت (number أو code) سنحاول تعبئته بأمان
    try:
        setattr(wc, "number", card)
    except Exception:
        try:
            setattr(wc, "code", card)
        except Exception:
            pass

    db.add(wc)

    db.add(Notice(title="تم استلام كارتك", body=f"أسيا سيل: {card}", for_owner=False, uid=uid))
    db.add(Notice(title="كارت أسيا سيل جديد", body=f"UID={uid} | {card}", for_owner=True, uid=uid))
    db.commit()
    return {"ok": True, "card_id": getattr(wc, "id", None)}

# ---- طلباتي
@r.get("/orders/my")
def orders_my(uid: str = Query(...), db: Session = Depends(get_db)):
    lst: List[ServiceOrder] = (
        db.query(ServiceOrder)
        .filter_by(uid=uid)
        .order_by(ServiceOrder.created_at.desc())
        .limit(200)
        .all()
    )
    return [_row_order(o) for o in lst]

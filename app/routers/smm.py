# app/routers/smm.py
from fastapi import APIRouter, HTTPException, Body, Query, Depends
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List, Dict, Any

from ..database import get_db
from ..models import User, ServiceOrder, WalletCard, Notice
from ..providers.smm_client import provider_add_order  # موجود مسبقًا في مشروعك

r = APIRouter()

# ---------------------------
# Helpers
# ---------------------------
def now_ms() -> int:
    return int(datetime.utcnow().timestamp() * 1000)

def _status_str(s: str) -> str:
    s = (s or "").lower()
    if s in ("pending", ""):
        return "Pending"
    if s in ("processing", "inprogress", "in_progress"):
        return "Processing"
    if s in ("done", "completed", "success"):
        return "Done"
    if s in ("rejected", "cancelled", "canceled", "failed"):
        return "Rejected"
    if s in ("refunded",):
        return "Refunded"
    return "Pending"

def _safe_json(o: Any) -> Any:
    # تحويل datetime -> iso
    if isinstance(o, datetime):
        return o.isoformat()
    return o

def _order_to_dict(o: ServiceOrder) -> Dict[str, Any]:
    return {
        "id": getattr(o, "id"),
        "title": getattr(o, "title"),
        "quantity": getattr(o, "quantity") or 0,
        "price": float(getattr(o, "price") or 0.0),
        "payload": getattr(o, "payload") or "",
        "status": _status_str(getattr(o, "status")),
        "created_at": int((getattr(o, "created_at") or datetime.utcnow()).timestamp() * 1000),
    }

# ---------------------------
# Schemas (requests)
# ---------------------------
class UpsertUserReq(BaseModel):
    uid: str = Field(..., min_length=2, max_length=40)

class ProviderOrderReq(BaseModel):
    uid: str
    service_id: int
    service_name: str
    link: str
    quantity: int = Field(..., ge=1)
    price: float = Field(..., ge=0)

class ManualOrderReq(BaseModel):
    uid: str
    title: str

class AsiacellCardReq(BaseModel):
    uid: str
    card: str

    @validator("card")
    def digits14_16(cls, v: str) -> str:
        d = "".join(ch for ch in v if ch.isdigit())
        if len(d) not in (14, 16):
            raise ValueError("card must be 14 or 16 digits")
        return d

# ---------------------------
# Public API
# ---------------------------

@r.post("/users/upsert")
def users_upsert(body: UpsertUserReq, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=body.uid).first()
    if not u:
        u = User(uid=body.uid, balance=0.0, is_banned=False)
        db.add(u)
        # إشعار ترحيبي للمستخدم
        db.add(Notice(title="تم إنشاء حسابك", body="مرحبًا بك 👋", for_owner=False, uid=body.uid))
    db.commit()
    return {"ok": True, "uid": body.uid}

@r.get("/wallet/balance")
def wallet_balance(uid: str = Query(...), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    return {"ok": True, "balance": float(u.balance) if u else 0.0}

@r.post("/orders/create/provider")
def orders_create_provider(body: ProviderOrderReq, db: Session = Depends(get_db)):
    # جلب/إنشاء المستخدم
    u = db.query(User).filter_by(uid=body.uid).first()
    if not u:
        u = User(uid=body.uid, balance=0.0, is_banned=False)
        db.add(u)
        db.flush()

    # التحقق من الرصيد
    if (u.balance or 0.0) < body.price:
        raise HTTPException(400, detail="insufficient balance")

    # إنشاء سجل الطلب مبدئيًا
    payload_obj = {
        "service_id": body.service_id,
        "link": body.link,
        "quantity": body.quantity,
    }
    ord_db = ServiceOrder(
        uid=body.uid,
        title=body.service_name,
        quantity=body.quantity,
        price=float(body.price),
        payload=str(payload_obj),
        status="Processing",  # سيصبح Done لاحقًا بعد التتبع
        created_at=datetime.utcnow(),
    )
    # خصم الرصيد
    u.balance = round(float(u.balance or 0.0) - float(body.price), 2)
    db.add(ord_db)
    db.add(u)
    # إشعار للمستخدم + للمالك
    db.add(Notice(title="تم استلام طلبك", body=f"{body.service_name}", for_owner=False, uid=body.uid))
    db.add(Notice(title="طلب خدمات معلّق", body=f"UID={body.uid} | {body.service_name}", for_owner=True))
    db.commit()

    # محاولة إرسال الطلب للمزوّد
    ext_order_id = None
    try:
        res = provider_add_order(service_id=body.service_id, link=body.link, quantity=body.quantity)
        # نتقبّل أكثر من شكل للنتيجة
        ext_order_id = str(res.get("order") or res.get("order_id") or res.get("id") or "")
    except Exception:
        ext_order_id = None

    # تحديث الطلب إذا توفر رقم خارجي
    if ext_order_id:
        setattr(ord_db, "ext_order_id", ext_order_id)
        db.add(ord_db)
        db.commit()
    else:
        # لو فشل الإرسال للمزوّد: نعيد الرصيد ونرفض الطلب
        u = db.query(User).filter_by(uid=body.uid).first()
        u.balance = round(float(u.balance or 0.0) + float(body.price), 2)
        ord_db.status = "Rejected"
        db.add(u); db.add(ord_db)
        db.add(Notice(title="فشل إنشاء الطلب", body=body.service_name, for_owner=False, uid=body.uid))
        db.commit()
        raise HTTPException(502, detail="provider error")

    return {"ok": True, "order_id": ord_db.id, "ext_order_id": ext_order_id}

@r.post("/orders/create/manual")
def orders_create_manual(body: ManualOrderReq, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=body.uid).first()
    if not u:
        u = User(uid=body.uid, balance=0.0, is_banned=False)
        db.add(u); db.flush()

    ord_db = ServiceOrder(
        uid=body.uid,
        title=body.title,
        quantity=0,
        price=0.0,
        payload="{}",
        status="Pending",
        created_at=datetime.utcnow(),
    )
    db.add(ord_db)
    db.add(Notice(title="طلب معلّق", body=body.title, for_owner=False, uid=body.uid))
    db.add(Notice(title="طلب يدوي جديد", body=f"UID={body.uid} | {body.title}", for_owner=True))
    db.commit()
    return {"ok": True, "order_id": ord_db.id}

@r.get("/orders/my")
def orders_my(uid: str = Query(...), db: Session = Depends(get_db)):
    lst: List[ServiceOrder] = (
        db.query(ServiceOrder)
        .filter_by(uid=uid)
        .order_by(ServiceOrder.created_at.desc())
        .limit(100)
        .all()
    )
    return [_order_to_dict(x) for x in lst]

@r.post("/wallet/asiacell/submit")
def wallet_asiacell_submit(body: AsiacellCardReq, db: Session = Depends(get_db)):
    # تأكد من وجود المستخدم
    u = db.query(User).filter_by(uid=body.uid).first()
    if not u:
        u = User(uid=body.uid, balance=0.0, is_banned=False)
        db.add(u); db.flush()

    # إنشاء بطاقة معلّقة للمراجعة
    wc = WalletCard(
        uid=body.uid,
        card=body.card,          # اسم العمود في مخططك: card (إن كان card_number غيّر هنا)
        status="pending",
        created_at=datetime.utcnow(),
    )
    db.add(wc)
    db.add(Notice(title="تم استلام كارتك", body="قيد المراجعة", for_owner=False, uid=body.uid))
    db.add(Notice(title="كارت أسيا سيل جديد", body=f"UID={body.uid} | CARD={body.card}", for_owner=True))
    db.commit()
    return {"ok": True, "card_id": wc.id}

# app/routers/smm.py
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Form
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
import re

from ..database import get_db
from ..models import (
    User, Notice, Token,
    WalletCard,
    ServiceOrder, ItunesOrder, PhoneTopup, PubgOrder, LudoOrder
)

r = APIRouter()  # سيتم تضمين هذا الراوتر تحت /api من main.py

# -------- Helpers --------
def _row(obj):
    if obj is None:
        return None
    out: Dict[str, Any] = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    return out

def _rows(lst):
    return [_row(o) for o in lst]

# -------- Health --------
@r.get("/health")
def health():
    return {"ok": True}

# -------- Users: إنشاء/تحديث UID وحفظه --------
@r.post("/users/upsert")
def users_upsert(uid: str = Query(...), db: Session = Depends(get_db)):
    """
    ينشئ المستخدم إذا لم يكن موجودًا، ولا يغيّر الرصيد لو موجود.
    """
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.flush()
        db.add(Notice(title="مرحبًا!", body="تم إنشاء حسابك", uid=uid, for_owner=False))
    db.commit()
    return {"ok": True, "user": {"uid": u.uid, "balance": u.balance, "is_banned": u.is_banned}}

# -------- Users: الرصيد --------
@r.get("/users/{uid}/balance")
def user_balance(uid: str, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.commit()
    return {"ok": True, "uid": uid, "balance": u.balance}

# -------- تسجيل توكن الإشعارات --------
@r.post("/notify/token")
def register_token(
    token: str = Query(...),
    uid: Optional[str] = Query(default=None),
    for_owner: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    # unique by token
    exists = db.query(Token).filter_by(token=token).first()
    if exists:
        exists.uid = uid
        exists.for_owner = for_owner
        db.add(exists)
    else:
        db.add(Token(token=token, uid=uid, for_owner=for_owner))
    db.commit()
    return {"ok": True}

# -------- إشعارات المستخدم --------
@r.get("/notices")
def list_notices(
    uid: Optional[str] = Query(default=None),
    for_owner: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Notice).filter_by(for_owner=for_owner)
    if not for_owner:
        if not uid:
            raise HTTPException(400, "uid required")
        q = q.filter(Notice.uid == uid)
    lst = q.order_by(Notice.created_at.desc()).limit(limit).all()
    return {"ok": True, "list": _rows(lst)}

# =========================
#  كارت أسيا سيل (من المستخدم)
# =========================
@r.post("/cards/asiacell/submit")
def submit_asiacell_card(
    # ندعم Query + JSON + Form حتى لا يفشل التطبيق مهما كان تنسيقه
    uid: Optional[str] = Query(default=None),
    card_number: Optional[str] = Query(default=None),
    uid_body: Optional[str] = Body(default=None, embed=True),
    card_number_body: Optional[str] = Body(default=None, embed=True),
    uid_form: Optional[str] = Form(default=None),
    card_number_form: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    # اجمع القيم من أي مصدر متاح
    uid = (uid or uid_body or uid_form or "").strip()
    card_number = (card_number or card_number_body or card_number_form or "").strip()

    if not uid:
        raise HTTPException(400, "uid required")

    # تنظيف الرقم (أرقام فقط)
    digits = re.sub(r"\D+", "", card_number)
    if digits == "":
        raise HTTPException(400, "card_number required")
    if len(digits) not in (14, 16):
        raise HTTPException(400, "card_number must be 14 or 16 digits")

    # تأكد من وجود المستخدم
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.flush()

    # خزّن الطلب
    wc = WalletCard(uid=uid, card_number=digits, status="pending")
    db.add(wc)
    db.flush()

    # إشعار للمالك + للمستخدم
    masked = digits[:2] + "*" * (len(digits) - 4) + digits[-2:]
    db.add(Notice(
        title="طلب شحن أسيا سيل",
        body=f"UID={uid} | Card={masked} (معلّق)",
        for_owner=True,
        uid=None
    ))
    db.add(Notice(
        title="استلام طلبك",
        body="تم استلام رقم الكارت وسيتم المراجعة قريبًا.",
        for_owner=False,
        uid=uid
    ))

    db.commit()
    return {"ok": True, "card_id": wc.id, "masked": masked, "status": wc.status}

# =========================
#  طلبات الخدمات (من المستخدم)
# =========================
@r.post("/orders/service/create")
def create_service_order(
    uid: Optional[str] = Query(default=None),
    service_key: Optional[str] = Query(default=None),     # مثلاً: tiktok_followers
    service_code: Optional[int] = Query(default=None),    # رقم الخدمة عند المزود
    link: Optional[str] = Query(default=None),
    quantity: Optional[int] = Query(default=None, ge=1),
    unit_price_per_k: Optional[float] = Query(default=None),  # سعر لكل 1000
    # دعم JSON body أيضًا
    payload: Optional[dict] = Body(default=None),
    db: Session = Depends(get_db),
):
    # جلب من JSON إذا مرسل
    if payload:
        uid = payload.get("uid", uid)
        service_key = payload.get("service_key", service_key)
        service_code = payload.get("service_code", service_code)
        link = payload.get("link", link)
        quantity = payload.get("quantity", quantity)
        unit_price_per_k = payload.get("unit_price_per_k", unit_price_per_k)

    # متطلبات
    if not all([uid, service_key, service_code, link, quantity, unit_price_per_k]):
        raise HTTPException(400, "missing fields")

    # المستخدم
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0)
        db.add(u)
        db.flush()

    # السعر النهائي
    try:
        price = round(float(unit_price_per_k) * (int(quantity) / 1000.0), 4)
    except Exception:
        raise HTTPException(400, "invalid quantity or unit_price_per_k")

    # تحقق الرصيد
    if (u.balance or 0.0) < price:
        raise HTTPException(402, "insufficient_balance")

    # خصم الرصيد
    u.balance = round((u.balance or 0.0) - price, 4)
    db.add(u)

    # إنشاء الطلب بالحالة pending
    so = ServiceOrder(
        uid=uid,
        service_key=str(service_key),
        service_code=int(service_code),
        link=str(link),
        quantity=int(quantity),
        unit_price_per_k=float(unit_price_per_k),
        price=float(price),
        status="pending"
    )
    db.add(so)
    db.flush()

    # إشعارات
    db.add(Notice(
        title="طلب خدمة جديد",
        body=f"UID={uid} | {service_key} | qty={quantity} | ${price}",
        for_owner=True,
        uid=None
    ))
    db.add(Notice(
        title="تم إنشاء الطلب",
        body=f"رقم الطلب #{so.id} | سيتم التنفيذ قريبًا",
        for_owner=False,
        uid=uid
    ))

    db.commit()
    return {"ok": True, "order": _row(so), "balance": u.balance}

# -------- عرض طلبات المستخدم (مختصرة) --------
@r.get("/users/{uid}/orders")
def list_user_orders(uid: str, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    out: List[Dict[str, Any]] = []

    so = (
        db.query(ServiceOrder)
        .filter_by(uid=uid)
        .order_by(ServiceOrder.created_at.desc())
        .limit(limit)
        .all()
    )
    for o in so:
        d = _row(o); d["type"] = "service"; out.append(d)

    io = (
        db.query(ItunesOrder)
        .filter_by(uid=uid)
        .order_by(ItunesOrder.created_at.desc())
        .limit(limit)
        .all()
    )
    for o in io:
        d = _row(o); d["type"] = "itunes"; out.append(d)

    pt = (
        db.query(PhoneTopup)
        .filter_by(uid=uid)
        .order_by(PhoneTopup.created_at.desc())
        .limit(limit)
        .all()
    )
    for o in pt:
        d = _row(o); d["type"] = "phone"; out.append(d)

    pb = (
        db.query(PubgOrder)
        .filter_by(uid=uid)
        .order_by(PubgOrder.created_at.desc())
        .limit(limit)
        .all()
    )
    for o in pb:
        d = _row(o); d["type"] = "pubg"; out.append(d)

    lu = (
        db.query(LudoOrder)
        .filter_by(uid=uid)
        .order_by(LudoOrder.created_at.desc())
        .limit(limit)
        .all()
    )
    for o in lu:
        d = _row(o); d["type"] = "ludo"; out.append(d)

    # أحدث أولاً
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"ok": True, "list": out[:limit]}

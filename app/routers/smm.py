from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from uuid import uuid4

from app.database import get_db
from app.models import User, Wallet, WalletLedger, Order, AsiacellCard, Notification, DeviceToken
from app.provider_map import SERVICE_CATALOG, SERVICE_CATEGORIES, calc_price

router = APIRouter()

class UpsertUser(BaseModel):
    uid: str

class BalanceQuery(BaseModel):
    uid: str

class ProviderOrderIn(BaseModel):
    uid: str
    service_id: int
    quantity: int
    link: str

class ManualOrderIn(BaseModel):
    uid: str
    title: str
    quantity: int | None = None
    price: float
    payload: dict | None = None

class AsiacellIn(BaseModel):
    uid: str
    card_number: str = Field(min_length=14, max_length=32)

class DeviceIn(BaseModel):
    uid: str | None = None
    token: str
    is_owner: bool = False

def ensure_user(db: Session, uid: str) -> User:
    user = db.query(User).filter(User.uid == uid).first()
    if not user:
        user = User(uid=uid)
        db.add(user)
        db.flush()
        db.add(Wallet(user_id=user.id, balance=0))
        db.flush()
    return user

@router.get("/health")
async def health():
    return {"ok": True}

@router.post("/users/upsert")
def upsert_user(payload: UpsertUser, db: Session = Depends(get_db)):
    ensure_user(db, payload.uid)
    db.commit()
    return {"ok": True}

@router.get("/wallet/balance")
def wallet_balance(uid: str, db: Session = Depends(get_db)):
    user = ensure_user(db, uid)
    bal = db.query(Wallet).filter(Wallet.user_id == user.id).first().balance
    db.commit()
    return {"ok": True, "balance": float(bal or 0)}

@router.post("/orders/create/provider")
def create_provider(payload: ProviderOrderIn, db: Session = Depends(get_db)):
    user = ensure_user(db, payload.uid)
    # حساب السعر
    try:
        price = calc_price(payload.service_id, payload.quantity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    if float(wallet.balance) < price:
        raise HTTPException(status_code=400, detail="INSUFFICIENT_BALANCE")

    order_id = f"ord_{uuid4()}"
    title = SERVICE_CATALOG[payload.service_id]["name"]
    db.add(Order(
        id=order_id,
        user_id=user.id,
        type="provider",
        service_id=payload.service_id,
        title=title,
        quantity=payload.quantity,
        price=price,
        payload={"link": payload.link},
        status="PENDING",
    ))
    wallet.balance = float(wallet.balance) - price
    db.add(WalletLedger(user_id=user.id, delta=-price, reason="provider_order", ref=order_id))

    # إشعارات
    db.add(Notification(user_id=user.id, title="طلب جديد (خدمة مزود)", body=f"تم استلام طلبك ({title}).", is_for_owner=False))
    db.add(Notification(user_id=None, title="طلب خدمات معلّق", body=f"UID={payload.uid} | {title} | qty={payload.quantity}", is_for_owner=True))

    db.commit()
    return {"ok": True, "order_id": order_id, "status": "PENDING", "price": price}

@router.post("/orders/create/manual")
def create_manual(payload: ManualOrderIn, db: Session = Depends(get_db)):
    user = ensure_user(db, payload.uid)
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    price = float(payload.price)
    if float(wallet.balance) < price:
        raise HTTPException(status_code=400, detail="INSUFFICIENT_BALANCE")

    order_id = f"ord_{uuid4()}"
    db.add(Order(
        id=order_id,
        user_id=user.id,
        type="manual",
        service_id=None,
        title=payload.title,
        quantity=payload.quantity,
        price=price,
        payload=payload.payload or {},
        status="REVIEW",
    ))
    wallet.balance = float(wallet.balance) - price
    db.add(WalletLedger(user_id=user.id, delta=-price, reason="manual_order", ref=order_id))

    db.add(Notification(user_id=user.id, title="طلبك قيد المراجعة", body=f"تم استلام طلب ({payload.title}).", is_for_owner=False))
    db.add(Notification(user_id=None, title="طلب يدوي جديد", body=f"UID={payload.uid} | {payload.title} | qty={payload.quantity} | price={price}", is_for_owner=True))

    db.commit()
    return {"ok": True, "order_id": order_id, "status": "REVIEW"}

@router.post("/wallet/asiacell/submit")
def submit_asiacell(payload: AsiacellIn, db: Session = Depends(get_db)):
    user = ensure_user(db, payload.uid)
    ticket_id = f"card_{uuid4()}"
    db.add(AsiacellCard(id=ticket_id, user_id=user.id, card_number=payload.card_number, status="REVIEW"))
    db.add(Notification(user_id=user.id, title="تم استلام كارتك", body="أُرسل الكارت للمراجعة وسيتم الرد قريبًا.", is_for_owner=False))
    db.add(Notification(user_id=None, title="كارت أسيا سيل جديد", body=f"UID={payload.uid} | card={payload.card_number}", is_for_owner=True))
    db.commit()
    return {"ok": True, "ticket_id": ticket_id, "status": "REVIEW"}

@router.get("/orders/my")
def my_orders(uid: str, db: Session = Depends(get_db)):
    user = ensure_user(db, uid)
    q = db.query(Order).filter(Order.user_id == user.id).order_by(Order.created_at.desc()).all()
    db.commit()
    return {"ok": True, "orders": [
        {
            "id": o.id,
            "title": o.title,
            "quantity": o.quantity,
            "price": float(o.price),
            "payload": o.payload,
            "status": o.status,
            "created_at": o.created_at
        } for o in q
    ]}

@router.get("/notifications/my")
def my_notifications(uid: str, db: Session = Depends(get_db)):
    user = ensure_user(db, uid)
    q = db.query(Notification)\
        .filter(Notification.is_for_owner == False, Notification.user_id == user.id)\
        .order_by(Notification.created_at.desc()).limit(100).all()
    db.commit()
    return {"ok": True, "items": [
        {"id": n.id, "title": n.title, "body": n.body, "created_at": n.created_at} for n in q
    ]}

@router.post("/device/register")
def register_device(payload: DeviceIn, db: Session = Depends(get_db)):
    # يسمح بتسجيل جهاز مالك بدون uid
    user_id = None
    if payload.uid:
        user_id = ensure_user(db, payload.uid).id
    # تجاهل التكرار
    existing = db.query(DeviceToken).filter(DeviceToken.token == payload.token).first()
    if existing:
        existing.is_owner = payload.is_owner
    else:
        db.add(DeviceToken(user_id=user_id, token=payload.token, is_owner=payload.is_owner))
    db.commit()
    return {"ok": True}

import datetime as dt
import httpx
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import ADMIN_PASSWORD, JWT_SECRET, JWT_EXPIRE_DAYS, FCM_SERVER_KEY
from app.database import get_db
from app.models import Order, Wallet, WalletLedger, Notification, User, AsiacellCard, DeviceToken
from app.providers.smm_client import provider_balance
from app.provider_map import SERVICE_CATALOG

router = APIRouter()

# ====== نماذج ======
class AdminLoginIn(BaseModel):
    password: str

class ApproveIn(BaseModel):
    order_id: str

class RejectIn(BaseModel):
    order_id: str
    reason: str | None = None

class RefundIn(BaseModel):
    order_id: str

class WalletChangeIn(BaseModel):
    uid: str
    amount: float
    note: str | None = None

# ====== JWT ======
def make_token() -> str:
    expiry = dt.datetime.utcnow() + dt.timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode({"role": "admin", "exp": expiry}, JWT_SECRET, algorithm="HS256")

def require_admin(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")
    token = authorization[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("role") != "admin":
            raise HTTPException(status_code=401, detail="UNAUTHORIZED")
    except Exception:
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")

# ====== Routes ======
@router.post("/login")
def login(body: AdminLoginIn):
    if body.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")
    return {"ok": True, "token": make_token()}

@router.get("/pending/services", dependencies=[Depends(require_admin)])
def pending_services(db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.type=="provider", Order.status.in_(("PENDING","REVIEW")))\
        .order_by(Order.created_at.desc()).all()
    return {"ok": True, "items": [serialize_order(o) for o in q]}

@router.get("/pending/itunes", dependencies=[Depends(require_admin)])
def pending_itunes(db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.type=="manual", Order.title.contains("ايتونز"), Order.status=="REVIEW")\
        .order_by(Order.created_at.desc()).all()
    return {"ok": True, "items": [serialize_order(o) for o in q]}

@router.get("/pending/topups", dependencies=[Depends(require_admin)])
def pending_topups(db: Session = Depends(get_db)):
    q = db.query(AsiacellCard).filter(AsiacellCard.status=="REVIEW").order_by(AsiacellCard.created_at.desc()).all()
    return {"ok": True, "items": [{"id": c.id, "user_id": c.user_id, "card_number": c.card_number, "created_at": c.created_at} for c in q]}

@router.get("/pending/pubg", dependencies=[Depends(require_admin)])
def pending_pubg(db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.type=="manual", Order.title.contains("ببجي"), Order.status=="REVIEW")\
        .order_by(Order.created_at.desc()).all()
    return {"ok": True, "items": [serialize_order(o) for o in q]}

@router.get("/pending/ludo", dependencies=[Depends(require_admin)])
def pending_ludo(db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.type=="manual", Order.title.contains("لودو"), Order.status=="REVIEW")\
        .order_by(Order.created_at.desc()).all()
    return {"ok": True, "items": [serialize_order(o) for o in q]}

@router.post("/orders/approve", dependencies=[Depends(require_admin)])
def approve_order(body: ApproveIn, db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == body.order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
    o.status = "DONE"
    db.add(Notification(user_id=o.user_id, title="تم تنفيذ طلبك", body=f"({o.title}) أُنجز.", is_for_owner=False))
    db.commit()
    return {"ok": True}

@router.post("/orders/reject", dependencies=[Depends(require_admin)])
def reject_order(body: RejectIn, db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == body.order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
    # رد الرصيد إن لم يكن DONE
    if o.status != "DONE":
        w = db.query(Wallet).filter(Wallet.user_id == o.user_id).first()
        w.balance = float(w.balance) + float(o.price)
        db.add(WalletLedger(user_id=o.user_id, delta=float(o.price), reason="order_reject_refund", ref=o.id))
    o.status = "REJECTED"
    db.add(Notification(user_id=o.user_id, title="تم رفض طلبك", body=(body.reason or "تم رفض الطلب وسيُعاد الرصيد."), is_for_owner=False))
    db.commit()
    return {"ok": True}

@router.post("/orders/refund", dependencies=[Depends(require_admin)])
def refund_order(body: RefundIn, db: Session = Depends(get_db)):
    o = db.query(Order).filter(Order.id == body.order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="ORDER_NOT_FOUND")
    w = db.query(Wallet).filter(Wallet.user_id == o.user_id).first()
    w.balance = float(w.balance) + float(o.price)
    o.status = "REFUNDED"
    db.add(WalletLedger(user_id=o.user_id, delta=float(o.price), reason="manual_refund", ref=o.id))
    db.add(Notification(user_id=o.user_id, title="تم رد المبلغ", body=f"تم رد {float(o.price):.2f}$ للطلب ({o.title}).", is_for_owner=False))
    db.commit()
    return {"ok": True}

@router.post("/wallet/topup", dependencies=[Depends(require_admin)])
def wallet_topup(body: WalletChangeIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.uid == body.uid).first()
    if not u:
        u = User(uid=body.uid); db.add(u); db.flush(); db.add(Wallet(user_id=u.id, balance=0)); db.flush()
    w = db.query(Wallet).filter(Wallet.user_id == u.id).first()
    w.balance = float(w.balance) + float(body.amount)
    db.add(WalletLedger(user_id=u.id, delta=float(body.amount), reason="admin_topup", ref=body.note))
    db.add(Notification(user_id=u.id, title="تم شحن رصيدك", body=f"المبلغ: {float(body.amount):.2f}$"))
    db.commit()
    return {"ok": True, "balance": float(w.balance)}

@router.post("/wallet/deduct", dependencies=[Depends(require_admin)])
def wallet_deduct(body: WalletChangeIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.uid == body.uid).first()
    if not u:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    w = db.query(Wallet).filter(Wallet.user_id == u.id).first()
    w.balance = max(0.0, float(w.balance) - float(body.amount))
    db.add(WalletLedger(user_id=u.id, delta=-float(body.amount), reason="admin_deduct", ref=body.note))
    db.commit()
    return {"ok": True, "balance": float(w.balance)}

@router.get("/stats/users-count", dependencies=[Depends(require_admin)])
def users_count(db: Session = Depends(get_db)):
    cnt = db.query(User).count()
    return {"ok": True, "count": cnt}

@router.get("/stats/users-balances", dependencies=[Depends(require_admin)])
def users_balances(db: Session = Depends(get_db)):
    total = db.query(Wallet).with_entities(func.coalesce(func.sum(Wallet.balance), 0)).scalar()  # type: ignore
    return {"ok": True, "total_balance": float(total or 0)}

@router.get("/provider/balance", dependencies=[Depends(require_admin)])
async def provider_bal():
    try:
        info = await provider_balance()
    except Exception:
        info = {"balance": 0}
    return {"ok": True, "provider": info}

# (اختياري) إرسال إشعار دفع عبر FCM لكل أجهزة المالك أو لمستخدم معيّن
@router.post("/notify/push", dependencies=[Depends(require_admin)])
async def push_notify(title: str, body: str, uid: str | None = None, to_owner: bool = False, db: Session = Depends(get_db)):
    if not FCM_SERVER_KEY:
        raise HTTPException(status_code=400, detail="FCM_NOT_CONFIGURED")

    q = db.query(DeviceToken)
    if uid:
        user = db.query(User).filter(User.uid == uid).first()
        if not user: return {"ok": True, "sent": 0}
        q = q.filter(DeviceToken.user_id == user.id)
    if to_owner:
        q = q.filter(DeviceToken.is_owner == True)
    tokens = [t.token for t in q.all()]
    if not tokens:
        return {"ok": True, "sent": 0}

    headers = {"Authorization": f"key={FCM_SERVER_KEY}", "Content-Type": "application/json"}
    payload = {"registration_ids": tokens, "notification": {"title": title, "body": body}}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post("https://fcm.googleapis.com/fcm/send", headers=headers, json=payload)
        r.raise_for_status()
    return {"ok": True, "sent": len(tokens)}

# ====== Helpers ======
from sqlalchemy import func  # used above

def serialize_order(o: Order):
    return {
        "id": o.id, "user_id": o.user_id, "type": o.type, "service_id": o.service_id,
        "title": o.title, "quantity": o.quantity, "price": float(o.price),
        "payload": o.payload, "status": o.status, "created_at": o.created_at
    }

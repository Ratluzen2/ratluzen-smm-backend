from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, ServiceOrder, ItunesOrder, PhoneTopup, PubgOrder, LudoOrder, WalletCard, Token

r = APIRouter()

@r.get("/health")
def health():
    return {"ok": True}

# إنشاء/إرجاع مستخدم بالـ UID
@r.post("/users/upsert")
def upsert_user(uid: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(uid=uid).first()
    if not user:
        user = User(uid=uid)
        db.add(user); db.commit(); db.refresh(user)
    return {"ok": True, "user": {"uid": user.uid, "balance": user.balance, "is_banned": user.is_banned}}

@r.get("/users/{uid}/balance")
def user_balance(uid: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(uid=uid).first()
    if not user:
        raise HTTPException(404, "user not found")
    return {"ok": True, "balance": user.balance}

@r.get("/users/{uid}/orders")
def user_orders(uid: str, db: Session = Depends(get_db)):
    def map_list(rows, typ): 
        return [dict(type=typ, **{c.name: getattr(x, c.name) for c in x.__table__.columns}) for x in rows]
    srv = db.query(ServiceOrder).filter_by(uid=uid).order_by(ServiceOrder.created_at.desc()).all()
    it  = db.query(ItunesOrder).filter_by(uid=uid).order_by(ItunesOrder.created_at.desc()).all()
    ph  = db.query(PhoneTopup).filter_by(uid=uid).order_by(PhoneTopup.created_at.desc()).all()
    pb  = db.query(PubgOrder).filter_by(uid=uid).order_by(PubgOrder.created_at.desc()).all()
    ld  = db.query(LudoOrder).filter_by(uid=uid).order_by(LudoOrder.created_at.desc()).all()
    cd  = db.query(WalletCard).filter_by(uid=uid).order_by(WalletCard.created_at.desc()).all()
    orders = map_list(srv,"service")+map_list(it,"itunes")+map_list(ph,"phone")+map_list(pb,"pubg")+map_list(ld,"ludo")+map_list(cd,"asiacell_card")
    orders.sort(key=lambda x: x["created_at"], reverse=True)
    return {"ok": True, "orders": orders}

# حفظ توكن FCM
@r.post("/notify/register-token")
def register_token(token: str, uid: str | None = None, for_owner: bool = False, db: Session = Depends(get_db)):
    old = db.query(Token).filter_by(token=token).first()
    if old:
        db.delete(old); db.commit()
    t = Token(uid=uid, token=token, for_owner=for_owner)
    db.add(t); db.commit()
    return {"ok": True}

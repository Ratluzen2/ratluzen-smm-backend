from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User

router = APIRouter(prefix="/users", tags=["users"])

class UpsertIn(BaseModel):
    uid: str

@router.post("/upsert")
def upsert_user(payload: UpsertIn, db: Session = Depends(get_db)):
    """
    يستقبل {uid} من التطبيق في أول تشغيل:
    - ينشئ مستخدمًا جديدًا إن لم يوجد
    - يعيد بيانات المستخدم إن كان موجودًا
    """
    uid = (payload.uid or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="uid required")

    user = db.query(User).filter_by(uid=uid).first()
    if user is None:
        user = User(uid=uid, balance=0.0, role="user")
        db.add(user)
        db.commit()
        db.refresh(user)
        return {"ok": True, "created": True, "id": user.id, "uid": user.uid, "balance": float(user.balance)}

    return {"ok": True, "created": False, "id": user.id, "uid": user.uid, "balance": float(user.balance)}

@router.get("/{uid}")
def get_user(uid: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(uid=uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return {
        "ok": True,
        "id": user.id,
        "uid": user.uid,
        "balance": float(user.balance or 0.0),
        "is_banned": bool(user.is_banned),
        "role": user.role,
        "created_at": str(user.created_at) if user.created_at else None,
    }

@router.get("/{uid}/balance")
def get_user_balance(uid: str, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(uid=uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return {"ok": True, "uid": user.uid, "balance": float(user.balance or 0.0)}

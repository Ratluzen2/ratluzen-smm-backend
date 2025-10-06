from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from ..db import get_db
from ..models import User

router = APIRouter()

class UpsertIn(BaseModel):
    uid: str = Field(min_length=1, max_length=32)

@router.get("/health")
def health():
    return {"ok": True}

@router.post("/api/users/upsert")
def upsert_user(payload: UpsertIn, db: Session = Depends(get_db)):
    user = db.get(User, payload.uid)
    if not user:
        user = User(uid=payload.uid, balance_usd=0)
        db.add(user)
        db.commit()
    return {"ok": True, "uid": payload.uid}

@router.get("/api/users/{uid}/balance")
def get_balance(uid: str, db: Session = Depends(get_db)):
    user = db.get(User, uid)
    if not user:
        raise HTTPException(404, "user not found")
    return {"uid": uid, "balance": float(user.balance_usd)}

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from datetime import datetime
import re

from ..database import get_db
from ..models import User, WalletCard, Notice, Token

r = APIRouter()

def _row(obj):
    if obj is None:
        return None
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    return out

@r.get("/ping")
def ping():
    return {"ok": True}

@r.post("/users/upsert")
def users_upsert(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    if not uid:
        raise HTTPException(400, "uid required")
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0, is_banned=False)
        db.add(u)
        db.add(Notice(title="مستخدم جديد", body=f"UID: {uid}", for_owner=True, uid=None))
        db.commit()
    return {"ok": True, "user": {"uid": u.uid, "balance": u.balance, "is_banned": u.is_banned}}

@r.get("/users/balance")
def users_balance(uid: str = Query(...), db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0, is_banned=False)
        db.add(u); db.commit()
    return {"ok": True, "uid": u.uid, "balance": u.balance, "is_banned": u.is_banned}

@r.get("/notices")
def get_notices(uid: str = Query(...), db: Session = Depends(get_db)):
    lst = (
        db.query(Notice)
        .filter((Notice.uid == uid) | (Notice.uid.is_(None)))
        .order_by(Notice.created_at.desc())
        .limit(50)
        .all()
    )
    return {"ok": True, "list": [_row(n) for n in lst]}

@r.post("/tokens/register")
def register_token(payload: dict = Body(...), db: Session = Depends(get_db)):
    token = (payload.get("token") or "").strip()
    uid = (payload.get("uid") or "").strip() or None
    for_owner = bool(payload.get("for_owner", False))
    if not token:
        raise HTTPException(400, "token required")
    exists = db.query(Token).filter_by(token=token).first()
    if exists:
        exists.uid = uid
        exists.for_owner = for_owner
        db.add(exists)
        db.commit()
        return {"ok": True, "updated": True}
    db.add(Token(token=token, uid=uid, for_owner=for_owner))
    db.commit()
    return {"ok": True, "saved": True}

@r.post("/wallet/asiacell/submit")
def submit_asiacell_card(payload: dict = Body(...), db: Session = Depends(get_db)):
    uid = (payload.get("uid") or "").strip()
    card = re.sub(r"\D+", "", (payload.get("cardNumber") or ""))
    if not uid:
        raise HTTPException(400, "uid required")
    if not card or len(card) not in (14, 16):
        raise HTTPException(400, "card number must be 14 or 16 digits")

    u = db.query(User).filter_by(uid=uid).first()
    if not u:
        u = User(uid=uid, balance=0.0, is_banned=False)
        db.add(u); db.commit()

    wc = WalletCard(uid=uid, card_number=card, status="pending", amount_usd=None, reviewed_by=None)
    db.add(wc)
    db.add(Notice(
        title="كارت أسيا سيل جديد",
        body=f"UID={uid}\nCARD={card}",
        for_owner=True,
        uid=None
    ))
    db.commit()
    return {"ok": True, "card": _row(wc)}

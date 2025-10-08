# app/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice, Token
)
from ..providers.smm_client import provider_add_order, provider_balance

r = APIRouter(prefix="/admin")

# ---------------------- Helpers ----------------------
def _ts(dt: Optional[datetime]) -> int:
    return int((dt or datetime.utcnow()).timestamp() * 1000)

def _svc_row(o: ServiceOrder) -> Dict[str, Any]:
    return {
        "id": f"svc-{o.id}",
        "title": f"خدمة: {o.service_key}",
        "quantity": o.quantity,
        "price": round(float(o.price or 0), 2),
        "payload": o.link,  # الرابط للعرض/النسخ
        "created_at": _ts(o.created_at),
        "status": o.status,
    }

def _top_row(o: WalletCard) -> Dict[str, Any]:
    return {
        "id": f"top-{o.id}",
        "title": "كارت أسيا سيل",
        "quantity": 1,
        "price": float(o.amount_usd or 0.0),
        "payload": o.card_number,  # يظهر للمالك حتى ينسخه
        "created_at": _ts(o.created_at),
        "status": o.status,
    }

def _itunes_row(o: ItunesOrder) -> Dict[str, Any]:
    return {
        "id": f"itn-{o.id}",
        "title": f"iTunes ${o.amount}",
        "quantity": 1,
        "price": float(o.amount or 0.0),
        "payload": o.gift_code or "",
        "created_at": _ts(o.created_at),
        "status": o.status,
    }

def _pubg_row(o: PubgOrder) -> Dict[str, Any]:
    return {
        "id": f"pubg-{o.id}",
        "title": f"PUBG {o.pkg} UC",
        "quantity": o.pkg,
        "price": 0.0,
        "payload": o.pubg_id,
        "created_at": _ts(o.created_at),
        "status": o.status,
    }

def _ludo_row(o: LudoOrder) -> Dict[str, Any]:
    return {
        "id": f"ludo-{o.id}",
        "title": f"Ludo {o.kind} {o.pack}",
        "quantity": o.pack,
        "price": 0.0,
        "payload": o.ludo_id,
        "created_at": _ts(o.created_at),
        "status": o.status,
    }

def _notice(db: Session, title: str, body: str, uid: Optional[str]):
    db.add(Notice(title=title, body=body, for_owner=False, uid=uid))

# ---------------------- Guard ----------------------
def guard(x_admin_pass: Optional[str] = Header(None, alias="x-admin-pass")):
    if (x_admin_pass or "").strip() != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

# ---------------------- Auth -----------------------
@r.post("/login")
def admin_login(password: str = Body(..., embed=True)):
    if password == settings.ADMIN_PASSWORD:
        return {"token": password}
    raise HTTPException(401, "unauthorized")

# ---------------------- Pending lists (ARRAY) ----------------------
@r.get("/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(ServiceOrder)
        .filter(ServiceOrder.status == "pending")
        .order_by(ServiceOrder.created_at.desc())
        .all()
    )
    return [_svc_row(o) for o in rows]

@r.get("/pending/topups", dependencies=[Depends(guard)])
def pending_topups(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(WalletCard)
        .filter(WalletCard.status == "pending")
        .order_by(WalletCard.created_at.desc())
        .all()
    )
    return [_top_row(o) for o in rows]

@r.get("/pending/itunes", dependencies=[Depends(guard)])
def pending_itunes(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(ItunesOrder)
        .filter(ItunesOrder.status == "pending")
        .order_by(ItunesOrder.created_at.desc())
        .all()
    )
    return [_itunes_row(o) for o in rows]

@r.get("/pending/pubg", dependencies=[Depends(guard)])
def pending_pubg(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(PubgOrder)
        .filter(PubgOrder.status == "pending")
        .order_by(PubgOrder.created_at.desc())
        .all()
    )
    return [_pubg_row(o) for o in rows]

@r.get("/pending/ludo", dependencies=[Depends(guard)])
def pending_ludo(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(LudoOrder)
        .filter(LudoOrder.status == "pending")
        .order_by(LudoOrder.created_at.desc())
        .all()
    )
    return [_ludo_row(o) for o in rows]

# ---------------------- Actions: approve / reject / refund ----------------------
class ApproveReq(Any):
    ...

@r.post("/orders/approve", dependencies=[Depends(guard)])
def order_approve(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    """
    JSON:
    {"order_id": "svc-12"} أو {"order_id":"top-5","amount":10.0} أو {"order_id":"itn-3","gift_code":"XXXX"}
    """
    order_id = str(payload.get("order_id", "")).strip()
    if not order_id or "-" not in order_id:
        raise HTTPException(400, "order_id required")

    prefix, sid = order_id.split("-", 1)
    # -------- services (KD1S) --------
    if prefix == "svc":
        o = db.get(ServiceOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")

        # إرسال فعلي إلى KD1S باستخدام رقم الخدمة المخزّن service_code
        res = provider_add_order(
            service_id=o.service_code,
            link=o.link,
            quantity=o.quantity
        )
        if not res.get("ok"):
            raise HTTPException(502, res.get("error", "provider error"))

        o.status = "processing"
        o.provider_order_id = str(res.get("orderId") or res.get("order_id") or "")
        db.add(o)
        _notice(db, "تم تنفيذ طلبك", f"تم إرسال طلب {o.service_key} للمزوّد. رقم المزود: {o.provider_order_id}", o.uid)
        db.commit()
        return {"ok": True, "provider_order_id": o.provider_order_id}

    # -------- topups (Asiacell card) --------
    if prefix == "top":
        amount = payload.get("amount")
        if amount is None:
            raise HTTPException(400, "amount required")
        amount = float(amount)

        o = db.get(WalletCard, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")

        o.status = "accepted"
        o.amount_usd = amount
        o.reviewed_by = "owner"
        user = db.query(User).filter_by(uid=o.uid).first()
        if not user:
            user = User(uid=o.uid, balance=0.0)
        user.balance = round(user.balance + amount, 2)
        db.add(user)
        db.add(o)
        _notice(db, "تم شحن رصيدك", f"+${amount} عبر كارت أسيا سيل", o.uid)
        db.commit()
        return {"ok": True}

    # -------- itunes --------
    if prefix == "itn":
        gift_code = str(payload.get("gift_code") or "").strip()
        if not gift_code:
            raise HTTPException(400, "gift_code required")

        o = db.get(ItunesOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")

        o.status = "delivered"
        o.gift_code = gift_code
        db.add(o)
        _notice(db, "كود آيتونز", f"الكود: {gift_code}", o.uid)
        db.commit()
        return {"ok": True}

    # -------- pubg --------
    if prefix == "pubg":
        o = db.get(PubgOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "delivered"
        db.add(o)
        _notice(db, "تم شحن شداتك", f"حزمة {o.pkg} UC", o.uid)
        db.commit()
        return {"ok": True}

    # -------- ludo --------
    if prefix == "ludo":
        o = db.get(LudoOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "delivered"
        db.add(o)
        _notice(db, "تم تنفيذ لودو", f"{o.kind} {o.pack}", o.uid)
        db.commit()
        return {"ok": True}

    raise HTTPException(400, "unsupported order type")

@r.post("/orders/reject", dependencies=[Depends(guard)])
def order_reject(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    order_id = str(payload.get("order_id", "")).strip()
    if not order_id or "-" not in order_id:
        raise HTTPException(400, "order_id required")
    prefix, sid = order_id.split("-", 1)

    if prefix == "svc":
        o = db.get(ServiceOrder, int(sid))
        if not o or o.status not in ("pending", "processing"):
            raise HTTPException(404, "not found")
        o.status = "rejected"
        # ردّ الرصيد
        user = db.query(User).filter_by(uid=o.uid).first()
        if user:
            user.balance = round(user.balance + float(o.price or 0.0), 2)
            db.add(user)
        db.add(o)
        _notice(db, "تم رفض الطلب", "تم ردّ رصيدك", o.uid)
        db.commit()
        return {"ok": True}

    if prefix == "top":
        o = db.get(WalletCard, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "rejected"
        db.add(o)
        _notice(db, "رفض كارت أسيا سيل", "يرجى التأكد من الرقم والمحاولة مجددًا.", o.uid)
        db.commit()
        return {"ok": True}

    if prefix == "itn":
        o = db.get(ItunesOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "rejected"
        db.add(o)
        _notice(db, "رفض آيتونز", "تم رفض الطلب.", o.uid)
        db.commit()
        return {"ok": True}

    if prefix == "pubg":
        o = db.get(PubgOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "rejected"
        db.add(o)
        _notice(db, "رفض شدات ببجي", "تم رفض الطلب.", o.uid)
        db.commit()
        return {"ok": True}

    if prefix == "ludo":
        o = db.get(LudoOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "rejected"
        db.add(o)
        _notice(db, "رفض طلب لودو", "تم رفض الطلب.", o.uid)
        db.commit()
        return {"ok": True}

    raise HTTPException(400, "unsupported order type")

@r.post("/orders/refund", dependencies=[Depends(guard)])
def order_refund(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    order_id = str(payload.get("order_id", "")).strip()
    if not order_id or "-" not in order_id:
        raise HTTPException(400, "order_id required")
    prefix, sid = order_id.split("-", 1)

    if prefix == "svc":
        o = db.get(ServiceOrder, int(sid))
        if not o:
            raise HTTPException(404, "not found")
        user = db.query(User).filter_by(uid=o.uid).first()
        if not user:
            raise HTTPException(404, "user not found")
        user.balance = round(user.balance + float(o.price or 0.0), 2)
        o.status = "refunded"
        db.add(user)
        db.add(o)
        _notice(db, "ردّ رصيد", f"تم ردّ ${o.price}", o.uid)
        db.commit()
        return {"ok": True}

    raise HTTPException(400, "refund not supported for this order type")

# ---------------------- Stats & Provider ----------------------
@r.get("/stats/users-count", dependencies=[Depends(guard)])
def users_count(db: Session = Depends(get_db)):
    total = db.query(User).count()
    return {"count": total}

@r.get("/stats/users-balances", dependencies=[Depends(guard)])
def users_balances(db: Session = Depends(get_db)):
    lst = db.query(User).order_by(User.balance.desc()).limit(500).all()
    total = sum(float(u.balance or 0.0) for u in lst)
    return {
        "total": round(total, 2),
        "list": [{"uid": u.uid, "balance": float(u.balance or 0.0)} for u in lst]
    }

@r.get("/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    res = provider_balance()
    # وحِّد الإخراج
    if isinstance(res, dict) and "balance" in res:
        return {"balance": float(res["balance"])}
    return {"balance": 0.0}

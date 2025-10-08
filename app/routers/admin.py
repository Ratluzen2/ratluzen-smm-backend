# app/routers/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..config import settings
from ..database import get_db
from ..models import (
    User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup,
    PubgOrder, LudoOrder, Notice
)
from ..providers.smm_client import provider_add_order, provider_balance

r = APIRouter(prefix="/admin", tags=["admin"])

# ---------------------- Helpers ----------------------
def _ts(dt: Optional[datetime]) -> int:
    return int((dt or datetime.utcnow()).timestamp() * 1000)

def _svc_row(o: ServiceOrder) -> Dict[str, Any]:
    return {
        "id": f"svc-{o.id}",
        "title": f"خدمة: {o.service_key}",
        "quantity": o.quantity,
        "price": float(o.price or 0.0),
        "payload": o.link,
        "created_at": _ts(o.created_at),
        "status": o.status,
    }

def _top_row(o: WalletCard) -> Dict[str, Any]:
    return {
        "id": f"top-{o.id}",
        "title": "كارت أسيا سيل",
        "quantity": 1,
        "price": float(o.amount_usd or 0.0),
        "payload": o.card_number,  # يُعرض للمالك للنسخ
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

def _notify(db: Session, uid: Optional[str], title: str, body: str):
    db.add(Notice(title=title, body=body, for_owner=False, uid=uid))

# ---------------------- Guard ----------------------
def guard(
    x_admin_pass: Optional[str] = Header(None, alias="x-admin-pass"),
    x_admin_pass_alt: Optional[str] = Header(None, alias="X-Admin-Pass"),
    key: Optional[str] = Query(None),
):
    pwd = (x_admin_pass or x_admin_pass_alt or key or "").strip()
    if pwd != (settings.ADMIN_PASSWORD or ""):
        raise HTTPException(401, "unauthorized")

@r.get("/check", dependencies=[Depends(guard)])
def check_ok():
    return {"ok": True}

# ---------------------- Auth -----------------------
@r.post("/login")
def admin_login(password: str = Body(..., embed=True)):
    if password == (settings.ADMIN_PASSWORD or ""):
        return {"token": password}
    raise HTTPException(401, "unauthorized")

# ---------------------- Pending lists (return ARRAY) ----------------------
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
@r.post("/orders/approve", dependencies=[Depends(guard)])
def order_approve(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    """
    JSON أمثلة:
    {"order_id":"svc-12"}
    {"order_id":"top-5","amount":10.0}
    {"order_id":"itn-3","gift_code":"XXXX-XXXX"}
    """
    order_id = str(payload.get("order_id", "")).strip()
    if not order_id or "-" not in order_id:
        raise HTTPException(400, "order_id required")

    kind, sid = order_id.split("-", 1)

    if kind == "svc":
        o = db.get(ServiceOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")

        # إرسال فعلي إلى KD1S باستخدام رقم الخدمة المخزّن service_code
        res = provider_add_order(service_id=o.service_code, link=o.link, quantity=o.quantity)
        if not res or not res.get("ok"):
            raise HTTPException(502, res.get("error", "provider error") if isinstance(res, dict) else "provider error")

        o.status = "processing"
        o.provider_order_id = str(res.get("orderId") or res.get("order_id") or "")
        db.add(o)
        _notify(db, o.uid, "تم تنفيذ طلبك", f"أُرسل طلب {o.service_key} للمزوّد. رقم المزود: {o.provider_order_id}")
        db.commit()
        return {"ok": True, "provider_order_id": o.provider_order_id}

    if kind == "top":
        amount = payload.get("amount", None)
        if amount is None:
            raise HTTPException(400, "amount required")
        amount = float(amount)

        o = db.get(WalletCard, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")

        o.status = "accepted"
        o.amount_usd = amount
        o.reviewed_by = "owner"

        u = db.query(User).filter_by(uid=o.uid).first()
        if not u:
            u = User(uid=o.uid, balance=0.0)
        u.balance = round((u.balance or 0.0) + amount, 2)
        db.add(u); db.add(o)
        _notify(db, o.uid, "تم شحن رصيدك", f"+${amount} عبر كارت أسيا سيل")
        db.commit()
        return {"ok": True}

    if kind == "itn":
        gift_code = str(payload.get("gift_code") or "").strip()
        if not gift_code:
            raise HTTPException(400, "gift_code required")
        o = db.get(ItunesOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "delivered"
        o.gift_code = gift_code
        db.add(o)
        _notify(db, o.uid, "كود آيتونز", f"الكود: {gift_code}")
        db.commit()
        return {"ok": True}

    if kind == "pubg":
        o = db.get(PubgOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "delivered"
        db.add(o)
        _notify(db, o.uid, "تم شحن شداتك", f"حزمة {o.pkg} UC")
        db.commit()
        return {"ok": True}

    if kind == "ludo":
        o = db.get(LudoOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "delivered"
        db.add(o)
        _notify(db, o.uid, "تم تنفيذ لودو", f"{o.kind} {o.pack}")
        db.commit()
        return {"ok": True}

    raise HTTPException(400, "unsupported order type")

@r.post("/orders/reject", dependencies=[Depends(guard)])
def order_reject(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    order_id = str(payload.get("order_id", "")).strip()
    if not order_id or "-" not in order_id:
        raise HTTPException(400, "order_id required")
    kind, sid = order_id.split("-", 1)

    if kind == "svc":
        o = db.get(ServiceOrder, int(sid))
        if not o or o.status not in ("pending", "processing"):
            raise HTTPException(404, "not found")
        # ردّ الرصيد إذا كان مدفوعًا
        u = db.query(User).filter_by(uid=o.uid).first()
        if u:
            u.balance = round((u.balance or 0.0) + float(o.price or 0.0), 2)
            db.add(u)
        o.status = "rejected"
        db.add(o)
        _notify(db, o.uid, "تم رفض الطلب", "تم ردّ رصيدك")
        db.commit()
        return {"ok": True}

    if kind == "top":
        o = db.get(WalletCard, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "rejected"
        db.add(o)
        _notify(db, o.uid, "رفض كارت أسيا سيل", "يرجى التأكد من الرقم والمحاولة مجددًا.")
        db.commit()
        return {"ok": True}

    if kind == "itn":
        o = db.get(ItunesOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "rejected"
        db.add(o)
        _notify(db, o.uid, "رفض آيتونز", "تم رفض الطلب.")
        db.commit()
        return {"ok": True}

    if kind == "pubg":
        o = db.get(PubgOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "rejected"
        db.add(o)
        _notify(db, o.uid, "رفض شدات ببجي", "تم رفض الطلب.")
        db.commit()
        return {"ok": True}

    if kind == "ludo":
        o = db.get(LudoOrder, int(sid))
        if not o or o.status != "pending":
            raise HTTPException(404, "not found/pending")
        o.status = "rejected"
        db.add(o)
        _notify(db, o.uid, "رفض طلب لودو", "تم رفض الطلب.")
        db.commit()
        return {"ok": True}

    raise HTTPException(400, "unsupported order type")

@r.post("/orders/refund", dependencies=[Depends(guard)])
def order_refund(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    order_id = str(payload.get("order_id", "")).strip()
    if not order_id or "-" not in order_id:
        raise HTTPException(400, "order_id required")
    kind, sid = order_id.split("-", 1)

    if kind == "svc":
        o = db.get(ServiceOrder, int(sid))
        if not o:
            raise HTTPException(404, "not found")
        u = db.query(User).filter_by(uid=o.uid).first()
        if not u:
            raise HTTPException(404, "user not found")
        u.balance = round((u.balance or 0.0) + float(o.price or 0.0), 2)
        o.status = "refunded"
        db.add(u); db.add(o)
        _notify(db, o.uid, "ردّ رصيد", f"تم ردّ ${o.price}")
        db.commit()
        return {"ok": True}

    raise HTTPException(400, "refund not supported for this order type")

# ---------------------- Wallet (owner actions) ----------------------
@r.post("/wallet/topup", dependencies=[Depends(guard)])
def wallet_topup(data: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    uid = str(data.get("uid", "")).strip()
    amount = float(data.get("amount", 0))
    if not uid or amount <= 0:
        raise HTTPException(400, "uid & amount required")
    u = db.query(User).filter_by(uid=uid).first() or User(uid=uid, balance=0.0)
    u.balance = round((u.balance or 0.0) + amount, 2)
    db.add(u)
    _notify(db, uid, "تم إضافة رصيد", f"+${amount}")
    db.commit()
    return {"ok": True, "balance": u.balance}

@r.post("/wallet/deduct", dependencies=[Depends(guard)])
def wallet_deduct(data: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    uid = str(data.get("uid", "")).strip()
    amount = float(data.get("amount", 0))
    if not uid or amount <= 0:
        raise HTTPException(400, "uid & amount required")
    u = db.query(User).filter_by(uid=uid).first() or User(uid=uid, balance=0.0)
    newb = max(0.0, (u.balance or 0.0) - amount)
    u.balance = round(newb, 2)
    db.add(u)
    _notify(db, uid, "تم خصم رصيد", f"-${amount}")
    db.commit()
    return {"ok": True, "balance": u.balance}

# ---------------------- Stats & Provider ----------------------
@r.get("/stats/users-count", dependencies=[Depends(guard)])
def users_count(db: Session = Depends(get_db)):
    total = db.query(User).count()
    return {"count": total}

@r.get("/stats/users-balances", dependencies=[Depends(guard)])
def users_balances(db: Session = Depends(get_db)):
    lst = db.query(User).order_by(User.balance.desc()).limit(500).all()
    total = sum(float(u.balance or 0.0) for u in lst)
    return {"total": round(total, 2), "list": [{"uid": u.uid, "balance": float(u.balance or 0.0)} for u in lst]}

@r.get("/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    res = provider_balance()
    if isinstance(res, dict) and "balance" in res:
        try:
            return {"balance": float(res["balance"])}
        except Exception:
            pass
    return {"balance": 0.0}

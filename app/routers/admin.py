from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from ..config import settings
from ..database import get_db
from ..models import User, ServiceOrder, WalletCard, ItunesOrder, PhoneTopup, PubgOrder, LudoOrder, Notice, Token
from ..providers.smm_client import provider_add_order, provider_balance, provider_status

r = APIRouter(prefix="/admin")

def guard(pass_hdr: Optional[str] = Header(default=None, alias="x-admin-pass")):
    if (pass_hdr or "").strip() != settings.ADMIN_PASSWORD:
        raise HTTPException(401, "unauthorized")

# ---------- الخدمات المعلّقة ----------
@r.get("/pending/services", dependencies=[Depends(guard)])
def pending_services(db: Session = Depends(get_db)):
    lst = db.query(ServiceOrder).filter_by(status="pending").order_by(ServiceOrder.created_at.desc()).all()
    return {"ok": True, "list": lst}

@r.post("/pending/services/{order_id}/approve", dependencies=[Depends(guard)])
def approve_service(order_id: int, db: Session = Depends(get_db)):
    order = db.query(ServiceOrder).get(order_id)
    if not order or order.status != "pending":
        raise HTTPException(404, "order not found or not pending")
    send = provider_add_order(order.service_key, order.link, order.quantity)
    if not send.get("ok"):
        raise HTTPException(502, send.get("error", "provider error"))
    order.status = "processing"
    order.provider_order_id = send["orderId"]
    db.add(order)
    db.add(Notice(title="تم تنفيذ طلبك",
                  body=f"أُرسل طلبك للمزوّد. رقم المزود: {order.provider_order_id}",
                  for_owner=False, uid=order.uid))
    db.commit()
    return {"ok": True, "order": order}

@r.post("/pending/services/{order_id}/reject", dependencies=[Depends(guard)])
def reject_service(order_id: int, db: Session = Depends(get_db)):
    order = db.query(ServiceOrder).get(order_id)
    if not order or order.status != "pending":
        raise HTTPException(404, "order not found or not pending")
    order.status = "rejected"
    # رد الرصيد
    u = db.query(User).filter_by(uid=order.uid).first()
    if u:
        u.balance = round(u.balance + order.price, 2)
        db.add(u)
    db.add(order)
    db.add(Notice(title="تم رفض الطلب", body="تم رفض طلبك وتم ردّ الرصيد.", for_owner=False, uid=order.uid))
    db.commit()
    return {"ok": True}

# رصيد المزود وحالة الطلب
@r.get("/provider/balance", dependencies=[Depends(guard)])
def provider_bal():
    return provider_balance()

@r.get("/provider/order-status/{ext_order_id}", dependencies=[Depends(guard)])
def provider_order_status(ext_order_id: str):
    return provider_status(ext_order_id)

# ---------- كارتات أسيا سيل ----------
@r.get("/pending/cards", dependencies=[Depends(guard)])
def pending_cards(db: Session = Depends(get_db)):
    lst = db.query(WalletCard).filter_by(status="pending").order_by(WalletCard.created_at.desc()).all()
    return {"ok": True, "list": lst}

@r.post("/pending/cards/{card_id}/accept", dependencies=[Depends(guard)])
def accept_card(card_id: int, amount_usd: float, reviewed_by: str = "owner", db: Session = Depends(get_db)):
    card = db.query(WalletCard).get(card_id)
    if not card or card.status != "pending":
        raise HTTPException(404, "card not found or not pending")
    card.status = "accepted"
    card.amount_usd = amount_usd
    card.reviewed_by = reviewed_by
    u = db.query(User).filter_by(uid=card.uid).first()
    if u:
        u.balance = round(u.balance + amount_usd, 2)
        db.add(u)
    db.add(card)
    db.add(Notice(title="تم شحن رصيدك", body=f"+${amount_usd} عبر بطاقة أسيا سيل", for_owner=False, uid=card.uid))
    db.commit()
    return {"ok": True}

@r.post("/pending/cards/{card_id}/reject", dependencies=[Depends(guard)])
def reject_card(card_id: int, db: Session = Depends(get_db)):
    card = db.query(WalletCard).get(card_id)
    if not card or card.status != "pending":
        raise HTTPException(404, "card not found or not pending")
    card.status = "rejected"
    db.add(card)
    db.add(Notice(title="تم رفض الكارت", body="يرجى التأكد من الرقم والمحاولة مجددًا.", for_owner=False, uid=card.uid))
    db.commit()
    return {"ok": True}

# ---------- آيتونز ----------
@r.get("/pending/itunes", dependencies=[Depends(guard)])
def pending_itunes(db: Session = Depends(get_db)):
    lst = db.query(ItunesOrder).filter_by(status="pending").order_by(ItunesOrder.created_at.desc()).all()
    return {"ok": True, "list": lst}

@r.post("/pending/itunes/{oid}/deliver", dependencies=[Depends(guard)])
def deliver_itunes(oid: int, gift_code: str, db: Session = Depends(get_db)):
    o = db.query(ItunesOrder).get(oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"; o.gift_code = gift_code
    db.add(o)
    db.add(Notice(title="كود آيتونز", body=f"الكود: {gift_code}", for_owner=False, uid=o.uid))
    db.commit()
    return {"ok": True}

@r.post("/pending/itunes/{oid}/reject", dependencies=[Depends(guard)])
def reject_itunes(oid: int, db: Session = Depends(get_db)):
    o = db.query(ItunesOrder).get(oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "rejected"
    db.add(o); db.add(Notice(title="رفض آيتونز", body="تم رفض طلبك.", for_owner=False, uid=o.uid))
    db.commit(); return {"ok": True}

# ---------- أرصدة الهاتف ----------
@r.get("/pending/phone", dependencies=[Depends(guard)])
def pending_phone(db: Session = Depends(get_db)):
    lst = db.query(PhoneTopup).filter_by(status="pending").order_by(PhoneTopup.created_at.desc()).all()
    return {"ok": True, "list": lst}

@r.post("/pending/phone/{oid}/deliver", dependencies=[Depends(guard)])
def deliver_phone(oid: int, code: str, db: Session = Depends(get_db)):
    o = db.query(PhoneTopup).get(oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"; o.code = code
    db.add(o); db.add(Notice(title="كارت الهاتف", body=f"الكود: {code}", for_owner=False, uid=o.uid))
    db.commit(); return {"ok": True}

@r.post("/pending/phone/{oid}/reject", dependencies=[Depends(guard)])
def reject_phone(oid: int, db: Session = Depends(get_db)):
    o = db.query(PhoneTopup).get(oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "rejected"
    db.add(o); db.add(Notice(title="رفض رصيد الهاتف", body="تم رفض الطلب.", for_owner=False, uid=o.uid))
    db.commit(); return {"ok": True}

# ---------- PUBG ----------
@r.get("/pending/pubg", dependencies=[Depends(guard)])
def pending_pubg(db: Session = Depends(get_db)):
    lst = db.query(PubgOrder).filter_by(status="pending").order_by(PubgOrder.created_at.desc()).all()
    return {"ok": True, "list": lst}

@r.post("/pending/pubg/{oid}/deliver", dependencies=[Depends(guard)])
def deliver_pubg(oid: int, db: Session = Depends(get_db)):
    o = db.query(PubgOrder).get(oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"
    db.add(o); db.add(Notice(title="تم شحن شداتك", body=f"حزمة {o.pkg} UC", for_owner=False, uid=o.uid))
    db.commit(); return {"ok": True}

@r.post("/pending/pubg/{oid}/reject", dependencies=[Depends(guard)])
def reject_pubg(oid: int, db: Session = Depends(get_db)):
    o = db.query(PubgOrder).get(oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "rejected"
    db.add(o); db.add(Notice(title="رفض شدات ببجي", body="تم رفض طلبك.", for_owner=False, uid=o.uid))
    db.commit(); return {"ok": True}

# ---------- لودو ----------
@r.get("/pending/ludo", dependencies=[Depends(guard)])
def pending_ludo(db: Session = Depends(get_db)):
    lst = db.query(LudoOrder).filter_by(status="pending").order_by(LudoOrder.created_at.desc()).all()
    return {"ok": True, "list": lst}

@r.post("/pending/ludo/{oid}/deliver", dependencies=[Depends(guard)])
def deliver_ludo(oid: int, db: Session = Depends(get_db)):
    o = db.query(LudoOrder).get(oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "delivered"
    db.add(o); db.add(Notice(title="تم تنفيذ لودو", body=f"{o.kind} {o.pack}", for_owner=False, uid=o.uid))
    db.commit(); return {"ok": True}

@r.post("/pending/ludo/{oid}/reject", dependencies=[Depends(guard)])
def reject_ludo(oid: int, db: Session = Depends(get_db)):
    o = db.query(LudoOrder).get(oid)
    if not o or o.status != "pending":
        raise HTTPException(404, "not found or not pending")
    o.status = "rejected"
    db.add(o); db.add(Notice(title="رفض طلب لودو", body="تم رفض طلبك.", for_owner=False, uid=o.uid))
    db.commit(); return {"ok": True}

# ---------- إدارة المستخدمين ----------
@r.get("/users/count", dependencies=[Depends(guard)])
def users_count(db: Session = Depends(get_db)):
    return {"ok": True, "count": db.query(User).count()}

@r.get("/users/balances", dependencies=[Depends(guard)])
def users_balances(db: Session = Depends(get_db)):
    lst = db.query(User).order_by(User.balance.desc()).limit(500).all()
    return {"ok": True, "list": [{"uid": u.uid, "balance": u.balance, "is_banned": u.is_banned} for u in lst]}

@r.post("/users/{uid}/topup", dependencies=[Depends(guard)])
def user_topup(uid: str, amount: float, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u: raise HTTPException(404, "not found")
    u.balance = round(u.balance + amount, 2); db.add(u)
    db.add(Notice(title="تم إضافة رصيد", body=f"+${amount}", for_owner=False, uid=uid))
    db.commit(); return {"ok": True, "balance": u.balance}

@r.post("/users/{uid}/deduct", dependencies=[Depends(guard)])
def user_deduct(uid: str, amount: float, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u: raise HTTPException(404, "not found")
    u.balance = max(0.0, round(u.balance - amount, 2)); db.add(u)
    db.add(Notice(title="تم خصم رصيد", body=f"-${amount}", for_owner=False, uid=uid))
    db.commit(); return {"ok": True, "balance": u.balance}

@r.post("/users/{uid}/ban", dependencies=[Depends(guard)])
def ban(uid: str, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u: raise HTTPException(404, "not found")
    u.is_banned = True; db.add(u); db.commit(); return {"ok": True}

@r.post("/users/{uid}/unban", dependencies=[Depends(guard)])
def unban(uid: str, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(uid=uid).first()
    if not u: raise HTTPException(404, "not found")
    u.is_banned = False; db.add(u); db.commit(); return {"ok": True}

# ---------- إشعارات (إرسال يدوي) ----------
import httpx
@r.post("/notify/push", dependencies=[Depends(guard)])
def push_notify(title: str = "تنبيه", body: str = "رسالة", target: str = "allUsers", db: Session = Depends(get_db)):
    key = settings.FCM_SERVER_KEY
    if not key: raise HTTPException(400, "FCM_SERVER_KEY not set")
    if target == "owners":
        tokens = [t.token for t in db.query(Token).filter_by(for_owner=True).all()]
    elif target.startswith("uid:"):
        uid = target.split(":",1)[1]
        tokens = [t.token for t in db.query(Token).filter_by(uid=uid).all()]
    else:
        tokens = [t.token for t in db.query(Token).filter_by(for_owner=False).all()]
    ok=0; fail=0
    for tk in tokens:
        try:
            httpx.post(
                "https://fcm.googleapis.com/fcm/send",
                json={"to": tk, "notification": {"title": title, "body": body}},
                headers={"Authorization": f"key={key}", "Content-Type":"application/json"},
                timeout=8.0
            )
            ok += 1
        except Exception:
            fail += 1
    return {"ok": True, "sent": ok, "failed": fail}

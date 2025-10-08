from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..config import settings
from ..models import Order, CardSubmission, ItunesOrder, PubgOrder, LudoOrder, User
from ..providers.smm_client import SMMClient

router = APIRouter(prefix="/api/admin", tags=["admin"])

def admin_guard(x_admin_pass: str = Header(None, convert_underscores=False)):
    if not x_admin_pass or x_admin_pass != settings.ADMIN_PASS:
        raise HTTPException(status_code=401, detail="unauthorized")
    return True

# ---- قوائم المعلّق ----
@router.get("/pending/services")
def pending_services(_: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.kind=="provider", Order.status=="Pending").all()
    return {"list": [
        {"id": o.id, "uid": o.uid, "quantity": o.quantity, "price": o.price,
         "service_key": o.title, "link": o.payload}
        for o in q
    ]}

@router.post("/pending/services/{oid}/approve")
def approve_service(oid: str, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o: raise HTTPException(404, "not found")
    o.status = "Processing"   # أو Done حسب رغبتك
    db.commit()
    return {"ok": True}

@router.post("/pending/services/{oid}/reject")
def reject_service(oid: str, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    o = db.get(Order, oid)
    if not o: raise HTTPException(404, "not found")
    o.status = "Rejected"
    db.commit()
    return {"ok": True}

@router.get("/pending/cards")
def pending_cards(_: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    q = db.query(CardSubmission).filter(CardSubmission.status=="Pending").all()
    return {"list": [{"id": c.id, "uid": c.uid, "card_number": c.card_number} for c in q]}

@router.post("/pending/cards/{cid}/accept")
def accept_card(cid: int, payload: dict, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    c = db.get(CardSubmission, cid)
    if not c: raise HTTPException(404, "not found")
    c.status = "Accepted"
    amount = float(payload.get("amount_usd", 0))
    u = db.query(User).filter(User.uid==c.uid).first()
    if u:
        u.balance = (u.balance or 0.0) + amount
    db.commit()
    return {"ok": True}

@router.post("/pending/cards/{cid}/reject")
def reject_card(cid: int, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    c = db.get(CardSubmission, cid)
    if not c: raise HTTPException(404, "not found")
    c.status = "Rejected"
    db.commit()
    return {"ok": True}

@router.get("/pending/itunes")
def pending_itunes(_: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    q = db.query(ItunesOrder).filter(ItunesOrder.status=="Pending").all()
    return {"list": [{"id": i.id, "uid": i.uid, "amount": i.amount} for i in q]}

@router.post("/pending/itunes/{iid}/deliver")
def deliver_itunes(iid: int, payload: dict, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    i = db.get(ItunesOrder, iid)
    if not i: raise HTTPException(404, "not found")
    i.gift_code = str(payload.get("gift_code", "")).strip()
    i.status = "Done"
    db.commit()
    return {"ok": True}

@router.post("/pending/itunes/{iid}/reject")
def reject_itunes(iid: int, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    i = db.get(ItunesOrder, iid)
    if not i: raise HTTPException(404, "not found")
    i.status = "Rejected"
    db.commit()
    return {"ok": True}

@router.get("/pending/pubg")
def pending_pubg(_: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    q = db.query(PubgOrder).filter(PubgOrder.status=="Pending").all()
    return {"list": [{"id": p.id, "uid": p.uid, "pkg": p.pkg, "pubg_id": p.pubg_id} for p in q]}

@router.post("/pending/pubg/{pid}/deliver")
def deliver_pubg(pid: int, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    p = db.get(PubgOrder, pid)
    if not p: raise HTTPException(404, "not found")
    p.status = "Done"
    db.commit()
    return {"ok": True}

@router.post("/pending/pubg/{pid}/reject")
def reject_pubg(pid: int, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    p = db.get(PubgOrder, pid)
    if not p: raise HTTPException(404, "not found")
    p.status = "Rejected"
    db.commit()
    return {"ok": True}

@router.get("/pending/ludo")
def pending_ludo(_: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    q = db.query(LudoOrder).filter(LudoOrder.status=="Pending").all()
    return {"list": [{"id": l.id, "uid": l.uid, "kind": l.kind, "pack": l.pack, "ludo_id": l.ludo_id} for l in q]}

@router.post("/pending/ludo/{lid}/deliver")
def deliver_ludo(lid: int, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    l = db.get(LudoOrder, lid)
    if not l: raise HTTPException(404, "not found")
    l.status = "Done"
    db.commit()
    return {"ok": True}

@router.post("/pending/ludo/{lid}/reject")
def reject_ludo(lid: int, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    l = db.get(LudoOrder, lid)
    if not l: raise HTTPException(404, "not found")
    l.status = "Rejected"
    db.commit()
    return {"ok": True}

# ---- المستخدمون: عدد/أرصدة + شحن/خصم ----
@router.get("/users/count")
def users_count(_: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    return {"count": db.query(User).count()}

@router.get("/users/balances")
def users_balances(_: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    users = db.query(User).all()
    return {"list": [{"uid": u.uid, "balance": u.balance or 0.0, "is_banned": bool(u.is_banned)} for u in users]}

@router.post("/users/{uid}/topup")
def users_topup(uid: str, payload: dict, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.uid == uid).first()
    if not u: raise HTTPException(404, "not found")
    amt = float(payload.get("amount", 0))
    u.balance = (u.balance or 0.0) + amt
    db.commit()
    return {"ok": True, "balance": u.balance}

@router.post("/users/{uid}/deduct")
def users_deduct(uid: str, payload: dict, _: bool = Depends(admin_guard), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.uid == uid).first()
    if not u: raise HTTPException(404, "not found")
    amt = float(payload.get("amount", 0))
    u.balance = (u.balance or 0.0) - amt
    db.commit()
    return {"ok": True, "balance": u.balance}

@router.get("/provider/balance")
async def provider_balance(_: bool = Depends(admin_guard)):
    try:
        res = await SMMClient().balance()
        # كثير من لوحات SMM ترجع {"balance":"123.45","currency":"USD"}
        bal = float(res.get("balance", 0))
    except Exception:
        bal = 0.0
    return {"balance": bal}

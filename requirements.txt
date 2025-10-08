# app/routers/admin.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import text
from ..database import engine
import os, requests, decimal

r = APIRouter(prefix="/api/admin", tags=["admin"])

# ========= إعدادات =========
ADMIN_PASS = os.getenv("ADMIN_PASS", "2000")
KD1S_API_URL = os.getenv("KD1S_API_URL", "https://kd1s.com/api/v2")
KD1S_API_KEY = os.getenv("KD1S_API_KEY", "")

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_admin(req: Request):
    token = req.headers.get("x-admin-pass")
    if token != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="unauthorized")
    return True

def to_float(x):
    if isinstance(x, decimal.Decimal):
        return float(x)
    return x

# ========= نماذج طلب =========
class AmountIn(BaseModel):
    amount: float

class CardAcceptIn(BaseModel):
    amount_usd: float
    reviewed_by: Optional[str] = "owner"

class ItunesDeliverIn(BaseModel):
    gift_code: str

# ========= تكامل KD1S =========
def kd1s_add_order(service_code: int, link: str, quantity: int) -> Dict[str, Any]:
    """
    يرجع {'ok': True, 'order': <id>} أو {'ok': False, 'error': '...'}
    """
    if not KD1S_API_KEY:
        return {"ok": False, "error": "KD1S_API_KEY not configured"}

    data = {
        "key": KD1S_API_KEY,
        "action": "add",
        "service": service_code,
        "link": link,
        "quantity": quantity
    }
    try:
        res = requests.post(KD1S_API_URL, data=data, timeout=30)
        j = res.json()
        # صيغ شائعة: {"order":123456} أو {"error":"..."}
        if "order" in j:
            return {"ok": True, "order": j["order"]}
        return {"ok": False, "error": j.get("error", "unknown error")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def kd1s_balance() -> Dict[str, Any]:
    if not KD1S_API_KEY:
        return {"ok": False, "error": "KD1S_API_KEY not configured"}
    data = {"key": KD1S_API_KEY, "action": "balance"}
    try:
        res = requests.post(KD1S_API_URL, data=data, timeout=20)
        j = res.json()
        # صيغ شائعة: {"balance":"123.45"} أو {"remains":...}
        bal = j.get("balance") or j.get("funds") or j.get("remains")
        if bal is None:
            return {"ok": False, "error": "no balance field", "raw": j}
        try:
            return {"ok": True, "balance": float(bal)}
        except:
            return {"ok": True, "balance": bal}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ========= المعلّقات: خدمات (orders.status='pending') =========
@r.get("/pending/services")
def get_pending_services(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    q = text("""
        SELECT id, uid, service_key, service_code, link, quantity, price
        FROM orders
        WHERE status = 'pending'
        ORDER BY id DESC
        LIMIT 200
    """)
    rows = db.execute(q).mappings().all()
    lst = []
    for row in rows:
        lst.append({
            "id": str(row["id"]),
            "uid": row["uid"],
            "service_key": row["service_key"],
            "service_code": int(row["service_code"]) if row["service_code"] is not None else None,
            "link": row["link"],
            "quantity": int(row["quantity"]) if row["quantity"] is not None else 0,
            "price": to_float(row["price"]) if row["price"] is not None else 0.0,
        })
    return {"ok": True, "list": lst}

@r.post("/pending/services/{order_id}/approve")
def approve_service(order_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    # اجلب الطلب
    row = db.execute(text("SELECT * FROM orders WHERE id=:id"), {"id": order_id}).mappings().first()
    if not row:
        raise HTTPException(404, "order not found")
    if row["status"] != "pending":
        raise HTTPException(400, "invalid status")

    # تحقق رصيد المستخدم (خصم عند الموافقة)
    user = db.execute(text("SELECT * FROM users WHERE uid=:u FOR UPDATE"), {"u": row["uid"]}).mappings().first()
    if not user:
        raise HTTPException(400, "user not found")
    price = float(row["price"] or 0)
    if (user["balance"] or 0) < price:
        raise HTTPException(400, "insufficient balance")

    # استدعِ KD1S
    svc = int(row["service_code"] or 0)
    if svc <= 0:
        raise HTTPException(400, "invalid service_code")
    kd = kd1s_add_order(svc, row["link"], int(row["quantity"] or 0))
    if not kd.get("ok"):
        raise HTTPException(502, f"kd1s error: {kd.get('error')}")

    provider_order_id = str(kd["order"])

    # حدّث الرصيد وحالة الطلب
    with db.begin():
        db.execute(
            text("UPDATE users SET balance = balance - :p WHERE uid=:u"),
            {"p": price, "u": row["uid"]}
        )
        db.execute(
            text("UPDATE orders SET status='processing', payload=:pl WHERE id=:id"),
            {"pl": provider_order_id, "id": order_id}
        )
    return {"ok": True, "provider_order": provider_order_id}

@r.post("/pending/services/{order_id}/reject")
def reject_service(order_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    exists = db.execute(text("SELECT 1 FROM orders WHERE id=:id"), {"id": order_id}).first()
    if not exists:
        raise HTTPException(404, "order not found")
    db.execute(text("UPDATE orders SET status='rejected' WHERE id=:id"), {"id": order_id})
    db.commit()
    return {"ok": True}

# ========= الكارتات المعلّقة =========
@r.get("/pending/cards")
def pending_cards(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    q = text("""
        SELECT id, uid, card_number, status, created_at
        FROM topup_cards
        WHERE status='pending'
        ORDER BY id DESC
        LIMIT 200
    """)
    rows = db.execute(q).mappings().all()
    lst = []
    for row in rows:
        lst.append({
            "id": row["id"],
            "uid": row["uid"],
            "card_number": row["card_number"],
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        })
    return {"ok": True, "list": lst}

@r.post("/pending/cards/{card_id}/accept")
def accept_card(card_id: int, body: CardAcceptIn, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    card = db.execute(text("SELECT * FROM topup_cards WHERE id=:id FOR UPDATE"), {"id": card_id}).mappings().first()
    if not card:
        raise HTTPException(404, "card not found")
    if card["status"] != "pending":
        raise HTTPException(400, "invalid status")

    uid = card["uid"]
    amount = float(body.amount_usd)

    with db.begin():
        # أضف الرصيد للعميل
        db.execute(text("""
            INSERT INTO users (uid, balance) VALUES (:u, :a)
            ON CONFLICT (uid) DO UPDATE SET balance = users.balance + EXCLUDED.balance
        """), {"u": uid, "a": amount})
        # حدّث حالة الكارت
        db.execute(text("""
            UPDATE topup_cards SET status='accepted', reviewed_by=:rv
            WHERE id=:id
        """), {"rv": body.reviewed_by or "owner", "id": card_id})

        # اختياري: سجل عملية في orders (كإشعار)
        db.execute(text("""
            INSERT INTO orders(uid, service_key, service_code, link, quantity, price, status, payload)
            VALUES (:u, 'شحن رصيد (أسيا سيل)', NULL, NULL, 0, :a, 'done', :p)
        """), {"u": uid, "a": amount, "p": f"topup_card:{card_id}"})

    return {"ok": True}

@r.post("/pending/cards/{card_id}/reject")
def reject_card(card_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    exists = db.execute(text("SELECT 1 FROM topup_cards WHERE id=:id"), {"id": card_id}).first()
    if not exists:
        raise HTTPException(404, "card not found")
    db.execute(text("UPDATE topup_cards SET status='rejected' WHERE id=:id"), {"id": card_id})
    db.commit()
    return {"ok": True}

# ========= ايتونز =========
@r.get("/pending/itunes")
def pending_itunes(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    q = text("""
        SELECT id, uid, amount, status, created_at
        FROM itunes_requests
        WHERE status='pending'
        ORDER BY id DESC
        LIMIT 200
    """)
    rows = db.execute(q).mappings().all()
    lst = []
    for row in rows:
        lst.append({
            "id": row["id"],
            "uid": row["uid"],
            "amount": to_float(row["amount"]),
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        })
    return {"ok": True, "list": lst}

@r.post("/pending/itunes/{req_id}/deliver")
def itunes_deliver(req_id: int, body: ItunesDeliverIn, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    req = db.execute(text("SELECT * FROM itunes_requests WHERE id=:id"), {"id": req_id}).mappings().first()
    if not req:
        raise HTTPException(404, "request not found")
    if req["status"] != "pending":
        raise HTTPException(400, "invalid status")

    with db.begin():
        db.execute(text("""
            UPDATE itunes_requests SET status='done', gift_code=:c WHERE id=:id
        """), {"c": body.gift_code, "id": req_id})
        # إشعار في orders (اختياري)
        db.execute(text("""
            INSERT INTO orders(uid, service_key, service_code, link, quantity, price, status, payload)
            VALUES (:u, 'شحن ايتونز', NULL, NULL, 1, :a, 'done', :p)
        """), {"u": req["uid"], "a": float(req["amount"] or 0), "p": f"itunes:{req_id}"})
    return {"ok": True}

@r.post("/pending/itunes/{req_id}/reject")
def itunes_reject(req_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    db.execute(text("UPDATE itunes_requests SET status='rejected' WHERE id=:id"), {"id": req_id})
    db.commit()
    return {"ok": True}

# ========= ببجي =========
@r.get("/pending/pubg")
def pending_pubg(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    q = text("""
        SELECT id, uid, amount, status, created_at, payload
        FROM pubg_requests
        WHERE status='pending'
        ORDER BY id DESC
        LIMIT 200
    """)
    rows = db.execute(q).mappings().all()
    lst = []
    for row in rows:
        lst.append({
            "id": row["id"],
            "uid": row["uid"],
            "amount": int(row["amount"] or 0),
            "status": row["status"],
            "payload": row["payload"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        })
    return {"ok": True, "list": lst}

@r.post("/pending/pubg/{req_id}/deliver")
def pubg_deliver(req_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    db.execute(text("UPDATE pubg_requests SET status='done' WHERE id=:id"), {"id": req_id})
    db.commit()
    return {"ok": True}

@r.post("/pending/pubg/{req_id}/reject")
def pubg_reject(req_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    db.execute(text("UPDATE pubg_requests SET status='rejected' WHERE id=:id"), {"id": req_id})
    db.commit()
    return {"ok": True}

# ========= لودو =========
@r.get("/pending/ludo")
def pending_ludo(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    q = text("""
        SELECT id, uid, amount, status, created_at, payload
        FROM ludo_requests
        WHERE status='pending'
        ORDER BY id DESC
        LIMIT 200
    """)
    rows = db.execute(q).mappings().all()
    lst = []
    for row in rows:
        lst.append({
            "id": row["id"],
            "uid": row["uid"],
            "amount": int(row["amount"] or 0),
            "status": row["status"],
            "payload": row["payload"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        })
    return {"ok": True, "list": lst}

@r.post("/pending/ludo/{req_id}/deliver")
def ludo_deliver(req_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    db.execute(text("UPDATE ludo_requests SET status='done' WHERE id=:id"), {"id": req_id})
    db.commit()
    return {"ok": True}

@r.post("/pending/ludo/{req_id}/reject")
def ludo_reject(req_id: int, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    db.execute(text("UPDATE ludo_requests SET status='rejected' WHERE id=:id"), {"id": req_id})
    db.commit()
    return {"ok": True}

# ========= الرصيد (تعبئة/خصم) =========
@r.post("/users/{uid}/topup")
def user_topup(uid: str, body: AmountIn, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    with db.begin():
        db.execute(text("""
            INSERT INTO users (uid, balance) VALUES (:u, :a)
            ON CONFLICT (uid) DO UPDATE SET balance = users.balance + EXCLUDED.balance
        """), {"u": uid, "a": float(body.amount)})
    return {"ok": True}

@r.post("/users/{uid}/deduct")
def user_deduct(uid: str, body: AmountIn, _: bool = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.execute(text("SELECT balance FROM users WHERE uid=:u FOR UPDATE"), {"u": uid}).first()
    if not row:
        raise HTTPException(404, "user not found")
    bal = float(row[0] or 0)
    if bal < body.amount:
        raise HTTPException(400, "insufficient balance")
    with db.begin():
        db.execute(text("UPDATE users SET balance = balance - :a WHERE uid=:u"),
                   {"a": float(body.amount), "u": uid})
    return {"ok": True}

# ========= إحصاءات =========
@r.get("/users/count")
def users_count(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
    return {"ok": True, "count": int(c)}

@r.get("/users/balances")
def users_balances(_: bool = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT uid, balance FROM users ORDER BY balance DESC")).mappings().all()
    lst = [{"uid": r["uid"], "balance": to_float(r["balance"])} for r in rows]
    return {"ok": True, "list": lst}

# ========= رصيد المزود =========
@r.get("/provider/balance")
def provider_balance(_: bool = Depends(require_admin)):
    kb = kd1s_balance()
    if not kb.get("ok"):
        raise HTTPException(502, kb.get("error", "provider error"))
    return {"ok": True, "balance": kb["balance"]}

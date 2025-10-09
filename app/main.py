import os
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, conint, confloat
from sqlalchemy import (
    create_engine, text
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
import httpx

# -----------------------------
# إعدادات
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/smm")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2000")

PROVIDER_API_URL = os.getenv("PROVIDER_API_URL", "https://kd1s.com/api/v2")
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "25a9ceb07be0d8b2ba88e70dcbe92e06")

app = FastAPI(title="Ratlwzan API (single file)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# -----------------------------
# قاعدة البيانات + إنشاء الجداول
# -----------------------------
engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True)

DDL = """
CREATE TABLE IF NOT EXISTS users(
  uid TEXT PRIMARY KEY,
  balance NUMERIC(18,2) NOT NULL DEFAULT 0.00,
  is_banned BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders(
  id BIGSERIAL PRIMARY KEY,
  uid TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
  title TEXT NOT NULL,
  service_id BIGINT,
  link TEXT,
  quantity INTEGER,
  price NUMERIC(18,2) NOT NULL DEFAULT 0.00,
  kind TEXT NOT NULL,              -- provider | manual | topup_card
  status TEXT NOT NULL DEFAULT 'Pending',   -- Pending/Processing/Done/Rejected/Refunded
  payload JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- فهارس خفيفة
CREATE INDEX IF NOT EXISTS idx_orders_uid ON orders(uid);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
"""

with engine.begin() as conn:
    for stmt in DDL.strip().split(";\n\n"):
        if stmt.strip():
            conn.exec_driver_sql(stmt)

# -----------------------------
# نماذج الطلب/الرد
# -----------------------------
class UpsertUser(BaseModel):
    uid: str

class WalletChange(BaseModel):
    uid: str
    amount: confloat(gt=0)

class ProviderOrderCreate(BaseModel):
    uid: str
    service_id: conint(gt=0)
    service_name: str = Field(..., alias="service_name")
    link: str
    quantity: conint(gt=0)
    price: confloat(gt=0)

class ManualOrderCreate(BaseModel):
    uid: str
    title: str

class AsiacellCard(BaseModel):
    uid: str
    card: str

def require_admin(x_admin_password: Optional[str] = Header(None, convert_underscores=False)):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="unauthorized (admin password)")
    return True

# -----------------------------
# مسارات عامة للمستخدم
# -----------------------------
@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}

@app.post("/api/users/upsert")
def upsert_user(body: UpsertUser):
    with engine.begin() as con:
        con.exec_driver_sql(
            "INSERT INTO users(uid) VALUES (:u) ON CONFLICT (uid) DO NOTHING",
            {"u": body.uid}
        )
    return {"ok": True}

@app.get("/api/wallet/balance")
def wallet_balance(uid: str = Query(...)):
    with engine.begin() as con:
        row = con.exec_driver_sql("SELECT balance FROM users WHERE uid=:u", {"u": uid}).first()
        if not row:
            return {"balance": 0.0}
        return {"balance": float(row[0])}

@app.post("/api/orders/create/provider")
def create_provider_order(body: ProviderOrderCreate):
    """يضيف طلب مزود ‘Pending’ ويخصم الرصيد مباشرة إن كان كافيًا.
       إن لم يكن الرصيد كافيًا يُنشئه (Pending) بدون خصم ويظهر لدى المالك للمراجعة.
       التطبيق يعتبر الطلب ناجحًا إذا وجد {"ok": true}."""
    with engine.begin() as con:
        # تأكد من وجود المستخدم
        con.exec_driver_sql(
            "INSERT INTO users(uid) VALUES(:u) ON CONFLICT (uid) DO NOTHING",
            {"u": body.uid}
        )
        # اجلب الرصيد
        row = con.exec_driver_sql("SELECT balance FROM users WHERE uid=:u", {"u": body.uid}).first()
        balance = float(row[0]) if row else 0.0

        will_deduct = balance >= float(body.price)
        # أنشئ الطلب
        payload = {
            "service_id": body.service_id,
            "link": body.link,
            "quantity": int(body.quantity),
            "auto_deduct": will_deduct
        }
        ins = con.exec_driver_sql(
            """
            INSERT INTO orders(uid,title,service_id,link,quantity,price,kind,status,payload)
            VALUES(:uid,:title,:sid,:link,:qty,:price,'provider','Pending',:payload)
            RETURNING id
            """,
            {
                "uid": body.uid,
                "title": body.service_name,
                "sid": int(body.service_id),
                "link": body.link,
                "qty": int(body.quantity),
                "price": float(body.price),
                "payload": payload
            }
        ).first()
        oid = int(ins[0])

        # خصم فوري إن أمكن
        if will_deduct:
            con.exec_driver_sql("UPDATE users SET balance = balance - :p WHERE uid=:u",
                                {"p": float(body.price), "u": body.uid})

    return {"ok": True, "order_id": oid, "auto_deduct": will_deduct}

@app.post("/api/orders/create/manual")
def create_manual_order(body: ManualOrderCreate):
    with engine.begin() as con:
        con.exec_driver_sql(
            "INSERT INTO users(uid) VALUES(:u) ON CONFLICT (uid) DO NOTHING",
            {"u": body.uid}
        )
        con.exec_driver_sql(
            """
            INSERT INTO orders(uid,title,price,kind,status)
            VALUES(:uid,:title,0,'manual','Pending')
            """,
            {"uid": body.uid, "title": body.title}
        )
    return {"ok": True}

@app.get("/api/orders/my")
def my_orders(uid: str):
    with engine.begin() as con:
        rows = con.exec_driver_sql(
            """
            SELECT id,title,quantity,price,status,created_at
            FROM orders
            WHERE uid=:u
            ORDER BY id DESC
            """, {"u": uid}
        ).all()
        out = []
        for r in rows:
            out.append({
                "id": str(r[0]),
                "title": r[1],
                "quantity": int(r[2] or 0),
                "price": float(r[3] or 0),
                "status": r[4],
                "created_at": r[5].isoformat()
            })
        return {"orders": out}

@app.post("/api/wallet/asiacell/submit")
def asiacell_submit(body: AsiacellCard):
    """يسجل الكارت كطلب ‘topup_card’ معلق يظهر للمالك"""
    card = body.card.strip()
    if not card.isdigit() or len(card) not in (14, 16):
        raise HTTPException(status_code=400, detail="invalid card format")

    with engine.begin() as con:
        con.exec_driver_sql(
            "INSERT INTO users(uid) VALUES(:u) ON CONFLICT (uid) DO NOTHING",
            {"u": body.uid}
        )
        payload = {"card": card, "provider": "asiacell"}
        con.exec_driver_sql(
            """
            INSERT INTO orders(uid,title,price,kind,status,payload)
            VALUES(:uid,:title,0,'topup_card','Pending',:payload)
            """,
            {"uid": body.uid, "title": "شحن عبر أسيا سيل (كارت)", "payload": payload}
        )
    return {"ok": True, "status": "received"}

# -----------------------------
# مسارات الأدمن
# -----------------------------
@app.get("/api/admin/users/count")
def admin_users_count(_: bool = Depends(require_admin)):
    with engine.begin() as con:
        row = con.exec_driver_sql("SELECT COUNT(*) FROM users").first()
        return {"count": int(row[0])}

@app.get("/api/admin/users/balances")
def admin_users_balances(_: bool = Depends(require_admin)):
    with engine.begin() as con:
        rows = con.exec_driver_sql(
            "SELECT uid,is_banned,balance FROM users ORDER BY uid ASC"
        ).all()
        return [{"uid": r[0], "is_banned": bool(r[1]), "balance": float(r[2])} for r in rows]

@app.post("/api/admin/wallet/topup")
def admin_topup(body: WalletChange, _: bool = Depends(require_admin)):
    with engine.begin() as con:
        con.exec_driver_sql("INSERT INTO users(uid) VALUES(:u) ON CONFLICT (uid) DO NOTHING", {"u": body.uid})
        con.exec_driver_sql("UPDATE users SET balance = balance + :a WHERE uid=:u", {"a": float(body.amount), "u": body.uid})
    return {"ok": True}

@app.post("/api/admin/wallet/deduct")
def admin_deduct(body: WalletChange, _: bool = Depends(require_admin)):
    with engine.begin() as con:
        con.exec_driver_sql("UPDATE users SET balance = GREATEST(balance - :a,0) WHERE uid=:u", {"a": float(body.amount), "u": body.uid})
    return {"ok": True}

@app.get("/api/admin/pending/services")
def admin_pending_services(_: bool = Depends(require_admin)):
    with engine.begin() as con:
        rows = con.exec_driver_sql(
            "SELECT id,title,quantity,price,link,payload FROM orders WHERE kind='provider' AND status='Pending' ORDER BY id ASC"
        ).all()
        out = []
        for r in rows:
            link = None
            if isinstance(r[5], dict):
                link = r[5].get("link")
            out.append({
                "id": int(r[0]),
                "title": r[1],
                "quantity": int(r[2] or 0),
                "price": float(r[3] or 0),
                "link": r[4] or link
            })
        return out

@app.get("/api/admin/pending/itunes")
def admin_pending_itunes(_: bool = Depends(require_admin)):
    with engine.begin() as con:
        rows = con.exec_driver_sql(
            "SELECT id,title FROM orders WHERE kind='manual' AND status='Pending' AND title ILIKE '%ايتونز%' ORDER BY id ASC"
        ).all()
        return [{"id": int(r[0]), "title": r[1]} for r in rows]

@app.get("/api/admin/pending/pubg")
def admin_pending_pubg(_: bool = Depends(require_admin)):
    with engine.begin() as con:
        rows = con.exec_driver_sql(
            "SELECT id,title FROM orders WHERE kind='manual' AND status='Pending' AND title ILIKE '%ببجي%' ORDER BY id ASC"
        ).all()
        return [{"id": int(r[0]), "title": r[1]} for r in rows]

@app.get("/api/admin/pending/ludo")
def admin_pending_ludo(_: bool = Depends(require_admin)):
    with engine.begin() as con:
        rows = con.exec_driver_sql(
            "SELECT id,title FROM orders WHERE kind='manual' AND status='Pending' AND title ILIKE '%ودو%' ORDER BY id ASC"
        ).all()
        return [{"id": int(r[0]), "title": r[1]} for r in rows]

@app.post("/api/admin/orders/{order_id}/approve")
def admin_order_approve(order_id: int, _: bool = Depends(require_admin)):
    """عند الموافقة:
       - إذا كان الطلب provider ويحتوي auto_deduct=False سنخصم الرصيد الآن إن كان كافيًا
       - (اختياري) يمكن استدعاء مزود KD1S هنا لإنشاء الطلب الحقيقي
    """
    with engine.begin() as con:
        row = con.exec_driver_sql("SELECT uid,price,kind,payload FROM orders WHERE id=:i FOR UPDATE", {"i": order_id}).first()
        if not row:
            raise HTTPException(status_code=404, detail="order not found")
        uid, price, kind, payload = row[0], float(row[1] or 0), row[2], row[3] or {}

        if kind == "provider":
            # حاول الخصم إذا لم يُخصم
            auto = bool(payload.get("auto_deduct", False)) if isinstance(payload, dict) else False
            if not auto:
                bal = con.exec_driver_sql("SELECT balance FROM users WHERE uid=:u", {"u": uid}).first()
                bal = float(bal[0] or 0)
                if bal < price:
                    raise HTTPException(status_code=400, detail="insufficient balance")
                con.exec_driver_sql("UPDATE users SET balance=balance-:p WHERE uid=:u", {"p": price, "u": uid})

            # (اختياري) إرسال للمزوّد الحقيقي KD1S
            try:
                if isinstance(payload, dict):
                    _sid = str(payload.get("service_id") or payload.get("service") or payload.get("sid") or "")
                    _link = str(payload.get("link") or "")
                    _qty = str(payload.get("quantity") or "0")
                    if _sid and _link and _qty != "0":
                        with httpx.Client(timeout=15) as client:
                            res = client.post(
                                PROVIDER_API_URL,
                                data={"key": PROVIDER_API_KEY, "action": "add", "service": _sid, "link": _link, "quantity": _qty}
                            )
                            # لا نفشل الطلب لو رد المزوّد خطأ؛ فقط نحفظ الرد للإطلاع
                            con.exec_driver_sql("UPDATE orders SET payload = COALESCE(payload,'{}'::jsonb) || :p::jsonb WHERE id=:i",
                                                {"p": {"provider_response": res.text[:500]}, "i": order_id})
            except Exception:
                pass

        con.exec_driver_sql("UPDATE orders SET status='Done' WHERE id=:i", {"i": order_id})
    return {"ok": True}

@app.post("/api/admin/orders/{order_id}/deliver")
def admin_order_deliver(order_id: int, _: bool = Depends(require_admin)):
    with engine.begin() as con:
        con.exec_driver_sql("UPDATE orders SET status='Rejected' WHERE id=:i", {"i": order_id})
    return {"ok": True}

@app.get("/api/admin/provider/balance")
def admin_provider_balance(_: bool = Depends(require_admin)):
    try:
        with httpx.Client(timeout=15) as client:
            r = client.post(PROVIDER_API_URL, data={"key": PROVIDER_API_KEY, "action": "balance"})
            txt = r.text.strip()
            try:
                # KD1S يرد JSON فيه balance
                import json
                j = json.loads(txt)
                if "balance" in j:
                    return float(j["balance"])
                if "data" in j and "balance" in j["data"]:
                    return float(j["data"]["balance"])
            except Exception:
                pass
            # في حال نص فقط
            if txt.replace(".", "", 1).isdigit():
                return float(txt)
            return {"balance_raw": txt}
    except Exception:
        raise HTTPException(status_code=502, detail="provider unreachable")

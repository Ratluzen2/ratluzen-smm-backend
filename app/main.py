# main.py
import os, json, time, logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests
import psycopg2
from psycopg2 import pool
from psycopg2.extras import Json

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ------------------ إعدادات ------------------
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_NEON")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is required")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2000")

PROVIDER_API_URL = os.getenv("PROVIDER_API_URL", "https://kd1s.com/api/v2")
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "25a9ceb07be0d8b2ba88e70dcbe92e06")

POOL_MIN, POOL_MAX = 1, int(os.getenv("DB_POOL_MAX", "5"))
dbpool: pool.SimpleConnectionPool = pool.SimpleConnectionPool(POOL_MIN, POOL_MAX, dsn=DATABASE_URL)

def get_conn(): return dbpool.getconn()
def put_conn(conn): dbpool.putconn(conn)

# ------------------ لوجينغ بسيط ------------------
logger = logging.getLogger("smm")
logging.basicConfig(level=logging.INFO)

# ------------------ إنشاء الجداول ------------------
def ensure_schema():
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
            CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
            CREATE SCHEMA IF NOT EXISTS public;

            CREATE TABLE IF NOT EXISTS public.users(
                id         SERIAL PRIMARY KEY,
                uid        TEXT UNIQUE NOT NULL,
                balance    NUMERIC(18,4) NOT NULL DEFAULT 0,
                is_banned  BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS public.wallet_txns(
                id         SERIAL PRIMARY KEY,
                user_id    INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                amount     NUMERIC(18,4) NOT NULL,
                reason     TEXT,
                meta       JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS public.orders(
                id                 SERIAL PRIMARY KEY,
                user_id            INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                title              TEXT NOT NULL,
                service_id         BIGINT,
                link               TEXT,
                quantity           INTEGER NOT NULL DEFAULT 0,
                price              NUMERIC(18,4) NOT NULL DEFAULT 0,
                status             TEXT NOT NULL DEFAULT 'Pending',
                provider_order_id  TEXT,
                payload            JSONB,
                created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_users_uid ON public.users(uid);
            CREATE INDEX IF NOT EXISTS idx_orders_user ON public.orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON public.orders(status);
            """)
    finally:
        put_conn(conn)

ensure_schema()

# ------------------ FastAPI & CORS ------------------
app = FastAPI(title="SMM Backend", version="1.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    dt = int((time.time() - t0) * 1000)
    logger.info("%s %s -> %s (%d ms)", request.method, request.url.path, response.status_code, dt)
    return response

@app.get("/")
def root():
    return {"ok": True, "msg": "backend running"}

@app.get("/health")
def health():
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return {"ok": True, "ts": int(time.time()*1000)}
    finally:
        put_conn(conn)

# ------------------ نماذج أساسية ------------------
class UpsertUserIn(BaseModel):
    uid: str

class ProviderOrderIn(BaseModel):
    uid: str
    service_id: int
    service_name: str
    link: str
    quantity: int = Field(ge=1)
    price: float = Field(ge=0)

class ManualOrderIn(BaseModel):
    uid: str
    title: str

class WalletChangeIn(BaseModel):
    uid: str
    amount: float

class AsiacellSubmitIn(BaseModel):
    uid: str
    card: str

# ------------------ أدوات ------------------
def _ensure_user(cur, uid: str) -> int:
    cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
    r = cur.fetchone()
    if r: return r[0]
    cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (uid,))
    return cur.fetchone()[0]

def _user_id_and_balance(cur, uid: str):
    cur.execute("SELECT id, balance, is_banned FROM public.users WHERE uid=%s", (uid,))
    r = cur.fetchone()
    if not r: return None
    return r[0], float(r[1]), bool(r[2])

def _refund_if_needed(cur, user_id: int, price: float, order_id: int):
    if price and price > 0:
        cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (Decimal(price), user_id))
        cur.execute("""
            INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
            VALUES(%s,%s,%s,%s)
        """, (user_id, Decimal(price), "order_refund", Json({"order_id": order_id})))

def _row_to_order_dict(row) -> Dict[str, Any]:
    (oid, title, qty, price, status, created_at_ms, link) = row
    return {
        "id": oid, "title": title, "quantity": qty,
        "price": float(price or 0), "status": status,
        "created_at": int(created_at_ms or 0), "link": link
    }

def _is_admin(passwd: str) -> bool:
    return passwd == ADMIN_PASSWORD

async def _coerce_json(request: Request) -> Dict[str, Any]:
    ctype = (request.headers.get("content-type") or "").lower()
    try:
        if "application/json" in ctype:
            return await request.json()
        if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
            form = await request.form()
            return {k: (v if isinstance(v, str) else str(v)) for k, v in form.items()}
        # نص خام
        raw = (await request.body()).decode("utf-8", errors="ignore").strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            data = {}
            for part in raw.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    data[k] = v
            return data or {"raw": raw}
    except Exception:
        return {}

# ------------------ عام ------------------
@app.post("/api/users/upsert")
def upsert_user(body: UpsertUserIn):
    uid = (body.uid or "").strip()
    if not uid:
        raise HTTPException(422, "uid required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_user(cur, uid)
        return {"ok": True, "uid": uid}
    finally:
        put_conn(conn)

@app.get("/api/wallet/balance")
def wallet_balance(uid: str):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT balance FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
        return {"ok": True, "balance": float(r[0] if r else 0.0)}
    finally:
        put_conn(conn)

# --------- إنشاء طلب خدمة (جوهر) ---------
def _create_provider_order_core(cur, uid: str, service_id: Optional[int], service_name: str,
                                link: Optional[str], quantity: int, price: float) -> int:
    cur.execute("SELECT id, balance, is_banned FROM public.users WHERE uid=%s", (uid,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, "user not found")
    user_id, bal, banned = r[0], float(r[1]), bool(r[2])
    if banned:
        raise HTTPException(403, "user banned")

    # خصم الرصيد إن كان الطلب مدفوعًا
    if price and price > 0:
        if bal < price:
            raise HTTPException(400, "insufficient balance")
        cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (Decimal(price), user_id))
        cur.execute("""
            INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
            VALUES(%s,%s,%s,%s)
        """, (user_id, Decimal(-price), "order_charge",
              Json({"service_id": service_id, "name": service_name, "qty": quantity})))

    # إنشاء الطلب كمعلّق
    cur.execute("""
        INSERT INTO public.orders(user_id, title, service_id, link, quantity, price, status, payload)
        VALUES(%s,%s,%s,%s,%s,%s,'Pending',%s)
        RETURNING id
    """, (user_id, service_name, service_id, link, quantity, Decimal(price or 0),
          Json({"source": "provider_form"})))
    oid = cur.fetchone()[0]
    return oid

# نقاط دخول “رسمية”
@app.post("/api/orders/create/provider")
def create_provider_order(body: ProviderOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            oid = _create_provider_order_core(
                cur, body.uid, body.service_id, body.service_name,
                body.link, body.quantity, body.price
            )
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

# نقاط دخول توافقية متعددة للأندرويد
PROVIDER_CREATE_PATHS = [
    "/api/orders/create",
    "/api/order/create",
    "/api/orders/provider/create",
    "/api/create/order",
    "/api/orders/add",
    "/api/add_order",
]
def _parse_provider_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    uid = (data.get("uid") or data.get("user_id") or "").strip()
    # service / service_id / category_id
    sv = data.get("service_id", data.get("service", data.get("category_id")))
    service_id = int(sv) if (sv not in (None, "", [])) else None
    link = data.get("link") or data.get("url") or data.get("target") or None
    qty_raw = data.get("quantity", data.get("qty", data.get("amount", 0)))
    quantity = int(qty_raw or 0)
    price = float(data.get("price", data.get("cost", 0)) or 0)
    service_name = data.get("service_name") or data.get("name") or (f"Service {service_id}" if service_id else "Manual")
    return dict(uid=uid, service_id=service_id, link=link, quantity=quantity, price=price, service_name=service_name)

for path in PROVIDER_CREATE_PATHS:
    @app.post(path)
    async def provider_create_compat(request: Request, _path=path):
        data = await _coerce_json(request)
        try:
            p = _parse_provider_payload(data)
            if not p["uid"] or p["quantity"] <= 0:
                raise ValueError
        except Exception:
            raise HTTPException(422, "invalid payload")
        conn = get_conn()
        try:
            with conn, conn.cursor() as cur:
                oid = _create_provider_order_core(cur, p["uid"], p["service_id"], p["service_name"], p["link"], p["quantity"], p["price"])
            return {"ok": True, "order_id": oid}
        finally:
            put_conn(conn)

# طلب يدوي (إن رغبت)
@app.post("/api/orders/create/manual")
def create_manual_order(body: ManualOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            user_id = _ensure_user(cur, body.uid)
            cur.execute("""
                INSERT INTO public.orders(user_id, title, quantity, price, status)
                VALUES(%s,%s,0,0,'Pending') RETURNING id
            """, (user_id, body.title))
            oid = cur.fetchone()[0]
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

# --------- آسيا سيل ---------
def _asiacell_submit_core(cur, uid: str, card_digits: str) -> int:
    user_id = _ensure_user(cur, uid)
    cur.execute("""
        INSERT INTO public.orders(user_id, title, quantity, price, status, payload)
        VALUES(%s,%s,0,0,'Pending', %s)
        RETURNING id
    """, (user_id, "كارت أسيا سيل", Json({"card": card_digits})))
    return cur.fetchone()[0]

def _extract_card(raw: Any) -> str:
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return digits

ASIACELL_PATHS = [
    "/api/wallet/asiacell/submit",
    "/api/topup/asiacell/submit",
    "/api/asiacell/submit",
    "/api/asiacell/recharge",
    "/api/wallet/asiacell",
    "/api/topup/asiacell",
    "/api/asiacell",
]
@app.post("/api/wallet/asiacell/submit")  # المسار الأساسي
def submit_asiacell(body: AsiacellSubmitIn):
    digits = _extract_card(body.card)
    if len(digits) not in (14, 16):
        raise HTTPException(422, "invalid card length")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            oid = _asiacell_submit_core(cur, body.uid, digits)
        return {"ok": True, "order_id": oid, "status": "received"}
    finally:
        put_conn(conn)

# بقية المسارات التوافقية
for path in ASIACELL_PATHS[1:]:
    @app.post(path)
    async def submit_asiacell_compat(request: Request, _path=path):
        data = await _coerce_json(request)
        uid = (data.get("uid") or data.get("user_id") or "").strip()
        raw = (data.get("card") or data.get("code") or data.get("voucher") or
               data.get("number") or data.get("serial") or
               data.get("recharge_no") or data.get("recharge_number") or
               data.get("value") or data.get("pin") or "")
        digits = _extract_card(raw)
        if not uid or len(digits) not in (14, 16):
            raise HTTPException(422, "invalid payload")
        conn = get_conn()
        try:
            with conn, conn.cursor() as cur:
                oid = _asiacell_submit_core(cur, uid, digits)
            return {"ok": True, "order_id": oid, "status": "received"}
        finally:
            put_conn(conn)

# --------- أوامري ---------
def _orders_for_uid(uid: str) -> List[dict]:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                return []
            user_id = r[0]
            cur.execute("""
                SELECT id, title, quantity, price,
                       status, EXTRACT(EPOCH FROM created_at)*1000, link
                FROM public.orders
                WHERE user_id=%s
                ORDER BY id DESC
            """, (user_id,))
            rows = cur.fetchall()
        return [_row_to_order_dict(t) for t in rows]
    finally:
        put_conn(conn)

@app.get("/api/orders/my")
def my_orders(uid: str):
    return _orders_for_uid(uid)

@app.get("/api/orders")
def orders_alias(uid: str):
    return _orders_for_uid(uid)

@app.get("/api/user/orders")
def user_orders_alias(uid: str):
    return _orders_for_uid(uid)

@app.get("/api/users/{uid}/orders")
def user_orders_path(uid: str):
    return _orders_for_uid(uid)

# ------------------ أدمن ------------------
def _require_admin(x_admin_password: str):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(401, "bad admin password")

def _list_pending(where_sql: str = "", args: tuple = ()) -> List[dict]:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            base = """
                SELECT id, title, quantity, price, status, EXTRACT(EPOCH FROM created_at)*1000, link
                FROM public.orders
                WHERE status='Pending' {extra}
                ORDER BY id DESC
            """
            sql = base.format(extra=(" AND " + where_sql) if where_sql else "")
            cur.execute(sql, args)
            rows = cur.fetchall()
            return [_row_to_order_dict(t) for t in rows]
    finally:
        put_conn(conn)

@app.get("/api/admin/pending/services")
def admin_pending_services(x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password); return _list_pending()

@app.get("/api/admin/pending/itunes")
def admin_pending_itunes(x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password); return _list_pending("LOWER(title) LIKE %s", ("%itunes%",))

@app.get("/api/admin/pending/pubg")
def admin_pending_pubg(x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password); return _list_pending("LOWER(title) LIKE %s", ("%pubg%",))

@app.get("/api/admin/pending/ludo")
def admin_pending_ludo(x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password); return _list_pending("LOWER(title) LIKE %s", ("%ludo%",))

@app.post("/api/admin/orders/{oid}/approve")
def admin_approve_order(oid: int, x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, service_id, link, quantity, price, status, provider_order_id, title, payload
                FROM public.orders WHERE id=%s FOR UPDATE
            """, (oid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "order not found")

            (order_id, user_id, service_id, link, quantity, price, status, provider_order_id, title, payload) = row
            price = float(price or 0)

            if status not in ("Pending", "Processing"):
                raise HTTPException(400, "invalid status")

            # طلب يدوي
            if service_id is None:
                cur.execute("UPDATE public.orders SET status='Processing' WHERE id=%s", (order_id,))
                return {"ok": True, "status": "Processing"}

            # إرسال إلى KD1S
            try:
                resp = requests.post(PROVIDER_API_URL, data={
                    "key": PROVIDER_API_KEY,
                    "action": "add",
                    "service": str(service_id),
                    "link": link,
                    "quantity": str(quantity)
                }, timeout=25)
            except Exception:
                _refund_if_needed(cur, user_id, price, order_id)
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
                return {"ok": False, "status": "Rejected", "reason": "provider_unreachable"}

            if resp.status_code // 100 != 2:
                _refund_if_needed(cur, user_id, price, order_id)
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
                return {"ok": False, "status": "Rejected", "reason": "provider_http"}

            try:
                data = resp.json()
            except Exception:
                _refund_if_needed(cur, user_id, price, order_id)
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
                return {"ok": False, "status": "Rejected", "reason": "bad_provider_json"}

            provider_id = data.get("order") or data.get("order_id")
            if not provider_id:
                _refund_if_needed(cur, user_id, price, order_id)
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
                return {"ok": False, "status": "Rejected", "reason": "no_provider_id"}

            cur.execute("""
                UPDATE public.orders
                SET provider_order_id=%s, status='Processing'
                WHERE id=%s
            """, (str(provider_id), order_id))
            return {"ok": True, "status": "Processing", "provider_order_id": provider_id}
    finally:
        put_conn(conn)

@app.post("/api/admin/orders/{oid}/deliver")
def admin_deliver_reject(oid: int, x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, user_id, price, status FROM public.orders WHERE id=%s FOR UPDATE", (oid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "order not found")
            order_id, user_id, price, status = row[0], row[1], float(row[2] or 0), row[3]
            if status in ("Done", "Rejected", "Refunded"):
                return {"ok": True, "status": status}
            _refund_if_needed(cur, user_id, price, order_id)
            cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
            return {"ok": True, "status": "Rejected"}
    finally:
        put_conn(conn)

@app.post("/api/admin/wallet/topup")
def admin_wallet_topup(body: WalletChangeIn, x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    amount = float(body.amount)
    if amount <= 0: raise HTTPException(422, "amount must be > 0")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (Decimal(amount), user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s,%s,%s,%s)
            """, (user_id, Decimal(amount), "admin_topup", Json({"by": "admin"})))
        return {"ok": True}
    finally:
        put_conn(conn)

@app.post("/api/admin/wallet/deduct")
def admin_wallet_deduct(body: WalletChangeIn, x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    amount = float(body.amount)
    if amount <= 0: raise HTTPException(422, "amount must be > 0")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1] or 0)
            if bal < amount: raise HTTPException(400, "insufficient balance")
            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (Decimal(amount), user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s,%s,%s,%s)
            """, (user_id, Decimal(-amount), "admin_deduct", Json({"by": "admin"})))
        return {"ok": True}
    finally:
        put_conn(conn)

@app.get("/api/admin/users/count")
def admin_users_count(x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.users")
            n = cur.fetchone()[0]
        return {"ok": True, "count": int(n)}
    finally:
        put_conn(conn)

@app.get("/api/admin/users/balances")
def admin_users_balances(x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT uid, balance, is_banned FROM public.users ORDER BY id DESC LIMIT 1000")
            rows = cur.fetchall()
        return [{"uid": r[0], "balance": float(r[1] or 0), "is_banned": bool(r[2])} for r in rows]
    finally:
        put_conn(conn)

@app.get("/api/admin/provider/balance")
def admin_provider_balance(x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    try:
        resp = requests.post(PROVIDER_API_URL, data={"key": PROVIDER_API_KEY, "action": "balance"}, timeout=20)
        if resp.status_code // 100 != 2:
            raise HTTPException(502, "provider http error")
        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        bal = data.get("balance")
        if bal is None:
            try: bal = float(resp.text.strip())
            except Exception: raise HTTPException(502, "bad provider payload")
        return float(bal)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "provider unreachable")

# ------------------ تشغيل محلي ------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

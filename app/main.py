import os, json, time
from decimal import Decimal
from typing import Optional, List, Any, Dict

import requests
import psycopg2
from psycopg2 import pool
from psycopg2.extras import Json

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# =========================
# إعدادات عامة
# =========================
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_NEON")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is required")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2000")

PROVIDER_API_URL = os.getenv("PROVIDER_API_URL", "https://kd1s.com/api/v2")
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "25a9ceb07be0d8b2ba88e70dcbe92e06")  # ضع مفتاحك أو اتركه من ENV

# هيروكو يضع sslmode ضمن الـ URL عادةً. لا نعدّل السلسلة.
POOL_MIN, POOL_MAX = 1, int(os.getenv("DB_POOL_MAX", "5"))
dbpool: pool.SimpleConnectionPool = pool.SimpleConnectionPool(POOL_MIN, POOL_MAX, dsn=DATABASE_URL)

def get_conn():
    return dbpool.getconn()

def put_conn(conn):
    dbpool.putconn(conn)

# =========================
# إنشاء الجداول تلقائيًا
# =========================
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

# =========================
# FastAPI & CORS
# =========================
app = FastAPI(title="SMM Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

@app.get("/")
def root():
    return {"ok": True, "msg": "backend running"}

@app.get("/health")
def health():
    # اختبار اتصال مبسّط
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return {"ok": True, "ts": int(time.time()*1000)}
    finally:
        put_conn(conn)

# =========================
# نماذج
# =========================
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

# =========================
# أدوات مساعدة
# =========================
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
        cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (price, user_id))
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

# =========================
# واجهات عامة
# =========================
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

@app.post("/api/orders/create/provider")
def create_provider_order(body: ProviderOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance, is_banned FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id, bal, banned = r[0], float(r[1]), bool(r[2])
            if banned:
                raise HTTPException(403, "user banned")
            if bal < body.price:
                raise HTTPException(400, "insufficient balance")

            # خصم الرصيد وتسجيل الحركة
            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (Decimal(body.price), user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s,%s,%s,%s)
            """, (user_id, Decimal(-body.price), "order_charge",
                  Json({"service_id": body.service_id, "name": body.service_name, "qty": body.quantity})))

            # إنشاء الطلب
            cur.execute("""
                INSERT INTO public.orders(user_id, title, service_id, link, quantity, price, status, payload)
                VALUES(%s,%s,%s,%s,%s,%s,'Pending',%s)
                RETURNING id
            """, (user_id, body.service_name, body.service_id, body.link, body.quantity,
                  Decimal(body.price), Json({"source": "provider_form"})))
            oid = cur.fetchone()[0]
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

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

@app.post("/api/wallet/asiacell/submit")
def submit_asiacell(body: AsiacellSubmitIn):
    digits = "".join(ch for ch in body.card if ch.isdigit())
    if len(digits) not in (14, 16):
        raise HTTPException(422, "invalid card length")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            user_id = _ensure_user(cur, body.uid)
            # نجعلها طلب Pending بعنوان واضح لتظهر بقائمة المعلّقات
            cur.execute("""
                INSERT INTO public.orders(user_id, title, quantity, price, status, payload)
                VALUES(%s,%s,0,0,'Pending', %s)
                RETURNING id
            """, (user_id, "كارت أسيا سيل", Json({"card": digits})))
            oid = cur.fetchone()[0]
        return {"ok": True, "order_id": oid, "status": "received"}
    finally:
        put_conn(conn)

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

# بعض المسارات البديلة (حتى لا يظهر "تعذر جلب البيانات" بالتطبيق)
@app.get("/api/orders")
def orders_alias(uid: str):
    return _orders_for_uid(uid)

@app.get("/api/user/orders")
def user_orders_alias(uid: str):
    return _orders_for_uid(uid)

@app.get("/api/users/{uid}/orders")
def user_orders_path(uid: str):
    return _orders_for_uid(uid)

@app.get("/api/orders/list")
def orders_list(uid: str):
    return {"orders": _orders_for_uid(uid)}

@app.get("/api/user/orders/list")
def user_orders_list(uid: str):
    return {"orders": _orders_for_uid(uid)}

# =========================
# واجهات الأدمن
# =========================
def _require_admin(x_admin_password: str):
    if not _is_admin(x_admin_password):
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
    _require_admin(x_admin_password)
    # نرجع كل المعلّقات، والتطبيق يرشّح منها "الكروت المعلقة" إذا احتاج
    return _list_pending()

@app.get("/api/admin/pending/itunes")
def admin_pending_itunes(x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    return _list_pending("LOWER(title) LIKE %s", ("%itunes%",))

@app.get("/api/admin/pending/pubg")
def admin_pending_pubg(x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    return _list_pending("LOWER(title) LIKE %s", ("%pubg%",))

@app.get("/api/admin/pending/ludo")
def admin_pending_ludo(x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    return _list_pending("LOWER(title) LIKE %s", ("%ludo%",))

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

            # إن لم يكن طلب خدمات (service_id None)، نعتبره يدوي -> نغّير الحالة فقط
            if service_id is None:
                cur.execute("UPDATE public.orders SET status='Processing' WHERE id=%s", (order_id,))
                return {"ok": True, "status": "Processing"}

            # إرسال للمزوّد KD1S
            try:
                resp = requests.post(PROVIDER_API_URL, data={
                    "key": PROVIDER_API_KEY,
                    "action": "add",
                    "service": str(service_id),
                    "link": link,
                    "quantity": str(quantity)
                }, timeout=25)
            except Exception:
                # فشل تواصل مع المزود -> ردّ المبلغ ورفض
                _refund_if_needed(cur, user_id, price, order_id)
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
                return {"ok": False, "status": "Rejected", "reason": "provider_unreachable"}

            if resp.status_code // 100 != 2:
                _refund_if_needed(cur, user_id, price, order_id)
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
                return {"ok": False, "status": "Rejected", "reason": "provider_http"}

            # تحليل استجابة KD1S
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

            # نجاح
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
    """زر الرفض في التطبيق يرسل هنا (Deliver=رفض)."""
    _require_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, price, status
                FROM public.orders WHERE id=%s FOR UPDATE
            """, (oid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "order not found")

            order_id, user_id, price, status = row[0], row[1], float(row[2] or 0), row[3]
            if status in ("Done", "Rejected", "Refunded"):
                return {"ok": True, "status": status}

            # ردّ مبلغ الطلب
            _refund_if_needed(cur, user_id, price, order_id)
            cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
            return {"ok": True, "status": "Rejected"}
    finally:
        put_conn(conn)

@app.post("/api/admin/wallet/topup")
def admin_wallet_topup(body: WalletChangeIn, x_admin_password: str = Header(..., alias="x-admin-password")):
    _require_admin(x_admin_password)
    amount = float(body.amount)
    if amount <= 0:
        raise HTTPException(422, "amount must be > 0")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
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
    if amount <= 0:
        raise HTTPException(422, "amount must be > 0")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1] or 0)
            if bal < amount:
                raise HTTPException(400, "insufficient balance")
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
        out = [{"uid": r[0], "balance": float(r[1] or 0), "is_banned": bool(r[2])} for r in rows]
        return out
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
            # بعض المزودين يرجعون نصًا فقط
            try:
                bal = float(resp.text.strip())
            except Exception:
                raise HTTPException(502, "bad provider payload")
        return float(bal)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "provider unreachable")


# =============== تشغيل محلي ===============
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

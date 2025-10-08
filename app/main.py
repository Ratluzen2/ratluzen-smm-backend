# app/main.py
# -*- coding: utf-8 -*-
import os
from typing import List, Optional, Tuple

from fastapi import FastAPI, APIRouter, HTTPException, Header
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import Json

# =========================
# Config
# =========================
ADMIN_PASSWORD   = os.getenv("ADMIN_PASSWORD", "2000")
DATABASE_URL     = os.getenv("DATABASE_URL")     # postgresql://user:pass@host/db?sslmode=require
PROVIDER_BALANCE = float(os.getenv("PROVIDER_BALANCE", "0") or 0.0)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is required")

# =========================
# DB Pool
# =========================
_pool: Optional[SimpleConnectionPool] = None

def _ensure_pool():
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(minconn=1, maxconn=5, dsn=DATABASE_URL, sslmode="require")

def get_conn():
    _ensure_pool()
    assert _pool is not None
    return _pool.getconn()

def put_conn(conn):
    if conn and _pool:
        _pool.putconn(conn)

# =========================
# Auto-migrate: create/patch schema if needed
# =========================
SCHEMA_SQL = """
-- USERS
CREATE TABLE IF NOT EXISTS public.users(
    id         BIGSERIAL PRIMARY KEY,
    uid        TEXT UNIQUE NOT NULL,
    balance    NUMERIC(14,2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- WALLET_TXNS
CREATE TABLE IF NOT EXISTS public.wallet_txns(
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    amount     NUMERIC(14,2) NOT NULL,
    reason     TEXT,
    meta       JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ORDERS (قاعدتنا المطلوبة)
CREATE TABLE IF NOT EXISTS public.orders(
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    service_id INTEGER,
    link       TEXT,
    quantity   INTEGER NOT NULL DEFAULT 0,
    price      NUMERIC(14,2) NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'Pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ===== Patch existing orders table to match backend =====
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS service_id INTEGER;
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS link TEXT;
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS quantity INTEGER DEFAULT 0;
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS price NUMERIC(14,2) DEFAULT 0;
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Pending';
ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

-- اجعل الأعمدة الضرورية NOT NULL بأمان (بعد التأكد من وجودها)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='orders' AND column_name='title') THEN
    EXECUTE 'ALTER TABLE public.orders ALTER COLUMN title SET NOT NULL';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='orders' AND column_name='quantity') THEN
    EXECUTE 'ALTER TABLE public.orders ALTER COLUMN quantity SET NOT NULL';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='orders' AND column_name='price') THEN
    EXECUTE 'ALTER TABLE public.orders ALTER COLUMN price SET NOT NULL';
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='orders' AND column_name='status') THEN
    EXECUTE 'ALTER TABLE public.orders ALTER COLUMN status SET NOT NULL';
  END IF;
END$$;

-- أربط المفتاح الأجنبي بأمان
ALTER TABLE public.orders DROP CONSTRAINT IF EXISTS orders_user_id_fkey;
ALTER TABLE public.orders
  ADD CONSTRAINT orders_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- لو كان عندك عمود uid قديم في orders وجالس يسبب NOT NULL، خليه قابلًا للفراغ
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public' AND table_name='orders' AND column_name='uid'
  ) THEN
    BEGIN
      EXECUTE 'ALTER TABLE public.orders ALTER COLUMN uid DROP NOT NULL';
    EXCEPTION WHEN undefined_column THEN
      NULL;
    END;
  END IF;
END$$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_uid          ON public.users(uid);
CREATE INDEX IF NOT EXISTS idx_orders_user_id     ON public.orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status      ON public.orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at  ON public.orders(created_at);
"""

def ensure_schema():
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
    finally:
        put_conn(conn)

# =========================
# Models
# =========================
class UpsertUserIn(BaseModel):
    uid: str

class ProviderOrderIn(BaseModel):
    uid: str
    service_id: int
    service_name: str = Field(min_length=1)
    # نستخدم نص عادي بدل HttpUrl لأن بعض الروابط قد تكون معرفات (playerid:..., acc:...)
    link: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    price: float = Field(ge=0)

class ManualOrderIn(BaseModel):
    uid: str
    title: str = Field(min_length=1)

class WalletChangeIn(BaseModel):
    uid: str
    amount: float = Field(gt=0)

# =========================
# Helpers
# =========================
def _check_admin(p: Optional[str]):
    if not p or p != ADMIN_PASSWORD:
        raise HTTPException(401, "bad admin password")

def _orders_for_uid(uid: str) -> List[dict]:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                return []
            user_id = r[0]
            cur.execute(
                """
                SELECT id, title, quantity, price, status, EXTRACT(EPOCH FROM created_at)*1000
                FROM public.orders
                WHERE user_id=%s ORDER BY id DESC
                """,
                (user_id,)
            )
            rows = cur.fetchall()
        return [
            {"id": a, "title": b, "quantity": c, "price": float(d), "status": e, "created_at": int(f)}
            for (a, b, c, d, e, f) in rows
        ]
    finally:
        put_conn(conn)

def _pending_like(where_sql: str, params: Tuple) -> List[dict]:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT o.id, u.uid, o.title, o.quantity, o.price, o.status,
                       EXTRACT(EPOCH FROM o.created_at)*1000
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE o.status='Pending' AND {where_sql}
                ORDER BY o.id DESC
                """,
                params
            )
            rows = cur.fetchall()
        return [
            {"id": a, "uid": b, "title": c, "quantity": d, "price": float(e), "status": f, "created_at": int(g)}
            for (a, b, c, d, e, f, g) in rows
        ]
    finally:
        put_conn(conn)

# =========================
# FastAPI App
# =========================
app = FastAPI(
    title="Ratlwzan SMM Backend (single-file)",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Health + root alias
@app.get("/", include_in_schema=False)
def root_redirect():
    return RedirectResponse(url="/docs")

@app.get("/health", tags=["public"])
@app.get("/api/health", tags=["public"])
def health():
    return JSONResponse({"ok": True})

# أنشئ/صحّح الجداول عند الإقلاع
ensure_schema()

# --------- Public Router ---------
public = APIRouter(prefix="/api", tags=["public"])

@public.post("/users/upsert")
def upsert_user(body: UpsertUserIn):
    uid = body.uid.strip()
    if not uid:
        raise HTTPException(422, "uid required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM public.users WHERE uid=%s", (uid,))
            if not cur.fetchone():
                cur.execute("INSERT INTO public.users(uid) VALUES(%s)", (uid,))
        return {"ok": True, "uid": uid}
    finally:
        put_conn(conn)

@public.get("/wallet/balance")
def wallet_balance(uid: str):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT balance FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
        return {"ok": True, "balance": float(r[0] if r else 0.0)}
    finally:
        put_conn(conn)

@public.post("/orders/create/provider")
def create_provider_order(body: ProviderOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            # احصل على المستخدم والرصيد
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1])
            if bal < body.price:
                raise HTTPException(400, "insufficient balance")

            # خصم الرصيد + تسجيل الحركة
            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (body.price, user_id))
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason, meta) VALUES(%s,%s,%s,%s)",
                (user_id, -body.price, "order_charge",
                 Json({"service_id": body.service_id, "name": body.service_name, "qty": body.quantity, "link": body.link}))
            )

            # إنشاء الطلب
            cur.execute(
                """
                INSERT INTO public.orders(user_id, title, service_id, link, quantity, price, status)
                VALUES(%s,%s,%s,%s,%s,%s,'Pending') RETURNING id
                """,
                (user_id, body.service_name, body.service_id, body.link, body.quantity, body.price)
            )
            (oid,) = cur.fetchone()
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

@public.post("/orders/create/manual")
def create_manual_order(body: ManualOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = r[0]
            cur.execute(
                """
                INSERT INTO public.orders(user_id, title, quantity, price, status)
                VALUES(%s,%s,0,0,'Pending') RETURNING id
                """,
                (user_id, body.title)
            )
            (oid,) = cur.fetchone()
        return {"ok": True, "order_id": oid}
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
            cur.execute(
                """
                SELECT id, title, quantity, price, status, EXTRACT(EPOCH FROM created_at)*1000
                FROM public.orders
                WHERE user_id=%s ORDER BY id DESC
                """,
                (user_id,)
            )
            rows = cur.fetchall()
        return [
            {"id": a, "title": b, "quantity": c, "price": float(d), "status": e, "created_at": int(f)}
            for (a, b, c, d, e, f) in rows
        ]
    finally:
        put_conn(conn)

@public.get("/orders/my")
def my_orders(uid: str): return _orders_for_uid(uid)

@public.get("/orders")
def orders_alias(uid: str): return _orders_for_uid(uid)

@public.get("/user/orders")
def user_orders_alias(uid: str): return _orders_for_uid(uid)

@public.get("/users/{uid}/orders")
def user_orders_path(uid: str): return _orders_for_uid(uid)

@public.get("/orders/list")
def orders_list(uid: str): return {"orders": _orders_for_uid(uid)}

@public.get("/user/orders/list")
def user_orders_list(uid: str): return {"orders": _orders_for_uid(uid)}

# --------- Admin Router ---------
admin = APIRouter(prefix="/api/admin", tags=["admin"])

@admin.get("/ping")
def ping(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return {"ok": True}

@admin.get("/users/count")
def users_count(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.users")
            (c,) = cur.fetchone()
        return {"ok": True, "count": int(c)}
    finally:
        put_conn(conn)

@admin.get("/users/balances")
def users_balances(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT uid, balance FROM public.users ORDER BY id DESC")
            rows = cur.fetchall()
        return [{"uid": u, "balance": float(b)} for (u, b) in rows]
    finally:
        put_conn(conn)

class WalletChangeIn(BaseModel):
    uid: str
    amount: float = Field(gt=0)

@admin.post("/wallet/topup")
def topup_wallet(body: WalletChangeIn, x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (body.amount, user_id))
            cur.execute("INSERT INTO public.wallet_txns(user_id, amount, reason) VALUES(%s,%s,%s)",
                        (user_id, body.amount, "admin_topup"))
        return {"ok": True}
    finally:
        put_conn(conn)

@admin.post("/wallet/deduct")
def deduct_wallet(body: WalletChangeIn, x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1])
            if bal < body.amount: raise HTTPException(400, "insufficient balance")
            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (body.amount, user_id))
            cur.execute("INSERT INTO public.wallet_txns(user_id, amount, reason) VALUES(%s,%s,%s)",
                        (user_id, -body.amount, "admin_deduct"))
        return {"ok": True}
    finally:
        put_conn(conn)

@admin.get("/pending/services")
def pending_services(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return _pending_like("TRUE", tuple())

@admin.get("/pending/itunes")
def pending_itunes(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return _pending_like("o.title ILIKE %s", ("%itunes%",))

@admin.get("/pending/pubg")
def pending_pubg(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return _pending_like("o.title ILIKE %s", ("%pubg%",))

@admin.get("/pending/ludo")
def pending_ludo(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return _pending_like("o.title ILIKE %s", ("%ludo%",))

@admin.post("/orders/{order_id}/approve")
def approve_order(order_id: int, x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Approved' WHERE id=%s RETURNING 1", (order_id,))
            if not cur.fetchone(): raise HTTPException(404, "order not found")
        return {"ok": True}
    finally:
        put_conn(conn)

@admin.post("/orders/{order_id}/deliver")
def deliver_order(order_id: int, x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Delivered' WHERE id=%s RETURNING 1", (order_id,))
            if not cur.fetchone(): raise HTTPException(404, "order not found")
        return {"ok": True}
    finally:
        put_conn(conn)

@admin.get("/provider/balance")
def provider_balance(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return {"ok": True, "balance": float(PROVIDER_BALANCE)}

# ضمّ الراوترين
app.include_router(public)
app.include_router(admin)

# نقطة info سريعة
@app.get("/api")
def api_root(): return {"ok": True, "service": "ratlwzan-smm-backend-single-file"}

# تشغيل محلي (لا يؤثر على Heroku)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)

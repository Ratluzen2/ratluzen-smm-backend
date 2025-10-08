# -*- coding: utf-8 -*-
import os
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import Json

# =========================
# Config
# =========================
ADMIN_PASSWORD   = os.getenv("ADMIN_PASSWORD", "2000")
DATABASE_URL     = os.getenv("DATABASE_URL")     # postgres://... أو postgresql://...
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
        # Neon يتطلب sslmode=require عادةً
        _pool = SimpleConnectionPool(minconn=1, maxconn=5, dsn=DATABASE_URL, sslmode="require")

def get_conn():
    _ensure_pool()
    assert _pool is not None
    return _pool.getconn()

def put_conn(conn):
    if conn and _pool:
        _pool.putconn(conn)

# =========================
# Auto-migrate (create tables if not exist)
# =========================
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS public.users(
    id         SERIAL PRIMARY KEY,
    uid        TEXT UNIQUE NOT NULL,
    balance    NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.wallet_txns(
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    amount     NUMERIC NOT NULL,
    reason     TEXT,
    meta       JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.orders(
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    service_id INTEGER,
    link       TEXT,
    quantity   INTEGER NOT NULL DEFAULT 0,
    price      NUMERIC NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'Pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_uid      ON public.users(uid);
CREATE INDEX IF NOT EXISTS idx_orders_status  ON public.orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_title   ON public.orders(LOWER(title));
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
    link: HttpUrl
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

def _pending_like(where_sql: str, params: tuple):
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
app = FastAPI(title="Ratlwzan SMM Backend (single-file)", openapi_url="/api/openapi.json", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# أنشئ الجداول عند الإقلاع
ensure_schema()

# Routers (public + admin) داخل نفس الملف
public = APIRouter(prefix="/api", tags=["public"])
admin  = APIRouter(prefix="/api/admin", tags=["admin"])

# --------- Public routes ---------
@public.get("/health")
def health(): return {"ok": True}

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
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1])
            if bal < body.price: raise HTTPException(400, "insufficient balance")

            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (body.price, user_id))
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason, meta) VALUES(%s,%s,%s,%s)",
                (user_id, -body.price, "order_charge",
                 Json({"service_id": body.service_id, "name": body.service_name, "qty": body.quantity}))
            )
            cur.execute(
                """
                INSERT INTO public.orders(user_id, title, service_id, link, quantity, price, status)
                VALUES(%s,%s,%s,%s,%s,%s,'Pending') RETURNING id
                """,
                (user_id, body.service_name, body.service_id, str(body.link), body.quantity, body.price)
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
            if not r: raise HTTPException(404, "user not found")
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

# --------- Admin routes ---------
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
            return [{"uid": u, "balance": float(b)} for (u, b) in cur.fetchall()]
    finally:
        put_conn(conn)

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

# رصيد المزوّد (API balance check)
@admin.get("/provider/balance")
def provider_balance(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return {"ok": True, "balance": float(PROVIDER_BALANCE)}

# ضمّ الراوترين
app.include_router(public)
app.include_router(admin)

# نقطة صحة أخرى جذرية
@app.get("/api")
def api_root(): return {"ok": True, "service": "ratlwzan-smm-backend"}

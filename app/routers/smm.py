# app/main.py
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import os, json, re

from .db import get_conn, put_conn

ADMIN_PASS = os.getenv("ADMIN_PASS", "2000")

app = FastAPI(title="Ratluzen SMM Backend", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- تهيئة الجداول تلقائياً عند الإقلاع --------
DDL_SQL = """
CREATE TABLE IF NOT EXISTS public.users (
    id         SERIAL PRIMARY KEY,
    uid        TEXT UNIQUE NOT NULL,
    balance    NUMERIC(14,2) NOT NULL DEFAULT 0.00,
    is_banned  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.wallet_txns (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    amount     NUMERIC(14,2) NOT NULL,
    reason     TEXT NOT NULL,
    meta       JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.orders (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    service_id BIGINT,
    link       TEXT,
    quantity   INTEGER NOT NULL DEFAULT 0,
    price      NUMERIC(14,2) NOT NULL DEFAULT 0.00,
    payload    JSONB NOT NULL DEFAULT '{}',
    status     TEXT NOT NULL DEFAULT 'Pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.asiacell_cards (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    card_number TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'Pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

@app.on_event("startup")
def ensure_schema():
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(DDL_SQL)
    finally:
        put_conn(conn)

# -------- Health --------
@app.get("/health")
def health():
    # اختبار سريع لاتصال قاعدة البيانات
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return {"ok": True}
    finally:
        put_conn(conn)

# ========================
# Users / Wallet
# ========================
class UpsertUserIn(BaseModel):
    uid: str

@app.post("/api/users/upsert")
def upsert_user(body: UpsertUserIn):
    uid = body.uid.strip()
    if not uid:
        raise HTTPException(422, "uid required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            row = cur.fetchone()
            if row:
                return {"ok": True, "uid": uid}
            cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (uid,))
            cur.fetchone()
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
            bal = r[0] if r else 0.0
        return {"ok": True, "balance": float(bal)}
    finally:
        put_conn(conn)

# ========================
# Orders (Provider + Manual)
# ========================
class ProviderOrderIn(BaseModel):
    uid: str
    service_id: int
    service_name: str
    link: str
    quantity: int = Field(ge=1)
    price: float = Field(ge=0)

def _get_user_id_and_balance(cur, uid: str):
    cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (uid,))
    row = cur.fetchone()
    if not row:
        # في حال لم يُسجل التطبيق الـ UID لأي سبب، ننشئه تلقائيًا
        cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id, balance", (uid,))
        row = cur.fetchone()
    return int(row[0]), float(row[1])

# المسار الأساسي الذي يستدعيه التطبيق
@app.post("/api/orders/create/provider")
def create_provider_order(body: ProviderOrderIn):
    """
    يُرجع دائمًا JSON يحتوي ok=true عند النجاح (التطبيق يبحث عن وجود 'ok' بنجاح).
    """
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            user_id, balance = _get_user_id_and_balance(cur, body.uid)
            # التحقق من الرصيد
            if balance < float(body.price):
                raise HTTPException(400, detail="insufficient balance")

            # خصم المبلغ
            cur.execute(
                "UPDATE public.users SET balance = balance - %s WHERE id=%s",
                (body.price, user_id)
            )
            # تسجيل حركة محفظة
            cur.execute(
                """
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s, %s, %s, %s)
                """,
                (user_id, -float(body.price), "order_charge",
                 json.dumps({"service_id": body.service_id,
                             "service_name": body.service_name,
                             "qty": body.quantity}))
            )
            # إنشاء الطلب
            cur.execute(
                """
                INSERT INTO public.orders(user_id, title, service_id, link, quantity, price, payload, status)
                VALUES(%s,%s,%s,%s,%s,%s,%s,'Pending')
                RETURNING id
                """,
                (user_id, body.service_name, body.service_id, body.link, body.quantity, body.price, json.dumps({}))
            )
            oid = cur.fetchone()[0]

        # (اختياري) استدعاء مزوّد خارجي هنا ثم تحديث الحالة لاحقًا
        return {"ok": True, "order_id": int(oid)}
    finally:
        put_conn(conn)

# مسار بديل احتياطي إن كان التطبيق لديك يضرب هذا المسار القديم
@app.post("/api/orders/create")
def create_provider_order_alias(body: ProviderOrderIn):
    return create_provider_order(body)

class ManualOrderIn(BaseModel):
    uid: str
    title: str

@app.post("/api/orders/create/manual")
def create_manual_order(body: ManualOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                # إنشاء المستخدم تلقائياً
                cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (body.uid,))
                r = cur.fetchone()
            user_id = r[0]
            cur.execute("""
                INSERT INTO public.orders(user_id, title, quantity, price, status)
                VALUES(%s,%s,0,0,'Pending') RETURNING id
            """, (user_id, body.title))
            oid = cur.fetchone()[0]
        return {"ok": True, "order_id": int(oid)}
    finally:
        put_conn(conn)

@app.get("/api/orders/my")
def my_orders(uid: str):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                return []
            user_id = r[0]
            cur.execute("""
                SELECT id, title, quantity, price, status, EXTRACT(EPOCH FROM created_at)*1000
                FROM public.orders WHERE user_id=%s ORDER BY id DESC
            """, (user_id,))
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "title": row[1],
                    "quantity": row[2],
                    "price": float(row[3]),
                    "status": row[4],
                    "created_at": int(row[5])
                }
                for row in rows
            ]
    finally:
        put_conn(conn)

# ========================
# Asiacell cards
# ========================
class AsiacellCardIn(BaseModel):
    uid: str
    card: str

_card_re = re.compile(r"^\d{14}$|^\d{16}$")

@app.post("/api/wallet/asiacell/submit")
def submit_asiacell_card(body: AsiacellCardIn):
    card = body.card.strip()
    if not _card_re.fullmatch(card):
        raise HTTPException(422, "invalid card")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (body.uid,))
                r = cur.fetchone()
            user_id = r[0]
            cur.execute("""
                INSERT INTO public.asiacell_cards(user_id, card_number, status)
                VALUES(%s,%s,'Pending') RETURNING id
            """, (user_id, card))
            cid = cur.fetchone()[0]
        return {"ok": True, "card_id": int(cid)}
    finally:
        put_conn(conn)

# ========================
# Admin (ترويسة X-Admin-Pass)
# ========================
def _admin_token(header: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
                 low_header: Optional[str] = Header(default=None, alias="x-admin-pass")) -> str:
    return (header or low_header or "")

def _require_admin(tok: str):
    if tok != ADMIN_PASS:
        raise HTTPException(401, "unauthorized")

class WalletOpIn(BaseModel):
    uid: str
    amount: float

@app.post("/api/admin/wallet/topup")
def admin_topup(body: WalletOpIn, x_admin: str = Depends(_admin_token)):
    _require_admin(x_admin)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (body.uid,))
                r = cur.fetchone()
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance = balance + %s WHERE id=%s", (body.amount, user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s, %s, %s, %s)
            """, (user_id, float(body.amount), "admin_topup", json.dumps({})))
            cur.execute("SELECT balance FROM public.users WHERE id=%s", (user_id,))
            bal = float(cur.fetchone()[0])
        return {"ok": True, "balance": bal}
    finally:
        put_conn(conn)

@app.post("/api/admin/wallet/deduct")
def admin_deduct(body: WalletOpIn, x_admin: str = Depends(_admin_token)):
    _require_admin(x_admin)
    if body.amount <= 0:
        raise HTTPException(400, "amount must be positive")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1])
            if bal < body.amount:
                raise HTTPException(400, "insufficient balance")
            cur.execute("UPDATE public.users SET balance = balance - %s WHERE id=%s", (body.amount, user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s, %s, %s, %s)
            """, (user_id, -float(body.amount), "admin_deduct", json.dumps({})))
            cur.execute("SELECT balance FROM public.users WHERE id=%s", (user_id,))
            nb = float(cur.fetchone()[0])
        return {"ok": True, "balance": nb}
    finally:
        put_conn(conn)

@app.get("/api/admin/pending/services")
def pending_services(x_admin: str = Depends(_admin_token)):
    _require_admin(x_admin)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT o.id, u.uid, o.title, o.quantity, o.price, o.status, EXTRACT(EPOCH FROM o.created_at)*1000
                FROM public.orders o JOIN public.users u ON u.id=o.user_id
                WHERE o.service_id IS NOT NULL AND o.status='Pending'
                ORDER BY o.id DESC
            """)
            rows = cur.fetchall()
            return [
                {"id": r[0], "title": r[2], "quantity": r[3], "price": float(r[4]),
                 "payload": f"UID={r[1]}", "status": r[5], "created_at": int(r[6])}
                for r in rows
            ]
    finally:
        put_conn(conn)

@app.get("/api/admin/pending/topups")
def pending_topups(x_admin: str = Depends(_admin_token)):
    _require_admin(x_admin)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, u.uid, c.card_number, EXTRACT(EPOCH FROM c.created_at)*1000
                FROM public.asiacell_cards c JOIN public.users u ON u.id=c.user_id
                WHERE c.status='Pending'
                ORDER BY c.id DESC
            """)
            rows = cur.fetchall()
            return [
                {"id": r[0], "title": "كارت أسيا سيل", "quantity": 0, "price": 0.0,
                 "payload": f"UID={r[1]} CARD={r[2]}", "status": "Pending", "created_at": int(r[3])}
                for r in rows
            ]
    finally:
        put_conn(conn)

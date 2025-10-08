from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional
from psycopg2.extras import Json
from ..db import get_conn, put_conn

router = APIRouter(prefix="/api", tags=["public"])

# ---------- Models ----------
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

# ---------- Users ----------
@router.post("/users/upsert")
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

# ---------- Wallet ----------
@router.get("/wallet/balance")
def wallet_balance(uid: str):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT balance FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
        return {"ok": True, "balance": float(r[0] if r else 0.0)}
    finally:
        put_conn(conn)

# ---------- Orders ----------
@router.post("/orders/create/provider")
def create_provider_order(body: ProviderOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1])
            if bal < body.price:
                raise HTTPException(400, "insufficient balance")

            # خصم الرصيد وتسجيل حركة
            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (body.price, user_id))
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason, meta) VALUES(%s,%s,%s,%s)",
                (user_id, -body.price, "order_charge",
                 Json({"service_id": body.service_id, "name": body.service_name, "qty": body.quantity}))
            )
            # إنشاء الطلب
            cur.execute(
                """
                INSERT INTO public.orders(user_id, title, service_id, link, quantity, price, status)
                VALUES(%s,%s,%s,%s,%s,%s,'Pending') RETURNING id
                """,
                (user_id, body.service_name, body.service_id, str(body.link), body.quantity, body.price)
            )
            oid = cur.fetchone()[0]
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

@router.post("/orders/create/manual")
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
            oid = cur.fetchone()[0]
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

# ---- Helpers ----
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

# ---- List endpoints (+ aliases) ----
@router.get("/orders/my")
def my_orders(uid: str):
    return _orders_for_uid(uid)

@router.get("/orders")
def orders_alias(uid: str):
    return _orders_for_uid(uid)

@router.get("/user/orders")
def user_orders_alias(uid: str):
    return _orders_for_uid(uid)

@router.get("/users/{uid}/orders")
def user_orders_path(uid: str):
    return _orders_for_uid(uid)

# Returns {"orders": [...]}
@router.get("/orders/list")
def orders_list(uid: str):
    return {"orders": _orders_for_uid(uid)}

@router.get("/user/orders/list")
def user_orders_list(uid: str):
    return {"orders": _orders_for_uid(uid)}

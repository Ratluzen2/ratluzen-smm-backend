# app/routers/admin.py
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from psycopg2.extras import Json
from ..db import get_conn, put_conn

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ---------- Helpers ----------
def _check_admin(x_admin_password: Optional[str]) -> None:
    import os
    want = os.getenv("ADMIN_PASSWORD", "")
    if not want or x_admin_password != want:
        raise HTTPException(status_code=401, detail="bad admin password")

# ---------- Schemas ----------
class WalletOp(BaseModel):
    uid: str = Field(..., description="User UID like U123456")
    amount: float = Field(..., gt=0, description="Positive amount")

class OrderIdIn(BaseModel):
    order_id: int

# ---------- Health / Ping ----------
@router.get("/ping")
def admin_ping(x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    return {"ok": True}

# ---------- Users ----------
@router.get("/users/count")
def users_count(x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.users")
            n = cur.fetchone()[0]
        return {"ok": True, "count": int(n)}
    finally:
        put_conn(conn)

@router.get("/users/balances")
def users_balances(x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT uid, COALESCE(balance,0) FROM public.users ORDER BY id DESC LIMIT 500")
            rows = cur.fetchall()
        return {"ok": True, "users": [{"uid": u, "balance": float(b)} for (u, b) in rows]}
    finally:
        put_conn(conn)

# ---------- Wallet ops ----------
@router.post("/wallet/topup")
def wallet_topup(body: WalletOp, x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance = COALESCE(balance,0) + %s WHERE id=%s",
                        (body.amount, user_id))
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason, meta) VALUES (%s,%s,%s,%s)",
                (user_id, body.amount, "admin_topup", Json({"by": "owner"}))
            )
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/wallet/deduct")
def wallet_deduct(body: WalletOp, x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, COALESCE(balance,0) FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1])
            if bal < body.amount:
                raise HTTPException(400, "insufficient balance")
            cur.execute("UPDATE public.users SET balance = balance - %s WHERE id=%s",
                        (body.amount, user_id))
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason, meta) VALUES (%s,%s,%s,%s)",
                (user_id, -body.amount, "admin_deduct", Json({"by": "owner"}))
            )
        return {"ok": True}
    finally:
        put_conn(conn)

# ---------- Provider balance (dummy-safe) ----------
@router.get("/provider/balance")
def provider_balance(x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    # يمكن لاحقاً ربط مزوّد حقيقي. الآن نرجع 0 إذا لم يُضبط
    import os, requests
    url = os.getenv("KD1S_API_URL", "").rstrip("/")
    key = os.getenv("KD1S_API_KEY", "")
    if url and key:
        try:
            r = requests.post(f"{url}/balance", data={"key": key}, timeout=10)
            data = r.json()
            bal = float(data.get("balance", 0))
            return {"ok": True, "balance": bal}
        except Exception:
            return {"ok": True, "balance": 0.0}
    return {"ok": True, "balance": 0.0}

# ---------- Pending Orders ----------
def _pending(kind: str):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            if kind == "services":
                cur.execute("""SELECT id, title, quantity, price, status
                               FROM public.orders
                               WHERE status='Pending' ORDER BY id DESC LIMIT 200""")
            elif kind == "pubg":
                cur.execute("""SELECT id, title, quantity, price, status
                               FROM public.orders
                               WHERE status='Pending' AND title ILIKE '%pubg%' ORDER BY id DESC LIMIT 200""")
            elif kind == "ludo":
                cur.execute("""SELECT id, title, quantity, price, status
                               FROM public.orders
                               WHERE status='Pending' AND title ILIKE '%ludo%' ORDER BY id DESC LIMIT 200""")
            rows = cur.fetchall()
        return [{"id": i, "title": t, "quantity": q, "price": float(p), "status": s} for (i,t,q,p,s) in rows]
    finally:
        put_conn(conn)

@router.get("/pending/services")
def pending_services(x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    return {"ok": True, "orders": _pending("services")}

@router.get("/pending/pubg")
def pending_pubg(x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    return {"ok": True, "orders": _pending("pubg")}

@router.get("/pending/ludo")
def pending_ludo(x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    return {"ok": True, "orders": _pending("ludo")}

# ---------- Approve / Deliver ----------
@router.post("/orders/approve")
def orders_approve(body: OrderIdIn, x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Processing' WHERE id=%s RETURNING id", (body.order_id,))
            if not cur.fetchone():
                raise HTTPException(404, "order not found")
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/orders/deliver")
def orders_deliver(body: OrderIdIn, x_admin_password: Optional[str] = Header(None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Completed' WHERE id=%s RETURNING id", (body.order_id,))
            if not cur.fetchone():
                raise HTTPException(404, "order not found")
        return {"ok": True}
    finally:
        put_conn(conn)

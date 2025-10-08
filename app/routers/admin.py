import os
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from ..db import get_conn, put_conn

router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2000")

def _check_admin(x_admin_password: Optional[str]):
    if not x_admin_password or x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="bad admin password")

# ======= Schemas =======
class WalletChangeIn(BaseModel):
    uid: str
    amount: float = Field(gt=0)

# ======= Basic =======
@router.get("/ping")
def ping(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return {"ok": True}

@router.get("/users/count")
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

@router.get("/users/balances")
def users_balances(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT uid, balance FROM public.users ORDER BY id DESC")
            rows = cur.fetchall()
        return [{"uid": r[0], "balance": float(r[1])} for r in rows]
    finally:
        put_conn(conn)

# ======= Wallet Ops =======
@router.post("/wallet/topup")
def topup_wallet(body: WalletChangeIn, x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance = balance + %s WHERE id=%s", (body.amount, user_id))
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason) VALUES(%s,%s,%s)",
                (user_id, body.amount, "admin_topup")
            )
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/wallet/deduct")
def deduct_wallet(body: WalletChangeIn, x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
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
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason) VALUES(%s,%s,%s)",
                (user_id, -body.amount, "admin_deduct")
            )
        return {"ok": True}
    finally:
        put_conn(conn)

# ======= Pending Lists (الخدمات/ايتونز/ببجي/لودو) =======
def _pending_like(pattern: str):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT o.id, u.uid, o.title, o.quantity, o.price, o.status, EXTRACT(EPOCH FROM o.created_at)*1000
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE o.status='Pending' AND o.title ILIKE %s
                ORDER BY o.id DESC
                """,
                (pattern,)
            )
            rows = cur.fetchall()
        return [
            {"id": a, "uid": b, "title": c, "quantity": d, "price": float(e), "status": f, "created_at": int(g)}
            for (a, b, c, d, e, f, g) in rows
        ]
    finally:
        put_conn(conn)

@router.get("/pending/services")
def pending_services(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return _pending_like("%")

@router.get("/pending/itunes")
def pending_itunes(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return _pending_like("%itunes%")

@router.get("/pending/pubg")
def pending_pubg(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return _pending_like("%pubg%")

@router.get("/pending/ludo")
def pending_ludo(x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    return _pending_like("%ludo%")

# ======= Orders admin actions (approve / deliver) =======
@router.post("/orders/{order_id}/approve")
def approve_order(order_id: int, x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Approved' WHERE id=%s RETURNING 1", (order_id,))
            if not cur.fetchone():
                raise HTTPException(404, "order not found")
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/orders/{order_id}/deliver")
def deliver_order(order_id: int, x_admin_password: Optional[str] = Header(default=None)):
    _check_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Delivered' WHERE id=%s RETURNING 1", (order_id,))
            if not cur.fetchone():
                raise HTTPException(404, "order not found")
        return {"ok": True}
    finally:
        put_conn(conn)

# ======= Provider/API Balance check (stub) =======
@router.get("/provider/balance")
def provider_balance(x_admin_password: Optional[str] = Header(default=None)):
    """
    زر 'فحص رصيد API' — يُرجع قيمة ثابتة من ENV أو 0.0
    غيّر PROVIDER_BALANCE في المتغيّرات البيئية إن أردت.
    """
    _check_admin(x_admin_password)
    import os
    bal = float(os.getenv("PROVIDER_BALANCE", "0") or 0)
    return {"ok": True, "balance": bal}

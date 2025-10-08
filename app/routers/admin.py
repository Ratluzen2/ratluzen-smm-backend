# app/routers/admin.py
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional, List
from ..db import get_conn, put_conn

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ======== Auth (Header) ========
def verify_admin(x_admin_password: Optional[str] = Header(None)) -> None:
    # غيّر كلمة السر من متغير البيئة ADMIN_PASSWORD داخل هيروكو
    import os
    if not x_admin_password or x_admin_password != os.getenv("ADMIN_PASSWORD", ""):
        raise HTTPException(401, "bad admin password")

# ======== Utilities ========
def _orders_where(where_sql: str, params: tuple) -> List[dict]:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT o.id,
                       u.uid,
                       o.title,
                       COALESCE(o.service_id, 0) AS service_id,
                       o.link,
                       o.quantity,
                       o.price,
                       o.status,
                       EXTRACT(EPOCH FROM o.created_at)*1000 AS created_ms
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE {where_sql}
                ORDER BY o.id DESC
                """,
                params,
            )
            rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "uid": r[1],
                "title": r[2],
                "service_id": int(r[3]) if r[3] is not None else 0,
                "link": r[4],
                "quantity": r[5],
                "price": float(r[6]),
                "status": r[7],
                "created_at": int(r[8]),
            }
            for r in rows
        ]
    finally:
        put_conn(conn)

# ======== Ping / Basic ========
@router.get("/ping")
def admin_ping(_: None = Depends(verify_admin)):
    return {"ok": True}

@router.get("/users/count")
def users_count(_: None = Depends(verify_admin)):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.users")
            c = cur.fetchone()[0]
        return {"ok": True, "count": int(c)}
    finally:
        put_conn(conn)

# ======== Wallet Ops ========
class WalletOpIn(BaseModel):
    uid: str
    amount: float = Field(gt=0)

@router.post("/wallet/topup")
def wallet_topup(body: WalletOpIn, _: None = Depends(verify_admin)):
    uid = body.uid.strip()
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (body.amount, user_id))
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason) VALUES(%s,%s,%s)",
                (user_id, body.amount, "admin_topup"),
            )
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/wallet/deduct")
def wallet_deduct(body: WalletOpIn, _: None = Depends(verify_admin)):
    uid = body.uid.strip()
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1])
            if bal < body.amount:
                raise HTTPException(400, "insufficient balance")
            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (body.amount, user_id))
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason) VALUES(%s,%s,%s)",
                (user_id, -body.amount, "admin_deduct"),
            )
        return {"ok": True}
    finally:
        put_conn(conn)

# ======== Pending Orders (NEW) ========
# خدمات المزود (لديها service_id)
@router.get("/pending/services")
def pending_services(_: None = Depends(verify_admin)):
    return _orders_where("o.status='Pending' AND o.service_id IS NOT NULL", ())

# آيتونز
@router.get("/pending/itunes")
def pending_itunes(_: None = Depends(verify_admin)):
    # نبحث في العنوان عن كلمات آيتونز بالإنجليزية أو العربية
    return _orders_where(
        "o.status='Pending' AND (LOWER(o.title) LIKE %s OR o.title ILIKE %s)",
        ("%itunes%", "%ايتونز%"),
    )

# PUBG
@router.get("/pending/pubg")
def pending_pubg(_: None = Depends(verify_admin)):
    return _orders_where(
        "o.status='Pending' AND (LOWER(o.title) LIKE %s OR o.title ILIKE %s)",
        ("%pubg%", "%شدات%"),
    )

# Ludo
@router.get("/pending/ludo")
def pending_ludo(_: None = Depends(verify_admin)):
    return _orders_where(
        "o.status='Pending' AND (LOWER(o.title) LIKE %s OR o.title ILIKE %s)",
        ("%ludo%", "%لودو%"),
    )

# ======== Approve/Deliver (عينات اختيارية) ========
class OrderActionIn(BaseModel):
    order_id: int

@router.post("/approve")
def approve_order(body: OrderActionIn, _: None = Depends(verify_admin)):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Approved' WHERE id=%s", (body.order_id,))
            if cur.rowcount == 0:
                raise HTTPException(404, "order not found")
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/deliver")
def deliver_order(body: OrderActionIn, _: None = Depends(verify_admin)):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Delivered' WHERE id=%s", (body.order_id,))
            if cur.rowcount == 0:
                raise HTTPException(404, "order not found")
        return {"ok": True}
    finally:
        put_conn(conn)

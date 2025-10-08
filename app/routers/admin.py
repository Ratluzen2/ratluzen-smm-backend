# app/routers/admin.py

import os
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Header, Body, Query
from pydantic import BaseModel, Field
from psycopg2.extras import Json
from ..db import get_conn, put_conn

# ===== إعدادات عامة =====
router = APIRouter(prefix="/api/admin", tags=["admin"])
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

def _require_admin(x_admin_password: Optional[str]):
    if not ADMIN_PASSWORD or x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="bad admin password")

def _row_to_order_dict(row) -> dict:
    """
    يحوّل صف الطلب إلى دكت مناسب للتطبيق.
    SELECT: o.id, u.uid, o.title, o.quantity, o.price, o.status, created_ms
    """
    return {
        "id": row[0],
        "uid": row[1],
        "title": row[2],
        "quantity": row[3],
        "price": float(row[4] or 0),
        "status": row[5],
        "created_at": int(row[6]),
    }

# ===== نماذج الإدخال =====
class WalletActionIn(BaseModel):
    uid: str = Field(min_length=2)
    amount: float = Field(gt=0)

class OrderActionIn(BaseModel):
    order_id: int
    status: str = Field(default="Completed", min_length=1)

# ===== فحوص أساسية =====
@router.get("/ping")
def admin_ping(x_admin_password: Optional[str] = Header(default=None)):
    _require_admin(x_admin_password)
    return {"ok": True}

# ===== إحصاءات المستخدمين =====
@router.get("/users/count")
def users_count(x_admin_password: Optional[str] = Header(default=None)):
    _require_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.users")
            n = cur.fetchone()[0]
        return {"ok": True, "count": int(n)}
    finally:
        put_conn(conn)

@router.get("/users/balances")
def users_balances(x_admin_password: Optional[str] = Header(default=None)):
    _require_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT uid, balance FROM public.users ORDER BY id DESC")
            rows = cur.fetchall()
        return {"ok": True, "users": [{"uid": r[0], "balance": float(r[1] or 0)} for r in rows]}
    finally:
        put_conn(conn)

# ===== عمليات الرصيد (إضافة/خصم) =====
@router.post("/topup")
def admin_topup(
    body: WalletActionIn,
    x_admin_password: Optional[str] = Header(default=None),
):
    _require_admin(x_admin_password)
    uid = body.uid.strip()
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = r[0]
            cur.execute(
                "UPDATE public.users SET balance=balance+%s WHERE id=%s RETURNING balance",
                (body.amount, user_id),
            )
            new_bal = float(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason, meta) "
                "VALUES(%s,%s,%s,%s)",
                (user_id, body.amount, "admin_topup", Json({"by": "owner"})),
            )
        return {"ok": True, "uid": uid, "balance": new_bal}
    finally:
        put_conn(conn)

@router.post("/deduct")
def admin_deduct(
    body: WalletActionIn,
    x_admin_password: Optional[str] = Header(default=None),
):
    _require_admin(x_admin_password)
    uid = body.uid.strip()
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1] or 0)
            if bal < body.amount:
                raise HTTPException(400, "insufficient balance")
            cur.execute(
                "UPDATE public.users SET balance=balance-%s WHERE id=%s RETURNING balance",
                (body.amount, user_id),
            )
            new_bal = float(cur.fetchone()[0])
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason, meta) "
                "VALUES(%s,%s,%s,%s)",
                (user_id, -body.amount, "admin_deduct", Json({"by": "owner"})),
            )
        return {"ok": True, "uid": uid, "balance": new_bal}
    finally:
        put_conn(conn)

# ===== رصيد المزوّد (API) =====
@router.get("/provider/balance")
def provider_balance(x_admin_password: Optional[str] = Header(default=None)):
    _require_admin(x_admin_password)

    # نحاول استعمال عميل المزوّد إن كان موجودًا
    try:
        from ..providers import smm_client  # type: ignore
    except Exception as e:
        # لا يوجد عميل—أعد رسالة واضحة
        raise HTTPException(500, f"smm client not available: {e}")

    try:
        bal = smm_client.get_balance()  # يجب أن تُرجع رقم أو dict فيه balance
        if isinstance(bal, dict):
            bal_value = float(bal.get("balance", 0))
        else:
            bal_value = float(bal)
        return {"ok": True, "balance": bal_value}
    except Exception as e:
        # فشل الاتصال بالمزوّد
        raise HTTPException(status_code=502, detail=f"provider error: {e}")

# ===== طلبات معلّقة =====
def _pending_by_title_keywords(
    keywords: List[str], limit: int = 500
) -> List[dict]:
    conn = get_conn()
    try:
        where_parts = " OR ".join(["o.title ILIKE %s"] * len(keywords))
        params = [f"%{k}%" for k in keywords]
        with conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    o.id, u.uid, o.title, o.quantity, o.price, o.status,
                    EXTRACT(EPOCH FROM o.created_at)*1000 AS created_ms
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE o.status='Pending' AND ({where_parts})
                ORDER BY o.id DESC
                LIMIT %s
                """,
                (*params, limit),
            )
            rows = cur.fetchall()
        return [_row_to_order_dict(r) for r in rows]
    finally:
        put_conn(conn)

def _pending_services(limit: int = 500) -> List[dict]:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    o.id, u.uid, o.title, o.quantity, o.price, o.status,
                    EXTRACT(EPOCH FROM o.created_at)*1000 AS created_ms
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE o.status='Pending' AND o.service_id IS NOT NULL
                ORDER BY o.id DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        return [_row_to_order_dict(r) for r in rows]
    finally:
        put_conn(conn)

@router.get("/pending/services")
def pending_services(
    x_admin_password: Optional[str] = Header(default=None),
    limit: int = Query(500, ge=1, le=2000),
):
    _require_admin(x_admin_password)
    return {"ok": True, "orders": _pending_services(limit)}

@router.get("/pending/itunes")
def pending_itunes(
    x_admin_password: Optional[str] = Header(default=None),
    limit: int = Query(500, ge=1, le=2000),
):
    _require_admin(x_admin_password)
    kws = ["itunes", "ايتونز", "آيتونز"]
    return {"ok": True, "orders": _pending_by_title_keywords(kws, limit)}

@router.get("/pending/pubg")
def pending_pubg(
    x_admin_password: Optional[str] = Header(default=None),
    limit: int = Query(500, ge=1, le=2000),
):
    _require_admin(x_admin_password)
    kws = ["pubg", "ببجي", "شدات"]
    return {"ok": True, "orders": _pending_by_title_keywords(kws, limit)}

@router.get("/pending/ludo")
def pending_ludo(
    x_admin_password: Optional[str] = Header(default=None),
    limit: int = Query(500, ge=1, le=2000),
):
    _require_admin(x_admin_password)
    kws = ["ludo", "لودو"]
    return {"ok": True, "orders": _pending_by_title_keywords(kws, limit)}

# ===== اعتماد/تسليم الطلب =====
@router.post("/approve")
def approve_order(
    body: OrderActionIn,
    x_admin_password: Optional[str] = Header(default=None),
):
    _require_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.orders SET status=%s WHERE id=%s RETURNING id",
                (body.status, body.order_id),
            )
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "order not found")
        return {"ok": True, "order_id": body.order_id, "status": body.status}
    finally:
        put_conn(conn)

@router.post("/deliver")
def deliver_order(
    body: OrderActionIn = Body(
        default=OrderActionIn(order_id=0, status="Delivered")
    ),
    x_admin_password: Optional[str] = Header(default=None),
):
    # مسار اختياري (عينات) — نفس approve لكن الحالة الافتراضية Delivered
    _require_admin(x_admin_password)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE public.orders SET status=%s WHERE id=%s RETURNING id",
                (body.status, body.order_id),
            )
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "order not found")
        return {"ok": True, "order_id": body.order_id, "status": body.status}
    finally:
        put_conn(conn)

from fastapi import APIRouter, Depends, Header, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..config import ADMIN_PASS
from ..db import get_conn, put_conn

router = APIRouter(prefix="/api/admin", tags=["admin"])

def _token(
    x_admin_upper: Optional[str] = Header(default=None, alias="X-Admin-Pass", convert_underscores=False),
    x_admin_lower: Optional[str] = Header(default=None, alias="x-admin-pass", convert_underscores=False),
    key: Optional[str] = Query(default=None),
):
    return (x_admin_upper or x_admin_lower or key or "").strip()

def _require_admin(token: str):
    if token != ADMIN_PASS:
        raise HTTPException(401, "unauthorized")

@router.get("/check")
def check(token: str = Depends(_token)):
    _require_admin(token); return {"ok": True}

@router.get("/pending/services")
def pending_services(token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, quantity, price, link, status, EXTRACT(EPOCH FROM created_at)*1000
                FROM public.orders
                WHERE status='Pending' AND service_id IS NOT NULL
                ORDER BY id DESC
            """)
            rows = cur.fetchall()
            return [
                {"id": r[0], "title": r[1], "quantity": r[2], "price": float(r[3]),
                 "payload": r[4] or "", "status": r[5], "created_at": int(r[6])}
                for r in rows
            ]
    finally: put_conn(conn)

@router.get("/pending/topups")
def pending_topups(token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, u.uid, c.card_number, EXTRACT(EPOCH FROM c.created_at)*1000
                FROM public.asiacell_cards c JOIN public.users u ON u.id=c.user_id
                WHERE c.status='Pending' ORDER BY c.id DESC
            """)
            rows = cur.fetchall()
            return [{
                "id": r[0], "title": "كارت أسيا سيل", "quantity": 0, "price": 0.0,
                "payload": f"UID={r[1]} CARD={r[2]}", "status": "Pending", "created_at": int(r[3])
            } for r in rows]
    finally: put_conn(conn)

# alias بطلب بعض النسخ من التطبيق
@router.get("/pending/cards")
def pending_cards_alias(token: str = Depends(_token)):
    return pending_topups(token)

class TopupAccept(BaseModel):
    card_id: int
    amount_usd: float

@router.post("/pending/topups/accept")
def topup_accept(body: TopupAccept, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT user_id FROM public.asiacell_cards WHERE id=%s AND status='Pending'", (body.card_id,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "card not found or not pending")
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (body.amount_usd, user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s,%s,%s,%s)
            """, (user_id, body.amount_usd, "admin_topup_card", {"card_id": body.card_id}))
            cur.execute("UPDATE public.asiacell_cards SET status='Accepted' WHERE id=%s", (body.card_id,))
        return {"ok": True}
    finally: put_conn(conn)

class TopupReject(BaseModel):
    card_id: int

@router.post("/pending/topups/reject")
def topup_reject(body: TopupReject, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.asiacell_cards SET status='Rejected' WHERE id=%s AND status='Pending'", (body.card_id,))
            if cur.rowcount == 0: raise HTTPException(404, "card not found or not pending")
        return {"ok": True}
    finally: put_conn(conn)

class WalletOp(BaseModel):
    uid: str
    amount: float

@router.post("/wallet/topup")
def admin_topup(body: WalletOp, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (body.amount, r[0]))
        return {"ok": True}
    finally: put_conn(conn)

@router.post("/wallet/deduct")
def admin_deduct(body: WalletOp, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            if float(r[1]) < body.amount: raise HTTPException(400, "insufficient balance")
            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (body.amount, r[0]))
        return {"ok": True}
    finally: put_conn(conn)

@router.get("/users/count")
def users_count(token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(1) FROM public.users")
            c = cur.fetchone()[0]
        return {"count": int(c)}
    finally: put_conn(conn)

@router.get("/users/balances")
def users_balances(token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT uid, balance FROM public.users ORDER BY uid ASC")
            rows = cur.fetchall()
        return [{"uid": r[0], "balance": float(r[1] or 0.0)} for r in rows]
    finally: put_conn(conn)

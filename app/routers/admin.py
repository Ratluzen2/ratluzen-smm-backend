from fastapi import APIRouter, Depends, Header, Query, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import base64

from ..config import ADMIN_PASS
from ..db import get_conn, put_conn

router = APIRouter(prefix="/api/admin", tags=["admin"])

# -------- Auth helpers --------
def _extract_bearer(auth: Optional[str]) -> Optional[str]:
    if not auth: return None
    auth = auth.strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    if auth.lower().startswith("basic "):
        try:
            raw = base64.b64decode(auth.split(" ",1)[1]).decode()
            # "user:pass" — أحياناً يرسل التطبيق كلمة المرور فقط
            if ":" in raw: return raw.split(":",1)[1]
            return raw
        except Exception:
            return None
    # أحياناً يرسلها مباشرةً بدون Bearer
    return auth

def _token(
    x_admin_upper: Optional[str] = Header(default=None, alias="X-Admin-Pass", convert_underscores=False),
    x_admin_lower: Optional[str] = Header(default=None, alias="x-admin-pass", convert_underscores=False),
    key: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None, alias="Authorization", convert_underscores=False),
):
    return (x_admin_upper or x_admin_lower or key or _extract_bearer(authorization) or "").strip()

def _require_admin(token: str):
    if token != ADMIN_PASS:
        raise HTTPException(401, "unauthorized")

@router.get("/check")
def check(token: str = Depends(_token)):
    _require_admin(token); return {"ok": True}

# -------- Helpers لقراءة الجسم من json/form/query --------
async def _read_payload(request: Request) -> dict:
    # جرّب JSON
    try:
        return await request.json()
    except Exception:
        pass
    # جرّب form
    try:
        form = await request.form()
        return {k: form.get(k) for k in form.keys()}
    except Exception:
        return {}

# -------- Pending Services --------
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
    finally:
        put_conn(conn)

# -------- Pending Topups --------
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
    finally:
        put_conn(conn)

@router.get("/pending/cards")  # alias مطلوب ببعض النسخ من الواجهة
def pending_cards_alias(token: str = Depends(_token)):
    return pending_topups(token)

class TopupAccept(BaseModel):
    card_id: int
    amount_usd: float

@router.post("/pending/topups/accept")
async def topup_accept(request: Request, token: str = Depends(_token),
                       card_id: Optional[int] = Query(None), amount_usd: Optional[float] = Query(None)):
    _require_admin(token)
    if card_id is None or amount_usd is None:
        p = await _read_payload(request)
        card_id = card_id or int(p.get("card_id"))
        amount_usd = amount_usd or float(p.get("amount_usd"))

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT user_id FROM public.asiacell_cards WHERE id=%s AND status='Pending'", (card_id,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "card not found or not pending")
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (amount_usd, user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s,%s,%s,%s)
            """, (user_id, amount_usd, "admin_topup_card", {"card_id": card_id}))
            cur.execute("UPDATE public.asiacell_cards SET status='Accepted' WHERE id=%s", (card_id,))
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/pending/topups/reject")
async def topup_reject(request: Request, token: str = Depends(_token),
                       card_id: Optional[int] = Query(None)):
    _require_admin(token)
    if card_id is None:
        p = await _read_payload(request)
        card_id = int(p.get("card_id"))

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.asiacell_cards SET status='Rejected' WHERE id=%s AND status='Pending'", (card_id,))
            if cur.rowcount == 0: raise HTTPException(404, "card not found or not pending")
        return {"ok": True}
    finally:
        put_conn(conn)

# -------- عمليات الرصيد (Add / Deduct) --------
class WalletOp(BaseModel):
    uid: str
    amount: float

@router.post("/wallet/topup")
@router.post("/wallet/add")       # alias
async def admin_topup(request: Request, token: str = Depends(_token),
                      uid: Optional[str] = Query(None), amount: Optional[float] = Query(None)):
    _require_admin(token)
    if uid is None or amount is None:
        p = await _read_payload(request)
        uid = uid or p.get("uid")
        amount = amount or float(p.get("amount"))

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (amount, r[0]))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s,%s,%s,%s)
            """, (r[0], amount, "admin_topup", {}))
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/wallet/deduct")
@router.post("/wallet/remove")    # alias
async def admin_deduct(request: Request, token: str = Depends(_token),
                       uid: Optional[str] = Query(None), amount: Optional[float] = Query(None)):
    _require_admin(token)
    if uid is None or amount is None:
        p = await _read_payload(request)
        uid = uid or p.get("uid")
        amount = amount or float(p.get("amount"))

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            if float(r[1]) < amount: raise HTTPException(400, "insufficient balance")
            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (amount, r[0]))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s,%s,%s,%s)
            """, (r[0], -amount, "admin_deduct", {}))
        return {"ok": True}
    finally:
        put_conn(conn)

# -------- إحصاءات --------
@router.get("/users/count")
def users_count(token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(1) FROM public.users")
            c = cur.fetchone()[0]
        return {"count": int(c)}
    finally:
        put_conn(conn)

@router.get("/users/balances")
def users_balances(token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT uid, balance FROM public.users ORDER BY uid ASC")
            rows = cur.fetchall()
        return [{"uid": r[0], "balance": float(r[1] or 0.0)} for r in rows]
    finally:
        put_conn(conn)

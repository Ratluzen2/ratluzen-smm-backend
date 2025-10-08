from fastapi import APIRouter, Depends, Header, Query, HTTPException, Request
from typing import Optional, Dict, Any, List
from psycopg2.extras import Json
import base64, requests

from ..config import ADMIN_PASS, KD1S_API_URL, KD1S_API_KEY
from ..db import get_conn, put_conn

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ===== auth helpers =====
def _extract_bearer(auth: Optional[str]) -> Optional[str]:
    if not auth: return None
    auth = auth.strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    if auth.lower().startswith("basic "):
        try:
            raw = base64.b64decode(auth.split(" ", 1)[1]).decode()
            return raw.split(":", 1)[1] if ":" in raw else raw
        except Exception:
            return None
    return auth

def _token(
    x_admin_pass: Optional[str] = Header(None, alias="x-admin-pass", convert_underscores=False),
    key: Optional[str] = Query(None),
    admin_password: Optional[str] = Query(None, alias="admin_password"),
    authorization: Optional[str] = Header(None, alias="Authorization", convert_underscores=False),
):
    return (x_admin_pass or key or admin_password or _extract_bearer(authorization) or "").strip()

def _require_admin(token: str):
    if token != ADMIN_PASS:
        raise HTTPException(401, "unauthorized")

@router.get("/check")
def check(token: str = Depends(_token)):
    _require_admin(token); return {"ok": True}

# ===== utils =====
async def _read_payload(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
        if isinstance(data, dict): return data
    except Exception:
        pass
    try:
        form = await request.form()
        return {k: form.get(k) for k in form.keys()}
    except Exception:
        return {}

def _json_list(items: List[Dict[str, Any]]):
    return {"list": items}

# ===== pending: خدمات مزوّد (services) =====
@router.get("/pending/services")
def pending_services(token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT o.id, u.uid, o.title, o.link, o.quantity, o.price,
                       EXTRACT(EPOCH FROM o.created_at)*1000
                FROM public.orders o
                JOIN public.users u ON u.id=o.user_id
                WHERE o.status='Pending' AND o.service_id IS NOT NULL
                ORDER BY o.id DESC
            """)
            rows = cur.fetchall()
            items = [{
                "id": r[0], "uid": r[1], "service_key": r[2], "link": r[3] or "",
                "quantity": r[4] or 0, "price": float(r[5] or 0.0), "created_at": int(r[6])
            } for r in rows]
            return _json_list(items)
    finally:
        put_conn(conn)

@router.post("/pending/services/{order_id}/approve")
def approve_service(order_id: int, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            # تنفيذ الطلب (نعيّن Done)
            cur.execute("UPDATE public.orders SET status='Done' WHERE id=%s AND status='Pending'", (order_id,))
            if cur.rowcount == 0: raise HTTPException(404, "order not found or not pending")
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/pending/services/{order_id}/reject")
def reject_service(order_id: int, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            # استرجاع السعر لعمل استرداد
            cur.execute("SELECT user_id, price FROM public.orders WHERE id=%s AND status='Pending'", (order_id,))
            row = cur.fetchone()
            if not row: raise HTTPException(404, "order not found or not pending")
            user_id, price = row[0], float(row[1] or 0.0)
            cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
            if price > 0:
                cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (price, user_id))
                cur.execute("""INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                               VALUES(%s,%s,%s,%s)""",
                            (user_id, price, "admin_reject_refund", Json({"order_id": order_id})))
        return {"ok": True}
    finally:
        put_conn(conn)

# ===== pending: كروت أسيا سيل =====
@router.get("/pending/cards")
def pending_cards(token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, u.uid, c.card_number, EXTRACT(EPOCH FROM c.created_at)*1000
                FROM public.asiacell_cards c
                JOIN public.users u ON u.id=c.user_id
                WHERE c.status='Pending'
                ORDER BY c.id DESC
            """)
            rows = cur.fetchall()
            items = [{"id": r[0], "uid": r[1], "card_number": r[2], "created_at": int(r[3])} for r in rows]
            return _json_list(items)
    finally:
        put_conn(conn)

@router.post("/pending/cards/{card_id}/accept")
async def accept_card(card_id: int, request: Request, token: str = Depends(_token)):
    _require_admin(token)
    p = await _read_payload(request)
    amount = float(p.get("amount_usd") or p.get("amount") or 0)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT user_id FROM public.asiacell_cards WHERE id=%s AND status='Pending'", (card_id,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "card not found or not pending")
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (amount, user_id))
            cur.execute("""INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                           VALUES(%s,%s,%s,%s)""",
                        (user_id, amount, "admin_topup_card", Json({"card_id": card_id})))
            cur.execute("UPDATE public.asiacell_cards SET status='Accepted' WHERE id=%s", (card_id,))
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/pending/cards/{card_id}/reject")
def reject_card(card_id: int, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.asiacell_cards SET status='Rejected' WHERE id=%s AND status='Pending'", (card_id,))
            if cur.rowcount == 0: raise HTTPException(404, "card not found or not pending")
        return {"ok": True}
    finally:
        put_conn(conn)

# ===== pending: iTunes / PUBG / Ludo (قوائم + تنفيذ/رفض) =====
def _pending_by_titles(titles: List[str]):
    like_params = tuple(["%" + t.lower() + "%" for t in titles])
    where = " OR ".join(["LOWER(o.title) LIKE %s"] * len(titles))
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(f"""
                SELECT o.id, u.uid, o.title, o.link, o.quantity, o.price,
                       EXTRACT(EPOCH FROM o.created_at)*1000
                FROM public.orders o JOIN public.users u ON u.id=o.user_id
                WHERE o.status='Pending' AND ({where})
                ORDER BY o.id DESC
            """, like_params)
            return cur.fetchall()
    finally:
        put_conn(conn)

@router.get("/pending/itunes")
def pending_itunes(token: str = Depends(_token)):
    _require_admin(token)
    rows = _pending_by_titles(["ايتونز", "itunes"])
    items = [{
        "id": r[0], "uid": r[1],
        "amount": r[4] or 0,     # نضع الكمية كـ amount إن وُجدت
        "created_at": int(r[6])
    } for r in rows]
    return _json_list(items)

@router.post("/pending/itunes/{order_id}/deliver")
async def itunes_deliver(order_id: int, request: Request, token: str = Depends(_token)):
    _require_admin(token)
    code = (await _read_payload(request)).get("gift_code", "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            # نضع الكود داخل link للتوثيق ونغلق الطلب
            cur.execute("UPDATE public.orders SET status='Done', link=%s WHERE id=%s AND status='Pending'",
                        (f"gift:{code}", order_id))
            if cur.rowcount == 0: raise HTTPException(404, "order not found or not pending")
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/pending/itunes/{order_id}/reject")
def itunes_reject(order_id: int, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s AND status='Pending'", (order_id,))
            if cur.rowcount == 0: raise HTTPException(404, "order not found or not pending")
        return {"ok": True}
    finally:
        put_conn(conn)

@router.get("/pending/pubg")
def pending_pubg(token: str = Depends(_token)):
    _require_admin(token)
    rows = _pending_by_titles(["شدات ببجي", "pubg"])
    items = [{
        "id": r[0], "uid": r[1], "pkg": r[4] or 0, "pubg_id": r[3] or "", "created_at": int(r[6])
    } for r in rows]
    return _json_list(items)

@router.post("/pending/pubg/{order_id}/deliver")
def pubg_deliver(order_id: int, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Done' WHERE id=%s AND status='Pending'", (order_id,))
            if cur.rowcount == 0: raise HTTPException(404, "order not found or not pending")
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/pending/pubg/{order_id}/reject")
def pubg_reject(order_id: int, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s AND status='Pending'", (order_id,))
            if cur.rowcount == 0: raise HTTPException(404, "order not found or not pending")
        return {"ok": True}
    finally:
        put_conn(conn)

@router.get("/pending/ludo")
def pending_ludo(token: str = Depends(_token)):
    _require_admin(token)
    rows = _pending_by_titles(["لودو", "ludo"])
    items = [{
        "id": r[0], "uid": r[1], "kind": "ludo", "pack": r[4] or 0, "ludo_id": r[3] or "", "created_at": int(r[6])
    } for r in rows]
    return _json_list(items)

@router.post("/pending/ludo/{order_id}/deliver")
def ludo_deliver(order_id: int, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Done' WHERE id=%s AND status='Pending'", (order_id,))
            if cur.rowcount == 0: raise HTTPException(404, "order not found or not pending")
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/pending/ludo/{order_id}/reject")
def ludo_reject(order_id: int, token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s AND status='Pending'", (order_id,))
            if cur.rowcount == 0: raise HTTPException(404, "order not found or not pending")
        return {"ok": True}
    finally:
        put_conn(conn)

# ===== users ops for owner =====
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
        return {"list": [{"uid": r[0], "balance": float(r[1] or 0.0)} for r in rows]}
    finally:
        put_conn(conn)

@router.post("/users/{uid}/topup")
async def user_topup(uid: str, request: Request, token: str = Depends(_token)):
    _require_admin(token)
    p = await _read_payload(request)
    amount = float(p.get("amount") or 0)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (amount, user_id))
            cur.execute("""INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                           VALUES(%s,%s,%s,%s)""", (user_id, amount, "admin_topup", Json({})))
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/users/{uid}/deduct")
async def user_deduct(uid: str, request: Request, token: str = Depends(_token)):
    _require_admin(token)
    p = await _read_payload(request)
    amount = float(p.get("amount") or 0)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r: raise HTTPException(404, "user not found")
            if float(r[1]) < amount: raise HTTPException(400, "insufficient balance")
            user_id = r[0]
            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (amount, user_id))
            cur.execute("""INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                           VALUES(%s,%s,%s,%s)""", (user_id, -amount, "admin_deduct", Json({})))
        return {"ok": True}
    finally:
        put_conn(conn)

# ===== provider balance =====
@router.get("/provider/balance")
def provider_balance(token: str = Depends(_token)):
    _require_admin(token)
    if not KD1S_API_URL or not KD1S_API_KEY:
        return {"balance": None}
    try:
        r = requests.post(KD1S_API_URL, data={"key": KD1S_API_KEY, "action": "balance"}, timeout=20)
        r.raise_for_status()
        js = r.json()
        bal = None
        for k in ("balance","funds","data","result"):
            if k in js:
                try: bal = float(js[k]); break
                except Exception: pass
        return {"balance": bal}
    except Exception:
        return {"balance": None}

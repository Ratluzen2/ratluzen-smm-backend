from fastapi import APIRouter, Depends, Header, Query, HTTPException, Request
from typing import Optional, Dict, Any, List
from psycopg2.extras import Json
import base64, os, requests

from ..config import ADMIN_PASS, KD1S_API_URL, KD1S_API_KEY
from ..db import get_conn, put_conn

router = APIRouter(prefix="/api/admin", tags=["admin"])

# ================= Auth helpers =================
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
    x_admin_key: Optional[str]  = Header(None, alias="x-admin-key",  convert_underscores=False),
    x_owner_key: Optional[str]  = Header(None, alias="x-owner-key",  convert_underscores=False),
    x_key: Optional[str]        = Header(None, alias="x-key",        convert_underscores=False),
    admin_password: Optional[str] = Query(None, alias="admin_password"),
    key: Optional[str] = Query(None),
    token_q: Optional[str] = Query(None, alias="token"),
    password: Optional[str] = Query(None, alias="password"),
    _auth: Optional[str] = Header(None, alias="Authorization", convert_underscores=False),
):
    return (x_admin_pass or x_admin_key or x_owner_key or x_key or
            admin_password or key or token_q or password or _extract_bearer(_auth) or "").strip()

def _require_admin(token: str):
    if token != ADMIN_PASS:
        raise HTTPException(401, "unauthorized")

@router.get("/check")
def check(token: str = Depends(_token)):
    _require_admin(token)
    return {"ok": True}

# ================= Utils =================
async def _read_payload(request: Request) -> Dict[str, Any]:
    # يقبل JSON أو x-www-form-urlencoded
    try:
        data = await request.json()
        if isinstance(data, dict): 
            return data
    except Exception:
        pass
    try:
        form = await request.form()
        return {k: form.get(k) for k in form.keys()}
    except Exception:
        return {}

def _row_to_admin_item(row) -> Dict[str, Any]:
    # id, title, quantity, price, link/payload, status, created_ms
    return {
        "id": row[0],
        "title": row[1],
        "quantity": row[2],
        "price": float(row[3] or 0),
        "payload": row[4] or "",
        "status": row[5],
        "created_at": int(row[6]),
    }

def _fetch_pending_where(where_sql: str, params: tuple) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, title, COALESCE(quantity,0), COALESCE(price,0), link, status,
                       EXTRACT(EPOCH FROM created_at)*1000
                FROM public.orders
                WHERE status='Pending' AND {where_sql}
                ORDER BY id DESC
            """, params)
            return [_row_to_admin_item(r) for r in cur.fetchall()]
    finally:
        put_conn(conn)

# ================= Pending Aliases (لمنع "تعذّر جلب البيانات") =================
def _wrap_orders_list(items: List[Dict[str, Any]]):
    # بعض الشاشات تريد مصفوفة مباشرة، وبعضها يريد {"orders": []}
    return items, {"orders": items}

@router.get("/pending/cards")
def pending_cards(token: str = Depends(_token)):
    _require_admin(token)
    items = _fetch_pending_where("LOWER(title) LIKE %s", ("%card%",))
    arr, obj = _wrap_orders_list(items)
    return obj  # نرجّع شكل object

@router.get("/pending/cards/list")
def pending_cards_list(token: str = Depends(_token)):
    _require_admin(token)
    return {"orders": _fetch_pending_where("LOWER(title) LIKE %s", ("%card%",))}

@router.get("/pending/itunes")
def pending_itunes(token: str = Depends(_token)):
    _require_admin(token)
    return {"orders": _fetch_pending_where("LOWER(title) LIKE %s", ("%itunes%",))}

@router.get("/pending/pubg")
def pending_pubg(token: str = Depends(_token)):
    _require_admin(token)
    return {"orders": _fetch_pending_where("LOWER(title) LIKE %s", ("%pubg%",))}

@router.get("/pending/ludo")
def pending_ludo(token: str = Depends(_token)):
    _require_admin(token)
    return {"orders": _fetch_pending_where("LOWER(title) LIKE %s", ("%ludo%",))}

@router.get("/pending/services")
def pending_services(token: str = Depends(_token)):
    _require_admin(token)
    return {"orders": _fetch_pending_where("service_id IS NOT NULL", tuple())}

# ================= Wallet: إضافة/خصم =================
@router.post("/wallet/add")
async def admin_topup(request: Request, token: str = Depends(_token),
                      uid: Optional[str] = Query(None), amount: Optional[float] = Query(None)):
    _require_admin(token)
    if uid is None or amount is None:
        p = await _read_payload(request)
        uid = uid or p.get("uid")
        amount = amount or float(p.get("amount") or 0)
    if not uid:
        raise HTTPException(422, "uid required")
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
            """, (r[0], amount, "admin_topup", Json({})))
        return {"ok": True}
    finally:
        put_conn(conn)

@router.post("/wallet/deduct")
async def admin_deduct(request: Request, token: str = Depends(_token),
                       uid: Optional[str] = Query(None), amount: Optional[float] = Query(None)):
    _require_admin(token)
    if uid is None or amount is None:
        p = await _read_payload(request)
        uid = uid or p.get("uid")
        amount = amount or float(p.get("amount") or 0)
    if not uid:
        raise HTTPException(422, "uid required")
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
            """, (r[0], -amount, "admin_deduct", Json({})))
        return {"ok": True}
    finally:
        put_conn(conn)

# ================= Stats / Users =================
@router.get("/users/balances")
def users_balances(token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT uid, balance FROM public.users ORDER BY uid ASC")
            rows = cur.fetchall()
        items = [{"uid": r[0], "balance": float(r[1] or 0.0)} for r in rows]
        # شكلان للتماشي مع أكثر من شاشة
        return {"users": items, "count": len(items)}
    finally:
        put_conn(conn)

@router.get("/users/balances/list")
def users_balances_list(token: str = Depends(_token)):
    _require_admin(token)
    # بعض الشاشات تتوقع فقط {"users": []}
    return users_balances(token)

@router.get("/users/count")
def users_count(token: str = Depends(_token)):
    _require_admin(token)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(1) FROM public.users")
            c = cur.fetchone()[0]
        # نرجّع value و count معًا لتغطية كل الاحتمالات
        return {"value": int(c), "count": int(c)}
    finally:
        put_conn(conn)

# ================= Provider (رصيد المزود API) =================
def _kd1s_balance() -> Optional[float]:
    url = KD1S_API_URL or os.getenv("KD1S_API_URL")
    key = KD1S_API_KEY or os.getenv("KD1S_API_KEY")
    if not url or not key:
        return None
    try:
        # أغلب مزودي SMM يدعمون endpoint balance بنفس الشكل
        r = requests.post(url, data={"key": key, "action": "balance"}, timeout=20)
        r.raise_for_status()
        js = r.json()
        # نحاول قراءة الحقول الشائعة
        for k in ("balance", "funds", "data", "result"):
            if k in js and isinstance(js[k], (int, float, str)):
                try:
                    return float(js[k])
                except Exception:
                    pass
        # fallback: أرقام داخل نص
        txt = r.text
        import re
        m = re.search(r"(\d+(?:\.\d+)?)", txt)
        return float(m.group(1)) if m else None
    except Exception:
        return None

@router.get("/provider/balance")
def provider_balance(token: str = Depends(_token)):
    _require_admin(token)
    bal = _kd1s_balance()
    return {"balance": bal}

# بعض الشاشات قد تستعمل اسمًا آخر:
@router.get("/smm/balance")
def smm_balance_alias(token: str = Depends(_token)):
    return provider_balance(token)

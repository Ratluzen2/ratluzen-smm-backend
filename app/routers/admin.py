from fastapi import APIRouter, Depends, Header, Query, HTTPException, Request
from typing import Optional, Dict, Any, List, Tuple
from psycopg2.extras import Json
import base64, re, requests

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
    key: Optional[str] = Query(None),
    admin_password: Optional[str] = Query(None, alias="admin_password"),
    authorization: Optional[str] = Header(None, alias="Authorization", convert_underscores=False),
):
    return (x_admin_pass or x_admin_key or key or admin_password or _extract_bearer(authorization) or "").strip()

def _require_admin(token: str):
    if token != ADMIN_PASS:
        raise HTTPException(401, "unauthorized")

@router.get("/check")
def check(token: str = Depends(_token)):
    _require_admin(token); return {"ok": True}

# ================= Utils =================
async def _read_payload(request: Request) -> Dict[str, Any]:
    # JSON أولاً
    try:
        data = await request.json()
        if isinstance(data, dict): return data
    except Exception:
        pass
    # ثم form
    try:
        form = await request.form()
        return {k: form.get(k) for k in form.keys()}
    except Exception:
        return {}

def _pick_id(p: Dict[str, Any], *names: str) -> Optional[int]:
    for n in names:
        if n in p and p[n] not in (None, ""):
            try: return int(str(p[n]).strip())
            except Exception: pass
    return None

def _pick_text(p: Dict[str, Any], *names: str) -> Optional[str]:
    for n in names:
        v = p.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return None

def _pick_amount(p: Dict[str, Any], *names: str) -> float:
    # يقبل "10", "10.0", "IQD 10,000", "12,5" ... إلخ
    for n in names:
        if n in p and p[n] not in (None, ""):
            raw = str(p[n]).strip()
            m = re.search(r"[-+]?\d+(?:[.,]\d+)?", raw)
            if m:
                return float(m.group(0).replace(",", "."))
    return 0.0

def _json_list(items: List[Dict[str, Any]]):
    # بعض الشاشات تريد {"list":[...]} وأخرى {"orders":[...]}، نرجّع الشكل الأكثر شيوعًا للوحة
    return {"list": items}

# ================== PENDING: Lists ==================
def _fetch_pending_cards() -> List[Dict[str, Any]]:
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
            return [{"id": r[0], "uid": r[1], "card_number": r[2], "created_at": int(r[3])} for r in rows]
    finally:
        put_conn(conn)

@router.get("/pending/cards")
def pending_cards(token: str = Depends(_token)):
    _require_admin(token)
    return _json_list(_fetch_pending_cards())

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
                "id": r[0], "uid": r[1], "service_key": r[2],
                "link": r[3] or "", "quantity": r[4] or 0,
                "price": float(r[5] or 0.0), "created_at": int(r[6])
            } for r in rows]
            return _json_list(items)
    finally:
        put_conn(conn)

def _pending_by_titles(titles: List[str]) -> List[Tuple]:
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
    items = [{"id": r[0], "uid": r[1], "amount": r[4] or 0, "created_at": int(r[6])} for r in rows]
    return _json_list(items)

@router.get("/pending/pubg")
def pending_pubg(token: str = Depends(_token)):
    _require_admin(token)
    rows = _pending_by_titles(["شدات ببجي", "pubg"])
    items = [{"id": r[0], "uid": r[1], "pkg": r[4] or 0, "pubg_id": r[3] or "", "created_at": int(r[6])} for r in rows]
    return _json_list(items)

@router.get("/pending/ludo")
def pending_ludo(token: str = Depends(_token)):
    _require_admin(token)
    rows = _pending_by_titles(["لودو", "ludo"])
    items = [{"id": r[0], "uid": r[1], "pack": r[4] or 0, "ludo_id": r[3] or "", "created_at": int(r[6])} for r in rows]
    return _json_list(items)

# ================== PENDING: Cards (accept/reject) ==================
def _accept_card(card_id: int, amount: float):
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
    finally:
        put_conn(conn)

def _reject_card(card_id: int):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.asiacell_cards SET status='Rejected' WHERE id=%s AND status='Pending'", (card_id,))
            if cur.rowcount == 0: raise HTTPException(404, "card not found or not pending")
    finally:
        put_conn(conn)

# مسارات بـ{card_id} في الـPath
@router.post("/pending/cards/{card_id}/accept")
async def cards_accept_path(card_id: int, request: Request, token: str = Depends(_token)):
    _require_admin(token)
    p = await _read_payload(request)
    amount = _pick_amount(p, "amount_usd", "amount", "value", "qty", "quantity")
    _accept_card(card_id, amount)
    return {"ok": True}

@router.post("/pending/cards/{card_id}/reject")
def cards_reject_path(card_id: int, token: str = Depends(_token)):
    _require_admin(token); _reject_card(card_id); return {"ok": True}

# Aliases بدون {id} في الـPath (id في الجسم/الاستعلام) + أسماء قديمة topups/*
@router.post("/pending/cards/accept")
@router.post("/pending/topups/accept")
async def cards_accept_legacy(request: Request, token: str = Depends(_token),
                              card_id_q: Optional[int] = Query(None, alias="card_id")):
    _require_admin(token)
    p = await _read_payload(request)
    cid = card_id_q or _pick_id(p, "card_id", "id")
    if cid is None: raise HTTPException(422, "card_id required")
    amount = _pick_amount(p, "amount_usd", "amount", "value", "qty", "quantity")
    _accept_card(cid, amount)
    return {"ok": True}

@router.post("/pending/cards/reject")
@router.post("/pending/topups/reject")
async def cards_reject_legacy(request: Request, token: str = Depends(_token),
                              card_id_q: Optional[int] = Query(None, alias="card_id")):
    _require_admin(token)
    p = await _read_payload(request)
    cid = card_id_q or _pick_id(p, "card_id", "id")
    if cid is None: raise HTTPException(422, "card_id required")
    _reject_card(cid)
    return {"ok": True}

# ================== PENDING: Provider services approve/reject ==================
def _approve_service(order_id: int):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Done' WHERE id=%s AND status='Pending'", (order_id,))
            if cur.rowcount == 0: raise HTTPException(404, "order not found or not pending")
    finally:
        put_conn(conn)

def _reject_service(order_id: int):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
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
    finally:
        put_conn(conn)

# بـ{order_id} في الـPath
@router.post("/pending/services/{order_id}/approve")
def services_approve_path(order_id: int, token: str = Depends(_token)):
    _require_admin(token); _approve_service(order_id); return {"ok": True}

@router.post("/pending/services/{order_id}/reject")
def services_reject_path(order_id: int, token: str = Depends(_token)):
    _require_admin(token); _reject_service(order_id); return {"ok": True}

# Aliases بدون {id} (id في الجسم/الاستعلام)
@router.post("/pending/services/approve")
@router.post("/pending/services/reject")
async def services_action_legacy(request: Request, token: str = Depends(_token),
                                 order_id_q: Optional[int] = Query(None, alias="order_id")):
    _require_admin(token)
    p = await _read_payload(request)
    oid = order_id_q or _pick_id(p, "order_id", "id")
    if oid is None: raise HTTPException(422, "order_id required")
    if str(request.url.path).endswith("/approve"):
        _approve_service(oid)
    else:
        _reject_service(oid)
    return {"ok": True}

# ================== PENDING: iTunes / PUBG / Ludo (deliver/reject) ==================
def _finish_order(order_id: int, status: str, link_note: Optional[str] = None):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            if status == "Done":
                cur.execute("UPDATE public.orders SET status='Done', link=COALESCE(%s, link) WHERE id=%s AND status='Pending'",
                            (link_note, order_id))
            else:
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s AND status='Pending'", (order_id,))
            if cur.rowcount == 0: raise HTTPException(404, "order not found or not pending")
    finally:
        put_conn(conn)

def _deliver_alias(request: Request) -> bool:
    # true إذا endpoint ينتهي بـ deliver
    return str(request.url.path).endswith("/deliver")

async def _itunes_action(order_id: Optional[int], request: Request):
    p = await _read_payload(request)
    code = _pick_text(p, "gift_code", "code", "card", "voucher", "pin")
    if _deliver_alias(request):
        _finish_order(order_id, "Done", f"gift:{code or ''}")
    else:
        _finish_order(order_id, "Rejected")

async def _simple_action(order_id: Optional[int], request: Request):
    if _deliver_alias(request):
        _finish_order(order_id, "Done")
    else:
        _finish_order(order_id, "Rejected")

# paths مع {order_id}
@router.post("/pending/itunes/{order_id}/deliver")
@router.post("/pending/itunes/{order_id}/reject")
async def itunes_path(order_id: int, request: Request, token: str = Depends(_token)):
    _require_admin(token); await _itunes_action(order_id, request); return {"ok": True}

@router.post("/pending/pubg/{order_id}/deliver")
@router.post("/pending/pubg/{order_id}/reject")
async def pubg_path(order_id: int, request: Request, token: str = Depends(_token)):
    _require_admin(token); await _simple_action(order_id, request); return {"ok": True}

@router.post("/pending/ludo/{order_id}/deliver")
@router.post("/pending/ludo/{order_id}/reject")
async def ludo_path(order_id: int, request: Request, token: str = Depends(_token)):
    _require_admin(token); await _simple_action(order_id, request); return {"ok": True}

# legacy بدون {id} في الـPath — نقرأ order_id من الجسم/الاستعلام
@router.post("/pending/itunes/deliver")
@router.post("/pending/itunes/reject")
async def itunes_legacy(request: Request, token: str = Depends(_token),
                        order_id_q: Optional[int] = Query(None, alias="order_id")):
    _require_admin(token)
    p = await _read_payload(request)
    oid = order_id_q or _pick_id(p, "order_id", "id")
    if oid is None: raise HTTPException(422, "order_id required")
    await _itunes_action(oid, request)
    return {"ok": True}

@router.post("/pending/pubg/deliver")
@router.post("/pending/pubg/reject")
async def pubg_legacy(request: Request, token: str = Depends(_token),
                      order_id_q: Optional[int] = Query(None, alias="order_id")):
    _require_admin(token)
    p = await _read_payload(request)
    oid = order_id_q or _pick_id(p, "order_id", "id")
    if oid is None: raise HTTPException(422, "order_id required")
    await _simple_action(oid, request)
    return {"ok": True}

@router.post("/pending/ludo/deliver")
@router.post("/pending/ludo/reject")
async def ludo_legacy(request: Request, token: str = Depends(_token),
                      order_id_q: Optional[int] = Query(None, alias="order_id")):
    _require_admin(token)
    p = await _read_payload(request)
    oid = order_id_q or _pick_id(p, "order_id", "id")
    if oid is None: raise HTTPException(422, "order_id required")
    await _simple_action(oid, request)
    return {"ok": True}

# ================== Users / Stats ==================
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

# ================== Provider balance (اختياري) ==================
@router.get("/provider/balance")
def provider_balance(token: str = Depends(_token)):
    _require_admin(token)
    if not KD1S_API_URL or not KD1S_API_KEY: return {"balance": None}
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

from fastapi import FastAPI, Depends, HTTPException, Header, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import os, json, re, urllib.parse, urllib.request

from .db import get_conn, put_conn
from .util import require_admin

# ------------ إعدادات بيئة ------------
ADMIN_PASS = os.getenv("ADMIN_PASS") or os.getenv("ADMIN_PASSWORD", "2000")
SUPPORT_TELEGRAM_URL = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/your_support")
SUPPORT_WHATSAPP_URL = os.getenv("SUPPORT_WHATSAPP_URL", "https://wa.me/1234567890")
SMM_API_URL = (os.getenv("SMM_API_URL") or os.getenv("KD1S_API_URL") or "https://kd1s.com/api/v2").strip().rstrip("/")
SMM_API_KEY = (os.getenv("SMM_API_KEY") or os.getenv("KD1S_API_KEY") or "").strip()

app = FastAPI(title="Ratluzen SMM Backend", version="1.0.0")

# ------------ CORS ليعمل من داخل الـAPK ------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------ Health ------------
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/health")
def health_alias():
    return {"ok": True}

# ------------ Config (روابط دعم) ------------
@app.get("/api/config")
def get_config():
    return {
        "ok": True,
        "data": {
            "support_telegram_url": SUPPORT_TELEGRAM_URL,
            "support_whatsapp_url": SUPPORT_WHATSAPP_URL,
            "app_name": "Ratluzen SMM Backend"
        }
    }

# ------------ فحص الخادم / المزود ------------
def _smm_balance_safe() -> Dict[str, Any]:
    """يحاول طلب رصيد المزود؛ لا يفشل السيرفر لو تعطل المزود."""
    if not SMM_API_KEY:
        return {"ok": False, "error": "no_api_key"}
    try:
        data = urllib.parse.urlencode({"key": SMM_API_KEY, "action": "balance"}).encode()
        req = urllib.request.Request(SMM_API_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            js = json.loads(raw)
            return {"ok": True, "data": js}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/server/ping")
def server_ping():
    smm = _smm_balance_safe()
    # ارجع هيكل واضح حتى لو فشل المزود
    out = {"ok": True, "upstream_ok": bool(smm.get("ok"))}
    if smm.get("ok"):
        out["balance_sample"] = smm.get("data", {})
    else:
        out["note"] = "upstream_error"
    return out

# ========== نماذج الإدخال ==========
class UpsertUserIn(BaseModel):
    uid: str

class ProviderOrderIn(BaseModel):
    uid: str
    service_id: int
    service_name: str
    link: str
    quantity: int = Field(ge=1)
    price: float = Field(ge=0)

class ManualOrderIn(BaseModel):
    uid: str
    title: str

class AsiacellCardIn(BaseModel):
    uid: str
    card: str

class OrderActionIn(BaseModel):
    order_id: int

class WalletOpIn(BaseModel):
    uid: str
    amount: float

# ========== أدوات ==========
import re as _re
def _valid_card(num: str) -> bool:
    return bool(_re.fullmatch(r"\d{14}|\d{16}", num))

def _header_admin_token(
    x_admin_upper: Optional[str] = Header(default=None, alias="X-Admin-Pass"),
    x_admin_lower: Optional[str] = Header(default=None, alias="x-admin-pass"),
    key: Optional[str] = Query(default=None),
) -> Optional[str]:
    return (x_admin_upper or x_admin_lower or key)

def _get_user_id(cur, uid: str) -> int:
    cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, "user not found")
    return r[0]

# ========== المستخدمون / المحفظة ==========
@app.post("/api/users/upsert")
def upsert_user(body: UpsertUserIn):
    uid = body.uid.strip()
    if not uid:
        raise HTTPException(422, "uid required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            row = cur.fetchone()
            if row:
                return {"ok": True, "uid": uid}
            cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (uid,))
            cur.fetchone()
        return {"ok": True, "uid": uid}
    finally:
        put_conn(conn)

@app.get("/api/wallet/balance")
def wallet_balance(uid: str):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT balance FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            bal = r[0] if r else 0.0
        return {"ok": True, "balance": float(bal)}
    finally:
        put_conn(conn)

@app.post("/api/wallet/asiacell/submit")
def submit_asiacell_card(body: AsiacellCardIn):
    card = body.card.strip()
    if not _valid_card(card):
        raise HTTPException(422, "invalid card")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = r[0]
            cur.execute("""
                INSERT INTO public.asiacell_cards(user_id, card_number, status)
                VALUES(%s,%s,'Pending') RETURNING id
            """, (user_id, card))
            cid = cur.fetchone()[0]
        return {"ok": True, "card_id": cid}
    finally:
        put_conn(conn)

# ========== الطلبات ==========
@app.post("/api/orders/create/provider")
def create_provider_order(body: ProviderOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (body.uid,))
            u = cur.fetchone()
            if not u:
                raise HTTPException(404, "user not found")
            user_id, balance = u[0], float(u[1])
            if balance < body.price:
                raise HTTPException(400, detail="insufficient balance")
            cur.execute("UPDATE public.users SET balance = balance - %s WHERE id=%s", (body.price, user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s, %s, %s, %s)
            """, (user_id, -body.price, "order_charge",
                  json.dumps({"service_id": body.service_id, "name": body.service_name, "qty": body.quantity})))
            cur.execute("""
                INSERT INTO public.orders(user_id, title, service_id, link, quantity, price, status)
                VALUES(%s,%s,%s,%s,%s,%s,'Pending') RETURNING id
            """, (user_id, body.service_name, body.service_id, body.link, body.quantity, body.price))
            oid = cur.fetchone()[0]
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

@app.post("/api/orders/create/manual")
def create_manual_order(body: ManualOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = r[0]
            cur.execute("""
                INSERT INTO public.orders(user_id, title, quantity, price, status)
                VALUES(%s,%s,0,0,'Pending') RETURNING id
            """, (user_id, body.title))
            oid = cur.fetchone()[0]
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

@app.get("/api/orders/my")
def my_orders(uid: str):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                return []
            user_id = r[0]
            cur.execute("""
                SELECT id, title, quantity, price, status, EXTRACT(EPOCH FROM created_at)*1000
                FROM public.orders WHERE user_id=%s ORDER BY id DESC
            """, (user_id,))
            rows = cur.fetchall()
            return [
                {"id": row[0], "title": row[1], "quantity": row[2], "price": float(row[3]),
                 "status": row[4], "created_at": int(row[5])}
                for row in rows
            ]
    finally:
        put_conn(conn)

# ========== أدمن ==========
def admin_token(
    token: Optional[str] = Depends(_header_admin_token)
) -> Optional[str]:
    return token

@app.get("/api/admin/pending/topups")
def pending_topups(x_admin: Optional[str] = Depends(admin_token)):
    require_admin(x_admin, ADMIN_PASS)
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

# Alias لتوافق الواجهة التي قد تستدعي /pending/cards
@app.get("/api/admin/pending/cards")
def pending_cards_alias(x_admin: Optional[str] = Depends(admin_token)):
    return pending_topups(x_admin)

# الخدمات المعلّقة (أوامر مزوّد) — ترجع مصفوفة مباشرة
@app.get("/api/admin/pending/services")
def pending_services(x_admin: Optional[str] = Depends(admin_token)):
    require_admin(x_admin, ADMIN_PASS)
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
                 "payload": (r[4] or ""), "status": r[5], "created_at": int(r[6])}
                for r in rows
            ]
    finally:
        put_conn(conn)

class AcceptTopupIn(BaseModel):
    card_id: int
    amount_usd: float

@app.post("/api/admin/pending/topups/accept")
def accept_topup(body: AcceptTopupIn, x_admin: Optional[str] = Depends(admin_token)):
    require_admin(x_admin, ADMIN_PASS)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            # جلب الكارت والمستخدم
            cur.execute("""
                SELECT c.user_id FROM public.asiacell_cards c WHERE c.id=%s AND c.status='Pending'
            """, (body.card_id,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "card not found or not pending")
            user_id = r[0]
            # شحن الرصيد وتحديث حالة الكارت
            cur.execute("UPDATE public.users SET balance = balance + %s WHERE id=%s", (body.amount_usd, user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s, %s, %s, %s)
            """, (user_id, body.amount_usd, "admin_topup_card", json.dumps({"card_id": body.card_id})))
            cur.execute("UPDATE public.asiacell_cards SET status='Accepted' WHERE id=%s", (body.card_id,))
        return {"ok": True}
    finally:
        put_conn(conn)

class RejectTopupIn(BaseModel):
    card_id: int

@app.post("/api/admin/pending/topups/reject")
def reject_topup(body: RejectTopupIn, x_admin: Optional[str] = Depends(admin_token)):
    require_admin(x_admin, ADMIN_PASS)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE public.asiacell_cards SET status='Rejected'
                WHERE id=%s AND status='Pending'
            """, (body.card_id,))
            if cur.rowcount == 0:
                raise HTTPException(404, "card not found or not pending")
        return {"ok": True}
    finally:
        put_conn(conn)

@app.post("/api/admin/orders/approve")
def admin_approve(body: OrderActionIn, x_admin: Optional[str] = Depends(admin_token)):
    require_admin(x_admin, ADMIN_PASS)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE public.orders SET status='Done' WHERE id=%s", (body.order_id,))
        return {"ok": True}
    finally:
        put_conn(conn)

@app.post("/api/admin/wallet/topup")
def admin_topup(body: WalletOpIn, x_admin: Optional[str] = Depends(admin_token)):
    require_admin(x_admin, ADMIN_PASS)
    if body.amount is None:
        raise HTTPException(400, detail="amount required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            user_id = _get_user_id(cur, body.uid)
            cur.execute("UPDATE public.users SET balance = balance + %s WHERE id=%s", (body.amount, user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s, %s, %s, %s)
            """, (user_id, body.amount, "admin_topup", json.dumps({})))
            cur.execute("SELECT balance FROM public.users WHERE id=%s", (user_id,))
            bal = float(cur.fetchone()[0])
        return {"ok": True, "balance": bal}
    finally:
        put_conn(conn)

@app.post("/api/admin/wallet/deduct")
def admin_deduct(body: WalletOpIn, x_admin: Optional[str] = Depends(admin_token)):
    require_admin(x_admin, ADMIN_PASS)
    if body.amount is None:
        raise HTTPException(400, detail="amount required")
    if body.amount <= 0:
        raise HTTPException(400, detail="amount must be positive")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (body.uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id, bal = r[0], float(r[1])
            if bal < body.amount:
                raise HTTPException(400, detail="insufficient balance")
            cur.execute("UPDATE public.users SET balance = balance - %s WHERE id=%s", (body.amount, user_id))
            cur.execute("""
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s, %s, %s, %s)
            """, (user_id, -body.amount, "admin_deduct", json.dumps({})))
            cur.execute("SELECT balance FROM public.users WHERE id=%s", (user_id,))
            nb = float(cur.fetchone()[0])
        return {"ok": True, "balance": nb}
    finally:
        put_conn(conn)

@app.get("/api/admin/users/count")
def admin_users_count(x_admin: Optional[str] = Depends(admin_token)):
    require_admin(x_admin, ADMIN_PASS)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(1) FROM public.users")
            c = int(cur.fetchone()[0])
        return {"count": c}
    finally:
        put_conn(conn)

@app.get("/api/admin/users/balances")
def admin_users_balances(x_admin: Optional[str] = Depends(admin_token)):
    require_admin(x_admin, ADMIN_PASS)
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT uid, balance FROM public.users ORDER BY uid ASC")
            rows = cur.fetchall()
            return [{"uid": r[0], "balance": float(r[1] or 0.0)} for r in rows]
    finally:
        put_conn(conn)

@app.get("/api/admin/provider/balance")
def admin_provider_balance(x_admin: Optional[str] = Depends(admin_token)):
    require_admin(x_admin, ADMIN_PASS)
    smm = _smm_balance_safe()
    bal = 0.0
    if smm.get("ok"):
        try:
            bal = float(smm["data"].get("balance", 0))
        except Exception:
            bal = 0.0
    return {"balance": bal}

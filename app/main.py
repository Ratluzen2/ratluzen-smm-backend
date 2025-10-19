
import os
import json
import time
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

from fastapi import FastAPI, HTTPException, Header, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# =========================
# Settings
# =========================
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_NEON")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is required")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2000")
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "").strip()
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID", "").strip()  # optional override
OWNER_UID = os.getenv("OWNER_UID", "OWNER-0001").strip()

PROVIDER_API_URL = os.getenv("PROVIDER_API_URL", "https://kd1s.com/api/v2")
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "25a9ceb07be0d8b2ba88e70dcbe92e06")

POOL_MIN, POOL_MAX = 1, int(os.getenv("DB_POOL_MAX", "5"))
dbpool: pool.SimpleConnectionPool = pool.SimpleConnectionPool(POOL_MIN, POOL_MAX, dsn=DATABASE_URL)

def get_conn() -> psycopg2.extensions.connection:
    return dbpool.getconn()

def put_conn(conn: psycopg2.extensions.connection) -> None:
    dbpool.putconn(conn)

# =========================
# Logging
# =========================
logger = logging.getLogger("smm")
logging.basicConfig(level=logging.INFO)

# =========================
# FCM helpers (V1 preferred; Legacy fallback)
# =========================
def _fcm_get_access_token_v1(sa_info: dict) -> Optional[str]:
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request as GoogleRequest
        creds = service_account.Credentials.from_service_account_info(sa_info, scopes=[
            "https://www.googleapis.com/auth/firebase.messaging"
        ])
        creds.refresh(GoogleRequest())
        return creds.token
    except Exception as e:
        logger.info("google-auth not available or failed: %s", e)
    try:
        import jwt, time as _t
        now = int(_t.time())
        payload = {
            "iss": sa_info["client_email"],
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": sa_info.get("token_uri", "https://oauth2.googleapis.com/token"),
            "iat": now,
            "exp": now + 3600,
        }
        signed_jwt = jwt.encode(payload, sa_info["private_key"], algorithm="RS256")
        resp = requests.post(sa_info.get("token_uri", "https://oauth2.googleapis.com/token"),
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed_jwt,
            }, timeout=10)
        if resp.status_code in (200, 201):
            return resp.json().get("access_token")
        else:
            logger.warning("JWT token fetch failed: %s %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.info("pyjwt flow not available or failed: %s", e)
    return None

def _fcm_send_v1(fcm_token: str, title: str, body: str, order_id: Optional[int], sa_info: dict, project_id: Optional[str] = None):
    try:
        access_token = _fcm_get_access_token_v1(sa_info)
        if not access_token:
            logger.warning("FCM v1: could not obtain access token")
            return
        pid = project_id or sa_info.get("project_id")
        if not pid:
            logger.warning("FCM v1: missing project_id")
            return
        url = f"https://fcm.googleapis.com/v1/projects/{pid}/messages:send"
        message = {
            "message": {
                "token": fcm_token,
                "notification": {"title": title, "body": body},
                "data": {"title": title, "body": body, "order_id": str(order_id or "")}
            }
        }
        resp = requests.post(url, headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }, json=message, timeout=10)
        if resp.status_code not in (200, 201):
            logger.warning("FCM v1 send failed (%s): %s", resp.status_code, resp.text[:300])
    except Exception as ex:
        logger.exception("FCM v1 send exception: %s", ex)

def _fcm_send_legacy(fcm_token: str, title: str, body: str, order_id: Optional[int], server_key: str):
    try:
        headers = {"Authorization": f"key={server_key}", "Content-Type": "application/json"}
        payload = {
            "to": fcm_token,
            "priority": "high",
            "notification": {"title": title, "body": body},
            "data": {"title": title, "body": body, "order_id": str(order_id or "")}
        }
        resp = requests.post("https://fcm.googleapis.com/fcm/send", headers=headers, json=payload, timeout=10)
        if resp.status_code not in (200, 201):
            logger.warning("FCM legacy send failed (%s): %s", resp.status_code, resp.text[:300])
    except Exception as ex:
        logger.exception("FCM legacy send exception: %s", ex)

def _fcm_send_push(fcm_token: Optional[str], title: str, body: str, order_id: Optional[int]):
    if not fcm_token:
        return
    sa_json = (GOOGLE_APPLICATION_CREDENTIALS_JSON or "").strip()
    if sa_json:
        try:
            info = json.loads(sa_json)
            _fcm_send_v1(fcm_token, title, body, order_id, info, project_id=(FCM_PROJECT_ID or None))
            return
        except Exception as e:
            logger.info("Invalid GOOGLE_APPLICATION_CREDENTIALS_JSON: %s", e)
    if FCM_SERVER_KEY:
        _fcm_send_legacy(fcm_token, title, body, order_id, FCM_SERVER_KEY)

# =========================
# Schema & Triggers
# =========================
def ensure_schema():
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(987654321)")
                try:
                    cur.execute("CREATE SCHEMA IF NOT EXISTS public;")

                    # users
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.users(
                            id         SERIAL PRIMARY KEY,
                            uid        TEXT UNIQUE NOT NULL,
                            balance    NUMERIC(18,4) NOT NULL DEFAULT 0,
                            is_banned  BOOLEAN NOT NULL DEFAULT FALSE,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            fcm_token  TEXT
                        );
                    """)
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_uid ON public.users(uid);")

                    # devices (multi-token per user)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.user_devices(
                            id BIGSERIAL PRIMARY KEY,
                            uid TEXT NOT NULL,
                            fcm_token TEXT NOT NULL UNIQUE,
                            platform TEXT DEFAULT 'android',
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                    """)
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_devices_uid ON public.user_devices(uid);")

                    # wallet_txns
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.wallet_txns(
                            id         SERIAL PRIMARY KEY,
                            user_id    INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                            amount     NUMERIC(18,4) NOT NULL,
                            reason     TEXT,
                            meta       JSONB,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                    """)
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_wallet_txns_user ON public.wallet_txns(user_id);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_wallet_txns_created ON public.wallet_txns(created_at);")

                    # orders
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.orders(
                            id                 SERIAL PRIMARY KEY,
                            user_id            INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                            title              TEXT NOT NULL,
                            service_id         BIGINT,
                            link               TEXT,
                            quantity           INTEGER NOT NULL DEFAULT 0,
                            price              NUMERIC(18,4) NOT NULL DEFAULT 0,
                            status             TEXT NOT NULL DEFAULT 'Pending',
                            provider_order_id  TEXT,
                            payload            JSONB DEFAULT '{}'::jsonb,
                            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            type               TEXT
                        );
                    """)
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON public.orders(user_id);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON public.orders(status);")
                    cur.execute("ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS type TEXT;")
                    cur.execute("UPDATE public.orders SET type='provider' WHERE type IS NULL;")
                    cur.execute("ALTER TABLE public.orders ALTER COLUMN type SET DEFAULT 'provider';")
                    cur.execute("ALTER TABLE public.orders ALTER COLUMN type SET NOT NULL;")
                    cur.execute("UPDATE public.orders SET payload='{}'::jsonb WHERE payload IS NULL;")

                    # service overrides tables
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.service_id_overrides(
                            ui_key TEXT PRIMARY KEY,
                            service_id BIGINT NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        );
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.service_pricing_overrides(
                            ui_key TEXT PRIMARY KEY,
                            price_per_k NUMERIC(18,6) NOT NULL,
                            min_qty INTEGER NOT NULL,
                            max_qty INTEGER NOT NULL,
                            mode TEXT NOT NULL DEFAULT 'per_k',
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        );
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.order_pricing_overrides(
                            order_id BIGINT PRIMARY KEY,
                            price NUMERIC(18,6) NOT NULL,
                            mode TEXT NOT NULL DEFAULT 'flat',
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        );
                    """)

                    # user_notifications
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.user_notifications(
                            id BIGSERIAL PRIMARY KEY,
                            user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                            order_id INTEGER NULL REFERENCES public.orders(id) ON DELETE SET NULL,
                            title TEXT NOT NULL,
                            body  TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'unread',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            read_at    TIMESTAMPTZ NULL
                        );
                    """)
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_notifications_user_created ON public.user_notifications(user_id, created_at DESC);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_notifications_status ON public.user_notifications(status);")

                    # trigger: notify on wallet_txns insert (skip asiacell_topup or meta.no_notify)
                    cur.execute("""
                        CREATE OR REPLACE FUNCTION public.wallet_txns_notify()
                        RETURNS trigger AS $$
                        DECLARE
                            t TEXT := 'تم تعديل رصيدك';
                            b TEXT;
                        BEGIN
                            IF NEW.reason = 'asiacell_topup' THEN
                                RETURN NEW;
                            END IF;
                            IF NEW.meta IS NOT NULL AND (NEW.meta ? 'no_notify') AND (NEW.meta->>'no_notify')::boolean IS TRUE THEN
                                RETURN NEW;
                            END IF;

                            IF NEW.amount > 0 THEN
                                b := 'تم إضافة ' || NEW.amount::text;
                            ELSIF NEW.amount < 0 THEN
                                b := 'تم خصم ' || ABS(NEW.amount)::text;
                            ELSE
                                RETURN NEW;
                            END IF;

                            INSERT INTO public.user_notifications (user_id, order_id, title, body, status, created_at)
                            VALUES (NEW.user_id, NULL, t, b, 'unread', NOW());

                            RETURN NEW;
                        END;
                        $$ LANGUAGE plpgsql;
                    """)
                    cur.execute("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_trigger WHERE tgname = 'wallet_txns_notify_ai'
                            ) THEN
                                CREATE TRIGGER wallet_txns_notify_ai
                                AFTER INSERT ON public.wallet_txns
                                FOR EACH ROW
                                EXECUTE FUNCTION public.wallet_txns_notify();
                            END IF;
                        END $$;
                    """)

                    # ensure owner row exists
                    cur.execute("INSERT INTO public.users(uid) VALUES(%s) ON CONFLICT (uid) DO NOTHING", (OWNER_UID,))
                finally:
                    cur.execute("SELECT pg_advisory_unlock(987654321)")
    finally:
        put_conn(conn)

ensure_schema()

# =========================
# FastAPI
# =========================
app = FastAPI(title="SMM Backend", version="1.9.6")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# ===== Helpers =====
def _require_admin(passwd: str):
    if passwd != ADMIN_PASSWORD:
        raise HTTPException(401, "bad admin password")

async def _read_json_object(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        raw = (await request.body()).decode("utf-8", errors="ignore").strip()
        data = json.loads(raw) if raw else {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise HTTPException(400, "Body must be a JSON object")
    return data

def _ensure_user(cur, uid: str) -> int:
    cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
    r = cur.fetchone()
    if r:
        return int(r[0])
    cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (uid,))
    return int(cur.fetchone()[0])

def _ensure_owner_user_id(cur) -> int:
    cur.execute("SELECT id FROM public.users WHERE uid=%s", (OWNER_UID,))
    r = cur.fetchone()
    if r and r[0]:
        return int(r[0])
    cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (OWNER_UID,))
    return int(cur.fetchone()[0])

def _tokens_for_uid(cur, uid: str) -> List[str]:
    # prefer multi-device table
    try:
        cur.execute("SELECT fcm_token FROM public.user_devices WHERE uid=%s", (uid,))
        rows = cur.fetchall()
        toks = [r[0] for r in rows if r and r[0]]
        if toks:
            return toks
    except Exception:
        pass
    # fallback to users.fcm_token
    cur.execute("SELECT fcm_token FROM public.users WHERE uid=%s", (uid,))
    r = cur.fetchone()
    return [r[0]] if r and r[0] else []

def _notify_user(_conn_ignored, user_id: int, order_id: Optional[int], title: str, body: str):
    """
    SAFE: open a fresh DB connection (no recursive re-entry).
    Inserts DB notification + pushes FCM to all user's devices.
    """
    c = get_conn()
    try:
        uid = None
        tokens: List[str] = []
        try:
            with c, c.cursor() as cur:
                cur.execute(
                    "INSERT INTO public.user_notifications (user_id, order_id, title, body, status, created_at) VALUES (%s,%s,%s,%s,'unread', NOW())",
                    (user_id, order_id, title, body)
                )
                cur.execute("SELECT uid FROM public.users WHERE id=%s", (user_id,))
                row = cur.fetchone()
                uid = row[0] if row else None
                if uid:
                    tokens = _tokens_for_uid(cur, uid)
        except Exception as e:
            logger.exception("notify user failed (DB): %s", e)

        for t in tokens:
            try:
                _fcm_send_push(t, title, body, order_id)
            except Exception as e:
                logger.exception("notify user push error: %s", e)
    finally:
        put_conn(c)

def _notify_owner_new_order(_conn_ignored, order_id: int):
    """
    SAFE: open fresh connection, insert notification for OWNER, push FCM to owner devices.
    """
    n_title = "طلب جديد"
    n_body  = f"طلب جديد رقم {order_id}"
    c = get_conn()
    try:
        tokens: List[str] = []
        try:
            with c, c.cursor() as cur:
                # enrich with order title + user uid
                try:
                    cur.execute("""
                        SELECT o.title, u.uid
                        FROM public.orders o
                        LEFT JOIN public.users u ON u.id = o.user_id
                        WHERE o.id=%s
                    """, (order_id,))
                    row = cur.fetchone()
                    if row:
                        o_title = row[0] or ""
                        u_uid   = row[1] or ""
                        n_body = f"طلب جديد رقم {order_id}: {o_title}" + (f" | UID: {u_uid}" if u_uid else "")
                except Exception:
                    pass

                owner_id = _ensure_owner_user_id(cur)
                cur.execute(
                    "INSERT INTO public.user_notifications(user_id, order_id, title, body, status, created_at) VALUES (%s,%s,%s,%s,'unread', NOW())",
                    (owner_id, order_id, n_title, n_body)
                )
                tokens = _tokens_for_uid(cur, OWNER_UID)
        except Exception as e:
            logger.exception("owner notify (db) failed: %s", e)

        for t in tokens:
            try:
                _fcm_send_push(t, n_title, n_body, order_id)
            except Exception as e:
                logger.exception("owner notify (push) failed: %s", e)
    finally:
        put_conn(c)

def _needs_code(title: str, otype: Optional[str]) -> bool:
    t = (title or "").lower()
    if (otype or "").lower() == "topup_card":
        return False
    for k in ("itunes","ايتونز","voucher","code","card","gift","رمز","كود","بطاقة","كارت","شراء"):
        if k in t:
            return True
    return False

def _payload_is_jsonb(conn) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_typeof(payload)::text FROM public.orders LIMIT 1")
            row = cur.fetchone()
            return bool(row and isinstance(row[0], str) and row[0].lower() == "jsonb")
    except Exception:
        return False

def _normalize_product(raw: str, fallback_title: str = "") -> str:
    t = (raw or "").strip().lower()
    ft = (fallback_title or "").strip().lower()
    def has_any(s: str, keys: Tuple[str, ...]) -> bool:
        s = s or ""
        return any(k in s for k in keys)
    if has_any(t, ("pubg","bgmi","uc","ببجي","شدات")) or has_any(ft, ("pubg","bgmi","uc","ببجي","شدات")):
        return "pubg_uc"
    if has_any(t, ("ludo_diamond","ludo-diamond","diamonds","الماس","الماسات","لودو")) and not has_any(t, ("gold","ذهب")):
        return "ludo_diamond"
    if has_any(ft, ("الماس","الماسات","diamonds","لودو")) and not has_any(ft, ("gold","ذهب")):
        return "ludo_diamond"
    if has_any(t, ("ludo_gold","gold","ذهب")) or has_any(ft, ("gold","ذهب")):
        return "ludo_gold"
    if has_any(t, ("itunes","ايتونز")) or has_any(ft, ("itunes","ايتونز")):
        return "itunes"
    if has_any(t, ("atheer","اثير")) or has_any(ft, ("atheer","اثير")):
        return "atheer"
    if has_any(t, ("asiacell","اسياسيل","أسيا")) or has_any(ft, ("asiacell","اسياسيل","أسيا")):
        return "asiacell"
    if has_any(t, ("korek","كورك")) or has_any(ft, ("korek","كورك")):
        return "korek"
    return t or "itunes"

def _parse_usd(d: Dict[str, Any]) -> int:
    for k in ("usd","price_usd","priceUsd","price","amount","amt","usd_amount"):
        if k in d and d[k] not in (None, ""):
            try:
                val = int(float(d[k]))
                return val
            except Exception:
                pass
    return 0

# =========================
# Models
# =========================
class UpsertUserIn(BaseModel):
    uid: str

class FcmTokenIn(BaseModel):
    uid: str
    fcm: str
    platform: Optional[str] = "android"

class ProviderOrderIn(BaseModel):
    uid: str
    service_id: Optional[int] = None
    service_name: str
    link: Optional[str] = None
    quantity: int = Field(ge=1, default=1)
    price: float = Field(ge=0, default=0)

class ManualOrderIn(BaseModel):
    uid: str
    title: str

class WalletCompatIn(BaseModel):
    uid: str
    amount: float
    reason: Optional[str] = None

class AsiacellSubmitIn(BaseModel):
    uid: str
    card: str

class TestPushIn(BaseModel):
    title: str = "طلب جديد (اختبار)"
    body: str = "هذا إشعار تجريبي للمالك"
    order_id: Optional[int] = None

# =========================
# Middleware logging
# =========================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    dt = int((time.time() - t0) * 1000)
    logger.info("%s %s -> %s (%d ms)", request.method, request.url.path, response.status_code, dt)
    return response

@app.get("/")
def root():
    return {"ok": True, "msg": "backend running"}

@app.get("/health")
def health():
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return {"ok": True, "ts": int(time.time()*1000)}
    finally:
        put_conn(conn)

# =========================
# Public user APIs
# =========================
@app.post("/api/users/upsert")
def upsert_user(body: UpsertUserIn):
    uid = (body.uid or "").strip()
    if not uid:
        raise HTTPException(422, "uid required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_user(cur, uid)
        return {"ok": True, "uid": uid}
    finally:
        put_conn(conn)

@app.post("/api/users/fcm_token")
def api_users_fcm_token(body: FcmTokenIn):
    uid = (body.uid or "").strip()
    fcm = (body.fcm or "").strip()
    plat = (body.platform or "android").strip().lower()
    if not uid or not fcm:
        raise HTTPException(422, "uid and fcm token required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            user_id = _ensure_user(cur, uid)
            # keep fallback in users
            cur.execute("UPDATE public.users SET fcm_token=%s WHERE id=%s", (fcm, user_id))
            # multi-device table
            cur.execute("""
                INSERT INTO public.user_devices(uid, fcm_token, platform)
                VALUES (%s, %s, %s)
                ON CONFLICT (fcm_token) DO UPDATE
                SET uid=EXCLUDED.uid, platform=COALESCE(EXCLUDED.platform,'android'), updated_at=NOW()
            """, (uid, fcm, plat))
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
        return {"ok": True, "balance": float(r[0] if r else 0.0)}
    finally:
        put_conn(conn)

# aliases
@app.get("/api/get_balance")
def wallet_balance_alias1(uid: str):
    return wallet_balance(uid)

@app.get("/api/balance")
def wallet_balance_alias2(uid: str):
    return wallet_balance(uid)

@app.get("/api/wallet/get")
def wallet_balance_alias3(uid: str):
    return wallet_balance(uid)

@app.get("/api/wallet/get_balance")
def wallet_balance_alias4(uid: str):
    return wallet_balance(uid)

@app.get("/api/users/{uid}/balance")
def wallet_balance_alias5(uid: str):
    return wallet_balance(uid)

# =========================
# Provider orders
# =========================
def _create_provider_order_core(cur, uid: str, service_id: Optional[int], service_name: str,
                                link: Optional[str], quantity: int, price: float) -> int:
    cur.execute("SELECT id, balance, is_banned FROM public.users WHERE uid=%s", (uid,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, "user not found")
    user_id, bal, banned = int(r[0]), float(r[1] or 0), bool(r[2])
    if banned:
        raise HTTPException(403, "user banned")

    eff_sid = service_id
    try:
        if service_name:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.service_id_overrides(
                    ui_key TEXT PRIMARY KEY,
                    service_id BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            cur.execute("SELECT service_id FROM public.service_id_overrides WHERE ui_key=%s", (service_name,))
            r_eff = cur.fetchone()
            if r_eff and r_eff[0]:
                eff_sid = int(r_eff[0])
    except Exception:
        pass

    eff_price = price
    try:
        rowp = None
        if service_name:
            cur.execute("SELECT price_per_k, min_qty, max_qty, COALESCE(mode,'per_k') FROM public.service_pricing_overrides WHERE ui_key=%s", (service_name,))
            rowp = cur.fetchone()
        if rowp:
            ppk = float(rowp[0]); mn = int(rowp[1]); mx = int(rowp[2]); mode = (rowp[3] or 'per_k')
            if mode == 'flat':
                eff_price = float(ppk)
            else:
                if quantity < mn or quantity > mx:
                    raise HTTPException(400, f"quantity out of allowed range [{mn}-{mx}]")
                eff_price = float(Decimal(quantity) * Decimal(ppk) / Decimal(1000))
        else:
            key = None
            sname = (service_name or "").lower()
            if any(w in sname for w in ["pubg","ببجي","uc"]):
                key = "cat.pubg"
            elif any(w in sname for w in ["ludo","لودو"]):
                key = "cat.ludo"
            if key:
                cur.execute("SELECT price_per_k, min_qty, max_qty, COALESCE(mode,'per_k') FROM public.service_pricing_overrides WHERE ui_key=%s", (key,))
                rowp = cur.fetchone()
                if rowp:
                    ppk = float(rowp[0]); mn = int(rowp[1]); mx = int(rowp[2]); mode = (rowp[3] or 'per_k')
                    if mode == 'flat':
                        eff_price = float(ppk)
                    else:
                        if quantity < mn or quantity > mx:
                            raise HTTPException(400, f"quantity out of allowed range [{mn}-{mx}]")
                        eff_price = float(Decimal(quantity) * Decimal(ppk) / Decimal(1000))
    except Exception:
        pass

    if eff_price and eff_price > 0:
        if bal < eff_price:
            raise HTTPException(400, "insufficient balance")
        cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (Decimal(eff_price), user_id))
        cur.execute("""
            INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
            VALUES(%s,%s,%s,%s)
        """, (user_id, Decimal(-eff_price), "order_charge",
              Json({"service_id": service_id, "name": service_name, "qty": quantity, "price_effective": eff_price})))

    cur.execute("""
        INSERT INTO public.orders(user_id, title, service_id, link, quantity, price, status, payload, type)
        VALUES(%s,%s,%s,%s,%s,%s,'Pending',%s,%s)
        RETURNING id
    """, (user_id, service_name, eff_sid, link, quantity, Decimal(eff_price or 0),
          Json({"source": "provider_form", "service_id_provided": service_id, "service_id_effective": eff_sid, "price_effective": eff_price}), 'provider'))
    oid = int(cur.fetchone()[0])
    return oid

@app.post("/api/orders/create/provider")
def create_provider_order(body: ProviderOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            oid = _create_provider_order_core(
                cur, body.uid, body.service_id, body.service_name,
                body.link, body.quantity, body.price
            )
            cur.execute("SELECT user_id, title FROM public.orders WHERE id=%s", (oid,))
            r = cur.fetchone()
            if r:
                _notify_user(conn, int(r[0]), oid, "تم استلام طلبك", f"تم استلام طلب {r[1]}.")
        _notify_owner_new_order(conn, oid)
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

# Compat creation paths
PROVIDER_CREATE_PATHS = [
    "/api/orders/create", "/api/order/create",
    "/api/create/order",  "/api/orders/add",
    "/api/add_order",     "/api/orders/provider/create"
]
def _parse_provider_payload(d: Dict[str, Any]) -> Dict[str, Any]:
    uid = (d.get("uid") or d.get("user_id") or "").strip()
    sv = d.get("service_id", d.get("service", d.get("category_id")))
    service_id = int(sv) if sv not in (None, "", []) else None
    link = d.get("link") or d.get("url") or d.get("target") or None
    qty_raw = d.get("quantity", d.get("qty", d.get("amount", 0)))
    quantity = int(qty_raw or 0)
    price = float(d.get("price", d.get("cost", 0)) or 0)
    service_name = d.get("service_name") or d.get("name") or (f"Service {service_id}" if service_id else "Manual")
    return dict(uid=uid, service_id=service_id, link=link, quantity=quantity, price=price, service_name=service_name)

for path in PROVIDER_CREATE_PATHS:
    @app.post(path)
    async def provider_create_compat(request: Request, _path=path):
        data = await _read_json_object(request)
        try:
            p = _parse_provider_payload(data)
            if not p["uid"] or p["quantity"] <= 0:
                raise ValueError
        except Exception:
            raise HTTPException(422, "invalid payload")
        conn = get_conn()
        try:
            with conn, conn.cursor() as cur:
                oid = _create_provider_order_core(cur, p["uid"], p["service_id"], p["service_name"], p["link"], p["quantity"], p["price"])
                cur.execute("SELECT user_id FROM public.orders WHERE id=%s", (oid,))
                ur = cur.fetchone()
                if ur:
                    _notify_user(conn, int(ur[0]), oid, "تم استلام طلبك", f"تم استلام طلب {p['service_name']}.")
            _notify_owner_new_order(conn, oid)
            return {"ok": True, "order_id": oid}
        finally:
            put_conn(conn)

# =========================
# Manual / Asiacell orders
# =========================
@app.post("/api/orders/create/manual")
def create_manual_order(body: ManualOrderIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            user_id = _ensure_user(cur, body.uid)
            cur.execute("""
                INSERT INTO public.orders(user_id, title, quantity, price, status, payload, type)
                VALUES(%s,%s,0,0,'Pending','{}'::jsonb,'manual')
                RETURNING id
            """, (user_id, body.title))
            oid = int(cur.fetchone()[0])
            _notify_user(conn, user_id, oid, "تم استلام طلبك", f"تم استلام طلب {body.title}.")
        _notify_owner_new_order(conn, oid)
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

def _extract_digits(raw: Any) -> str:
    return "".join(ch for ch in str(raw) if ch.isdigit())

def _asiacell_submit_core(cur, uid: str, card_digits: str) -> int:
    user_id = _ensure_user(cur, uid)
    cur.execute("""
        INSERT INTO public.orders(user_id, title, quantity, price, status, payload, type)
        VALUES(%s,%s,0,0,'Pending', %s, 'topup_card')
        RETURNING id
    """, (user_id, "كارت أسيا سيل", Json({"card": card_digits})))
    return int(cur.fetchone()[0])

ASIACELL_PATHS = [
    "/api/wallet/asiacell/submit",
    "/api/topup/asiacell/submit",
    "/api/asiacell/submit",
    "/api/asiacell/recharge",
    "/api/wallet/asiacell",
    "/api/topup/asiacell",
    "/api/asiacell",
]

@app.post("/api/wallet/asiacell/submit")
def submit_asiacell(body: AsiacellSubmitIn):
    digits = _extract_digits(body.card)
    if len(digits) not in (14, 16):
        raise HTTPException(422, "invalid card length")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            oid = _asiacell_submit_core(cur, body.uid, digits)
            cur.execute("SELECT user_id FROM public.orders WHERE id=%s", (oid,))
            r = cur.fetchone()
            if r:
                _notify_user(conn, int(r[0]), oid, "تم استلام طلبك", "تم استلام طلب كارت أسيا سيل.")
        _notify_owner_new_order(conn, oid)
        return {"ok": True, "order_id": oid, "status": "received"}
    finally:
        put_conn(conn)

for path in ASIACELL_PATHS[1:]:
    @app.post(path)
    async def submit_asiacell_compat(request: Request, _path=path):
        data = await _read_json_object(request)
        uid = (data.get("uid") or data.get("user_id") or "").strip()
        raw = (data.get("card") or data.get("code") or data.get("voucher") or
               data.get("number") or data.get("serial") or
               data.get("recharge_no") or data.get("recharge_number") or
               data.get("value") or data.get("pin") or "")
        digits = _extract_digits(raw)
        if not uid or len(digits) not in (14, 16):
            raise HTTPException(422, "invalid payload")
        conn = get_conn()
        try:
            with conn, conn.cursor() as cur:
                oid = _asiacell_submit_core(cur, uid, digits)
                cur.execute("SELECT user_id FROM public.orders WHERE id=%s", (oid,))
                r = cur.fetchone()
                if r:
                    _notify_user(conn, int(r[0]), oid, "تم استلام طلبك", "تم استلام طلب كارت أسيا سيل.")
            _notify_owner_new_order(conn, oid)
            return {"ok": True, "order_id": oid, "status": "received"}
        finally:
            put_conn(conn)

# =========================
# Orders of a user
# =========================
def _row_to_order_dict(row) -> Dict[str, Any]:
    (oid, title, qty, price, status, created_at, link) = row
    return {
        "id": int(oid), "title": title, "quantity": int(qty or 0),
        "price": float(price or 0), "status": status,
        "created_at": int(created_at or 0), "link": link
    }

def _orders_for_uid(uid: str) -> List[dict]:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                return []
            user_id = int(r[0])
            cur.execute("""
                SELECT id, title, quantity, price,
                       status, EXTRACT(EPOCH FROM created_at)*1000, link
                FROM public.orders
                WHERE user_id=%s
                ORDER BY id DESC
            """, (user_id,))
            rows = cur.fetchall()
        return [_row_to_order_dict(t) for t in rows]
    finally:
        put_conn(conn)

@app.get("/api/orders/my")
def my_orders(uid: str):
    return _orders_for_uid(uid)

@app.get("/api/orders")
def orders_alias(uid: str):
    return _orders_for_uid(uid)

@app.get("/api/user/orders")
def user_orders_alias(uid: str):
    return _orders_for_uid(uid)

@app.get("/api/users/{uid}/orders")
def user_orders_path(uid: str):
    return _orders_for_uid(uid)

@app.get("/api/orders/list")
def orders_list(uid: str):
    return {"orders": _orders_for_uid(uid)}

@app.get("/api/user/orders/list")
def user_orders_list(uid: str):
    return {"orders": _orders_for_uid(uid)}

# =========================
# Notifications
# =========================
@app.get("/api/user/by-uid/{uid}/notifications")
def list_user_notifications(uid: str, status: str = "unread", limit: int = 50):
    conn = get_conn()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                return []
            user_id = int(r["id"])
            where = "WHERE user_id=%s"
            params = [user_id]
            if status not in ("unread","read","all"):
                status = "unread"
            if status != "all":
                where += " AND status=%s"
                params.append(status)
            cur.execute(f"""
                SELECT id, user_id, order_id, title, body, status,
                       EXTRACT(EPOCH FROM created_at)*1000 AS created_at,
                       EXTRACT(EPOCH FROM read_at)*1000   AS read_at
                FROM public.user_notifications
                {where}
                ORDER BY id DESC
                LIMIT %s
            """, (*params, limit))
            return cur.fetchall() or []
    finally:
        put_conn(conn)

@app.get("/api/notifications/by_uid")
def _alias_notifications_by_uid(uid: str, status: str = "unread", limit: int = 50):
    return list_user_notifications(uid=uid, status=status, limit=limit)

@app.post("/api/user/{uid}/notifications/{nid}/read")
def mark_notification_read(uid: str, nid: int):
    conn = get_conn()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = int(r["id"])
            cur.execute(
                "UPDATE public.user_notifications SET status='read', read_at=NOW() WHERE id=%s AND user_id=%s RETURNING id",
                (nid, user_id)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "notification not found")
            return {"ok": True, "id": int(row["id"])}
    finally:
        put_conn(conn)

# =========================
# Manual PAID orders (charge now, refund on reject)
# =========================
class OrderPricingIn(BaseModel):
    order_id: int
    price: Optional[float] = None
    mode: Optional[str] = None

class OrderQtyIn(BaseModel):
    order_id: int
    quantity: int
    reprice: Optional[bool] = False

@app.post("/api/orders/create/manual_paid")
async def create_manual_paid(request: Request):
    data = await _read_json_object(request)
    uid = (data.get("uid") or "").strip()
    product_raw = (data.get("product") or data.get("type") or data.get("category") or data.get("title") or "").strip()
    usd = _parse_usd(data)
    account_id = (data.get("account_id") or data.get("accountId") or data.get("game_id") or "").strip()
    if not uid:
        raise HTTPException(422, "invalid payload")

    product = _normalize_product(product_raw, fallback_title=data.get("title") or "")
    allowed_telco = {5,10,15,20,25,30,40,50,100}
    allowed_pubg = {2,9,15,40,55,100,185}
    allowed_ludo = {5,10,20,35,85,165,475,800}

    if product in ("itunes","atheer","asiacell","korek"):
        if usd not in allowed_telco:
            raise HTTPException(422, "invalid usd for telco/itunes")
    elif product == "pubg_uc":
        if usd not in allowed_pubg:
            raise HTTPException(422, "invalid usd for pubg")
    elif product in ("ludo_diamond","ludo_gold"):
        if usd not in allowed_ludo:
            raise HTTPException(422, "invalid usd for ludo")
    else:
        raise HTTPException(422, "invalid product")

    steps = usd / 5.0
    if product == "itunes":
        price = steps * 9.0
        title = f"شراء رصيد ايتونز {usd}$"
    elif product == "atheer":
        price = steps * 7.0
        title = f"شراء رصيد اثير {usd}$"
    elif product == "asiacell":
        price = steps * 7.0
        title = f"شراء رصيد اسياسيل {usd}$"
    elif product == "korek":
        price = steps * 7.0
        title = f"شراء رصيد كورك {usd}$"
    elif product == "pubg_uc":
        price = float(usd)
        title = f"شحن شدات ببجي بسعر {usd}$"
    elif product == "ludo_diamond":
        price = float(usd)
        title = f"شراء الماسات لودو بسعر {usd}$"
    elif product == "ludo_gold":
        price = float(usd)
        title = f"شراء ذهب لودو بسعر {usd}$"
    else:
        raise HTTPException(422, "invalid product")

    if account_id:
        title = f"{title} | ID: {account_id}"

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, balance, is_banned FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id, 0.0, FALSE", (uid,))
                r = cur.fetchone()
            user_id, bal, banned = int(r[0]), float(r[1] or 0), bool(r[2])
            if banned:
                raise HTTPException(403, "user banned")
            if bal < price:
                raise HTTPException(400, "insufficient balance")

            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (Decimal(price), user_id))
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason, meta) VALUES(%s,%s,%s,%s)",
                (user_id, Decimal(-price), "order_charge", Json({"product": product, "usd": usd, "account_id": account_id}))
            )

            payload = {"product": product, "usd": usd, "charged": float(price)}
            if account_id:
                payload["account_id"] = account_id
            cur.execute(
                """
                INSERT INTO public.orders(user_id, title, quantity, price, status, payload, type)
                VALUES(%s,%s,%s,%s,'Pending',%s,'manual')
                RETURNING id
                """,
                (user_id, title, usd, float(price), Json(payload))
            )
            oid = int(cur.fetchone()[0])

            body_txt = title + (f" | ID: {account_id}" if account_id else "")
            _notify_user(conn, user_id, oid, "تم استلام طلبك", body_txt)
        _notify_owner_new_order(conn, oid)
        return {"ok": True, "order_id": oid, "charged": float(price)}
    finally:
        put_conn(conn)

# =========================
# Approve/Deliver/Reject
# =========================
def _refund_if_needed(cur, user_id: int, price: float, order_id: int):
    if price and price > 0:
        cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (Decimal(price), user_id))
        cur.execute("""
            INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
            VALUES(%s,%s,%s,%s)
        """, (user_id, Decimal(price), "order_refund", Json({"order_id": order_id})))

@app.post("/api/admin/orders/{oid}/approve")
def admin_approve_order(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    body = {}
    try:
        body = json.loads(request._body.decode()) if hasattr(request, "_body") and request._body else {}
    except Exception:
        try:
            body = request._json  # type: ignore
        except Exception:
            body = {}
    if (x_admin_password or password or "") != ADMIN_PASSWORD:
        raise HTTPException(401, "bad admin password")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, service_id, link, quantity, price, status, provider_order_id, title, payload, type
                FROM public.orders WHERE id=%s FOR UPDATE
            """, (oid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "order not found")

            (order_id, user_id, service_id, link, quantity, price, status, provider_order_id, title, payload, otype) = row
            price = float(price or 0)

            if status not in ("Pending", "Processing"):
                raise HTTPException(400, "invalid status")

            if otype in ("topup_card", "manual") or service_id is None:
                cur.execute("UPDATE public.orders SET status='Done' WHERE id=%s", (order_id,))
                return {"ok": True, "status": "Done"}

            try:
                resp = requests.post(
                    PROVIDER_API_URL,
                    data={"key": PROVIDER_API_KEY, "action": "add", "service": str(service_id), "link": link, "quantity": str(quantity)},
                    timeout=25
                )
            except Exception:
                _refund_if_needed(cur, user_id, price, order_id)
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
                return {"ok": False, "status": "Rejected", "reason": "provider_unreachable"}

            if resp.status_code // 100 != 2:
                _refund_if_needed(cur, user_id, price, order_id)
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
                return {"ok": False, "status": "Rejected", "reason": "provider_http"}

            try:
                data = resp.json()
            except Exception:
                _refund_if_needed(cur, user_id, price, order_id)
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
                return {"ok": False, "status": "Rejected", "reason": "bad_provider_json"}

            provider_id = data.get("order") or data.get("order_id")
            if not provider_id:
                _refund_if_needed(cur, user_id, price, order_id)
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))
                return {"ok": False, "status": "Rejected", "reason": "no_provider_id"}

            cur.execute("""
                UPDATE public.orders
                SET provider_order_id=%s, status='Processing'
                WHERE id=%s
            """, (str(provider_id), order_id))
            return {"ok": True, "status": "Processing", "provider_order_id": provider_id}
    finally:
        put_conn(conn)

@app.post("/api/admin/orders/{oid}/deliver")
async def admin_deliver(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    data = await _read_json_object(request)
    if (x_admin_password or password or "") != ADMIN_PASSWORD:
        raise HTTPException(401, "bad admin password")

    code_val = (data.get("code") or "").strip()
    amount   = data.get("amount")

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, user_id, price, status, payload, title, COALESCE(type,'') FROM public.orders WHERE id=%s FOR UPDATE", (oid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "order not found")
            order_id, user_id, price, status, payload, title, otype = row[0], row[1], float(row[2] or 0), row[3], (row[4] or {}), row[5], (row[6] or "")

            if status in ("Done", "Rejected", "Refunded"):
                return {"ok": True, "status": status}

            needs_code = _needs_code(title, otype)
            is_jsonb = _payload_is_jsonb(conn)

            current = {}
            if isinstance(payload, dict):
                current.update(payload)

            if needs_code:
                if not code_val:
                    raise HTTPException(400, "code is required for this order")
                current["card"] = code_val
                current["code"] = code_val

            if (otype or "").lower() == "topup_card" and amount is not None:
                try:
                    current["amount"] = float(amount)
                except Exception:
                    pass

            if current:
                if is_jsonb:
                    cur.execute("UPDATE public.orders SET status='Done', payload=%s WHERE id=%s", (Json(current), order_id))
                else:
                    cur.execute("UPDATE public.orders SET status='Done', payload=(%s)::jsonb::text WHERE id=%s", (json.dumps(current, ensure_ascii=False), order_id))
            else:
                cur.execute("UPDATE public.orders SET status='Done' WHERE id=%s", (order_id,))

            if (otype or "").lower() == "topup_card":
                add = 0.0
                try:
                    add = float(amount or 0)
                except Exception:
                    add = 0.0
                if add > 0:
                    cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (Decimal(add), user_id))
                    cur.execute("""
                        INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                        VALUES(%s,%s,%s,%s)
                    """, (user_id, Decimal(add), "asiacell_topup", Json({"order_id": order_id, "amount": add})))

        title_txt = f"تم تنفيذ طلبك {title or ''}".strip()
        if code_val:
            body_txt = f"الكود: {code_val}"
        elif amount is not None:
            body_txt = f"المبلغ: {amount}"
        else:
            body_txt = title or "تم التنفيذ"

        _notify_user(conn, user_id, order_id, title_txt, body_txt)
        return {"ok": True, "status": "Done"}
    finally:
        put_conn(conn)

@app.post("/api/admin/orders/{oid}/reject")
async def admin_reject(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    data = await _read_json_object(request)
    if (x_admin_password or password or "") != ADMIN_PASSWORD:
        raise HTTPException(401, "bad admin password")
    reason = (data.get("reason") or data.get("message") or "").strip()

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id, user_id, price, status, payload, title, COALESCE(type,'') FROM public.orders WHERE id=%s FOR UPDATE", (oid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "order not found")

            order_id, user_id, price, status, payload, title, otype = row[0], row[1], float(row[2] or 0), row[3], (row[4] or {}), row[5], (row[6] or "")
            if status in ("Done", "Rejected", "Refunded"):
                return {"ok": True, "status": status}

            is_jsonb = _payload_is_jsonb(conn)
            current: Dict[str, Any] = {}
            if isinstance(payload, dict):
                current.update(payload)

            if reason:
                current["reject_reason"] = reason

            already_refunded = bool(current.get("refunded")) if isinstance(current, dict) else False
            if price > 0 and not already_refunded:
                cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (Decimal(price), user_id))
                cur.execute("""
                    INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                    VALUES(%s,%s,%s,%s)
                """, (user_id, Decimal(price), "order_refund", Json({"order_id": order_id, "reject": True})))
                current["refunded"] = True
                current["refunded_amount"] = float(price)

            if current:
                if is_jsonb:
                    cur.execute("UPDATE public.orders SET status='Rejected', payload=%s WHERE id=%s", (Json(current), order_id))
                else:
                    cur.execute("UPDATE public.orders SET status='Rejected', payload=(%s)::jsonb::text WHERE id=%s", (json.dumps(current, ensure_ascii=False), order_id))
            else:
                cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (order_id,))

        _notify_user(conn, user_id, order_id, "تم رفض طلبك", reason or "عذرًا، تم رفض هذا الطلب")
        return {"ok": True, "status": "Rejected"}
    finally:
        put_conn(conn)

# --- Admin aliases ---
@app.post("/api/admin/orders/{oid}/execute")
async def admin_execute_alias(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_deliver(oid, request, x_admin_password, password)

@app.post("/api/admin/card/{oid}/execute")
async def admin_card_execute_alias(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_deliver(oid, request, x_admin_password, password)

@app.post("/api/admin/card/{oid}/reject")
async def admin_card_reject_alias(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_reject(oid, request, x_admin_password, password)

@app.post("/api/admin/topup/{oid}/execute")
async def admin_execute_topup_alias(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_deliver(oid, request, x_admin_password, password)

@app.post("/api/admin/topup/{oid}/reject")
async def admin_reject_topup_alias(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_reject(oid, request, x_admin_password, password)

@app.post("/api/admin/topup_cards/{oid}/execute")
async def admin_execute_topup_cards_alias(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_deliver(oid, request, x_admin_password, password)

@app.post("/api/admin/topup_cards/{oid}/reject")
async def admin_reject_topup_cards_alias(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_reject(oid, request, x_admin_password, password)

@app.post("/api/test/push_owner")
def test_push_owner(p: TestPushIn):
    c = get_conn()
    try:
        with c, c.cursor() as cur:
            owner_id = _ensure_owner_user_id(cur)
            cur.execute(
                "INSERT INTO public.user_notifications(user_id, order_id, title, body, status, created_at) VALUES (%s,%s,%s,%s,'unread', NOW())",
                (owner_id, p.order_id, p.title, p.body)
            )
            toks = _tokens_for_uid(cur, OWNER_UID)
        sent = 0
        for t in toks:
            _fcm_send_push(t, p.title, p.body, p.order_id)
            sent += 1
        return {"ok": True, "sent": sent, "owner_uid": OWNER_UID}
    finally:
        put_conn(c)

# =============== Run local ===============
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)

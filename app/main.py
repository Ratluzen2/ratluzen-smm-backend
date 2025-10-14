
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

from fastapi import FastAPI, HTTPException, Header, Request
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


def _fcm_config_status():
    mode = None
    details = {}
    sa_json = (GOOGLE_APPLICATION_CREDENTIALS_JSON or "").strip()
    if sa_json:
        mode = "v1_service_account"
        try:
            info = json.loads(sa_json)
            details["project_id"] = info.get("project_id") or (FCM_PROJECT_ID or None)
        except Exception as e:
            details["service_account_json_error"] = str(e)
    elif FCM_SERVER_KEY:
        mode = "legacy_server_key"
        details["key_present"] = True
    else:
        mode = "not_configured"
    return {"mode": mode, **details}
logging.basicConfig(level=logging.INFO)


# =========================
# FCM helpers (V1 preferred; Legacy fallback)
# =========================
def _fcm_get_access_token_v1(sa_info: dict) -> Optional[str]:
    """
    Returns OAuth2 access token using google-auth if available; otherwise falls back to manual JWT if PyJWT is installed.
    """
    # Try google-auth first
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

    # Try manual JWT with PyJWT
    try:
        import jwt, time
        now = int(time.time())
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

def _fcm_send_v1(fcm_token: str, title: str, body: str, order_id: Optional[int], sa_info: dict, project_id: Optional[str] = None, extra_data: Optional[dict] = None):
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
                "data": {
                    "title": title,
                    "body": body,
                    "order_id": str(order_id or ""),
                    **(extra_data or {}),
                }
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

def _fcm_send_legacy(fcm_token: str, title: str, body: str, order_id: Optional[int], server_key: str, extra_data: Optional[dict] = None):
    try:
        headers = {
            "Authorization": f"key={server_key}",
            "Content-Type": "application/json"
        }
        payload = {"to": fcm_token, "priority": "high", "notification": {"title": title, "body": body}, "data": {
                "title": title,
                "body": body,
                "order_id": str(order_id or ""),
                    **(extra_data or {}),
            }
        }
        resp = requests.post("https://fcm.googleapis.com/fcm/send", headers=headers, json=payload, timeout=10)
        if resp.status_code not in (200, 201):
            logger.warning("FCM legacy send failed (%s): %s", resp.status_code, resp.text[:300])
    except Exception as ex:
        logger.exception("FCM legacy send exception: %s", ex)

def _fcm_send_push(fcm_token: Optional[str], title: str, body: str, order_id: Optional[int], extra_data: Optional[dict] = None):
    if not fcm_token:
        return
    _cfg = _fcm_config_status()
    if _cfg.get('mode') == 'not_configured':
        logger.warning("FCM not configured: set GOOGLE_APPLICATION_CREDENTIALS_JSON or FCM_SERVER_KEY")
        return
    # Prefer v1 via Service Account JSON stored in env
    sa_json = (GOOGLE_APPLICATION_CREDENTIALS_JSON or "").strip()
    if sa_json:
        try:
            info = json.loads(sa_json)
            _fcm_send_v1(fcm_token, title, body, order_id, info, project_id=(FCM_PROJECT_ID or None), extra_data=extra_data)
            return
        except Exception as e:
            logger.info("Invalid GOOGLE_APPLICATION_CREDENTIALS_JSON: %s", e)
    # Fallback to legacy if configured
    if FCM_SERVER_KEY:
        _fcm_send_legacy(fcm_token, title, body, order_id, FCM_SERVER_KEY, extra_data=extra_data)
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
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        );
                    """)
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_uid ON public.users(uid);")
                    cur.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS fcm_token TEXT;")


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

                    
                        # owner FCM tokens (for admin/owner devices)
                    cur.execute("""
                    CREATE TABLE IF NOT EXISTS public.owner_fcm_tokens(
                        token TEXT PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
                finally:
                    cur.execute("SELECT pg_advisory_unlock(987654321)")
    finally:
        put_conn(conn)

ensure_schema()

# =========================
# FastAPI
# =========================
app = FastAPI(title="SMM Backend", version="1.9.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# ===== Helpers =====
def _require_admin(passwd: str):
    if passwd != ADMIN_PASSWORD:
        raise HTTPException(401, "bad admin password")

def _payload_is_jsonb(conn) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_typeof(payload)::text FROM public.orders LIMIT 1")
            row = cur.fetchone()
            return bool(row and isinstance(row[0], str) and row[0].lower() == "jsonb")
    except Exception:
        return False

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

def _notify_user(conn, user_id: int, order_id: Optional[int], title: str, body: str):
    """
    Insert a notification row AND immediately push an FCM message to the user's device (best-effort).
    """
    fcm_token = None
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.user_notifications (user_id, order_id, title, body, status, created_at)
                    VALUES (%s, %s, %s, %s, 'unread', NOW())
                    """,
                    (user_id, order_id, title, body)
                )
                cur.execute("SELECT fcm_token FROM public.users WHERE id=%s", (user_id,))
                row = cur.fetchone()
                fcm_token = row[0] if row else None
    except Exception as e:
        logger.exception("notify failed (DB): %s", e)

    try:
        _fcm_send_push(fcm_token, title, body, order_id)
    except Exception as e:
        logger.exception("push error (ignored): %s", e)

def _needs_code(title: str, otype: Optional[str]) -> bool:
    t = (title or "").lower()
    if (otype or "").lower() == "topup_card":
        return False
    for k in ("itunes","ايتونز","voucher","code","card","gift","رمز","كود","بطاقة","كارت","شراء"):
        if k in t:
            return True
    return False

# Admin auth compatibility helper
def _pick_admin_password(header_val: Optional[str], password_qs: Optional[str], body: Optional[Dict[str, Any]] = None) -> Optional[str]:
    cand = header_val or password_qs
    if not cand and body:
        cand = body.get("password") or body.get("admin_password") or body.get("x-admin-password")
    return cand

# New helpers (compatibility)
def _normalize_product(raw: str, fallback_title: str = "") -> str:
    t = (raw or "").strip().lower()
    ft = (fallback_title or "").strip().lower()
    def has_any(s: str, keys: Tuple[str, ...]) -> bool:
        s = s or ""
        return any(k in s for k in keys)

    # PUBG UC
    if has_any(t, ("pubg","bgmi","uc","ببجي","شدات")) or has_any(ft, ("pubg","bgmi","uc","ببجي","شدات")):
        return "pubg_uc"
    # Ludo Diamonds
    if has_any(t, ("ludo_diamond","ludo-diamond","diamonds","الماس","الماسات","لودو")) and not has_any(t, ("gold","ذهب")):
        return "ludo_diamond"
    if has_any(ft, ("الماس","الماسات","diamonds","لودو")) and not has_any(ft, ("gold","ذهب")):
        return "ludo_diamond"
    # Ludo Gold
    if has_any(t, ("ludo_gold","gold","ذهب")) or has_any(ft, ("gold","ذهب")):
        return "ludo_gold"
    # iTunes
    if has_any(t, ("itunes","ايتونز")) or has_any(ft, ("itunes","ايتونز")):
        return "itunes"
    # Atheer / Asiacell / Korek balance vouchers
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


def _push_user(conn, user_id: int, order_id: Optional[int], title: str, body: str):
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO public.user_notifications(user_id, order_id, title, body) VALUES(%s,%s,%s,%s)",
                    (user_id, order_id, title, body),
                )
            except Exception:
                # table may not exist yet; ignore insert errors to not break main flow
                pass
            try:
                cur.execute("SELECT fcm_token FROM public.users WHERE id=%s", (user_id,))
                r = cur.fetchone()
                if r and r[0]:
                    try:
                        _fcm_send_push(r[0], title, body, order_id, extra_data=None)
                    except Exception as ex:
                        logger.warning("user fcm send failed: %s", ex)
            except Exception:
                pass
    except Exception as e:
        logger.exception("_push_user failed: %s", e)
def _notify_owners(title: str, body: str, order_id: Optional[int] = None):
    conn = get_conn()
    tokens: List[str] = []
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT token FROM public.owner_fcm_tokens")
            tokens = [r[0] for r in cur.fetchall() or []]
    except Exception as e:
        logger.exception("read owner tokens failed: %s", e)
    finally:
        try: put_conn(conn)
        except Exception: pass
    if not tokens:
        return
    extra = {"for_owner": "1"}
    for tk in tokens:
        try:
            _fcm_send_push(tk, title, body, order_id, extra_data=extra)
        except Exception as ex:
            logger.warning("owner push failed: %s", ex)

# Unified helper to notify all owner devices when an order is created
def _notify_owners_order_created(order_id: int, title: str):
    try:
        logger.info("owner_notify: order_created id=%s title=%s", order_id, title)
    except Exception:
        pass
    try:
        _notify_owners("طلب جديد", f"{title} (ID={order_id}) وصل للمالك.", order_id)
    except Exception as ex:
        logger.warning("owner_notify send failed: %s", ex)


    """Push FCM without inserting a DB notification row (useful when a DB trigger already inserted)."""
    token = None
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT fcm_token FROM public.users WHERE id=%s", (user_id,))
            row = cur.fetchone()
            token = row[0] if row else None
    except Exception as e:
        logger.exception("push_user DB read failed: %s", e)
    try:
        _fcm_send_push(token, title, body, order_id)
    except Exception as e:
        logger.exception("push_user send failed: %s", e)
# =========================
# Models
# =========================
class UpsertUserIn(BaseModel):
    uid: str

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

class WalletChangeIn(BaseModel):
    uid: str
    amount: float

class AsiacellSubmitIn(BaseModel):
    uid: str
    card: str

class WalletCompatIn(BaseModel):
    uid: str
    amount: float
    reason: Optional[str] = None

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
# Internal helpers
# =========================
def _ensure_user(cur, uid: str) -> int:
    cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
    r = cur.fetchone()
    if r:
        return r[0]
    cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (uid,))
    return cur.fetchone()[0]

def _refund_if_needed(cur, user_id: int, price: float, order_id: int):
    # Correctly use the price parameter (eff_price might be used elsewhere).
    if price and price > 0:
        cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (Decimal(price), user_id))
        cur.execute("""
            INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
            VALUES(%s,%s,%s,%s)
        """, (user_id, Decimal(price), "order_refund", Json({"order_id": order_id})))

def _row_to_order_dict(row) -> Dict[str, Any]:
    (oid, title, qty, price, status, created_at, link) = row
    return {
        "id": oid, "title": title, "quantity": qty,
        "price": float(price or 0), "status": status,
        "created_at": int(created_at or 0), "link": link
    }

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


# Endpoint to store FCM token for a UID
class FcmTokenIn(BaseModel):
    uid: str
    fcm: str

@app.post("/api/users/fcm_token")
def api_users_fcm_token(body: FcmTokenIn):
    uid = (body.uid or "").strip()
    fcm = (body.fcm or "").strip()
    if not uid or not fcm:
        raise HTTPException(422, "uid and fcm token required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (uid,))
                user_id = cur.fetchone()[0]
            else:
                user_id = r[0]
            cur.execute("UPDATE public.users SET fcm_token=%s WHERE id=%s", (fcm, user_id))
        return {"ok": True, "uid": uid}
    finally:
        put_conn(conn)
# ---- Wallet balance (with several aliases to match the app) ----
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

# Create provider order core
def _create_provider_order_core(cur, uid: str, service_id: Optional[int], service_name: str,
                                link: Optional[str], quantity: int, price: float) -> int:
    cur.execute("SELECT id, balance, is_banned FROM public.users WHERE uid=%s", (uid,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(404, "user not found")
    user_id, bal, banned = r[0], float(r[1]), bool(r[2])
    if banned:
        raise HTTPException(403, "user banned")

    # apply service-id override by service_name (ui_key)
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

    # apply pricing override by service_name (ui_key)
    eff_price = price
    try:
        rowp = None
        if service_name:
            cur.execute("SELECT price_per_k, min_qty, max_qty, COALESCE(mode,'per_k') FROM public.service_pricing_overrides WHERE ui_key=%s", (service_name,))
            rowp = cur.fetchone()

        # compute price based on mode
        if rowp:
            ppk = float(rowp[0]); mn = int(rowp[1]); mx = int(rowp[2]); mode = (rowp[3] or 'per_k')
            if mode == 'flat':
                eff_price = float(ppk)
            else:
                if quantity < mn or quantity > mx:
                    raise HTTPException(400, f"quantity out of allowed range [{mn}-{mx}]")
                eff_price = float(Decimal(quantity) * Decimal(ppk) / Decimal(1000))

        if not rowp:
            # category-level fallback for PUBG/Ludo
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
        # keep original price if anything fails
        pass

    # charge if paid (use effective price)
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
    oid = cur.fetchone()[0]
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
            # Notify
            cur.execute("SELECT user_id, title FROM public.orders WHERE id=%s", (oid,))
            r = cur.fetchone()
            if r:
                _notify_user(conn, r[0], oid, "تم استلام طلبك", f"تم استلام طلب {r[1]}.")
        
        _notify_owners_order_created(oid, f"طلب {p['service_name']}")
        _notify_owners_order_created(oid, 'طلب يدوي مدفوع')
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
                    _notify_user(conn, ur[0], oid, "تم استلام طلبك", f"تم استلام طلب {p['service_name']}.")
                _notify_owners("طلب جديد", f"طلب {p['service_name']} (ID={oid}) وصل للمالك.", oid)
            return {"ok": True, "order_id": oid}
        finally:
            put_conn(conn)

# Manual order
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
            oid = cur.fetchone()[0]
        _notify_user(conn, user_id, oid, "تم استلام طلبك", f"تم استلام طلب {body.title}.")
        _notify_owners("طلب جديد", f"طلب {body.title} (ID={oid}) وصل للمالك.", oid)
        return {"ok": True, "order_id": oid}
    finally:
        put_conn(conn)

# Asiacell submit (topup via card)
def _asiacell_submit_core(cur, uid: str, card_digits: str) -> int:
    user_id = _ensure_user(cur, uid)
    cur.execute("""
        INSERT INTO public.orders(user_id, title, quantity, price, status, payload, type)
        VALUES(%s,%s,0,0,'Pending', %s, 'topup_card')
        RETURNING id
    """, (user_id, "كارت أسيا سيل", Json({"card": card_digits})))
    return cur.fetchone()[0]

def _extract_digits(raw: Any) -> str:
    return "".join(ch for ch in str(raw) if ch.isdigit())

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
                _notify_user(conn, r[0], oid, "تم استلام طلبك", "تم استلام طلب كارت أسيا سيل.")
        
        _notify_owners_order_created(oid, f"طلب {p['service_name']}")
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
                    _notify_user(conn, r[0], oid, "تم استلام طلبك", "تم استلام طلب كارت أسيا سيل.")
                _notify_owners("طلب جديد", f"طلب كارت أسيا سيل (ID={oid}) وصل للمالك.", oid)
            return {"ok": True, "order_id": oid, "status": "received"}
        finally:
            put_conn(conn)

# Orders of a user
def _orders_for_uid(uid: str) -> List[dict]:
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                return []
            user_id = r[0]
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

# more aliases for safety
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
            user_id = r["id"]
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

@app.post("/api/user/{uid}/notifications/{nid}/read")
def mark_notification_read(uid: str, nid: int):
    conn = get_conn()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = r["id"]
            cur.execute(
                "UPDATE public.user_notifications SET status='read', read_at=NOW() WHERE id=%s AND user_id=%s RETURNING id",
                (nid, user_id)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "notification not found")
            return {"ok": True, "id": row["id"]}
    finally:
        put_conn(conn)

# =========================
# Manual PAID orders (charge now, refund on reject)
# =========================
@app.post("/api/orders/create/manual_paid")
async def create_manual_paid(request: Request):
    """
    Creates a manual order (iTunes / Atheer / Asiacell / Korek / PUBG / Ludo) and atomically charges user balance.
    Body (flexible):
      {
        uid: str,
        product: "itunes"|"atheer"|"asiacell"|"korek"|"pubg_uc"|"ludo_diamond"|"ludo_gold" | Arabic labels,
        usd|price|priceUsd|price_usd|amount: int,
        account_id|accountId|game_id?: str
      }

    Pricing:
      - itunes:   each 5$ = 9$
      - atheer:   each 5$ = 7$
      - asiacell: each 5$ = 7$
      - korek:    each 5$ = 7$
      - pubg_uc:  price = usd (allowed {2,9,15,40,55,100,185})
      - ludo_*:   price = usd (allowed {5,10,20,35,85,165,475,800})

    Refund: if owner rejects later, /api/admin/orders/{id}/reject auto-refunds price>0.
    """
    data = await _read_json_object(request)
    uid = (data.get("uid") or "").strip()
    product_raw = (data.get("product") or data.get("type") or data.get("category") or data.get("title") or "").strip()
    usd = _parse_usd(data)

    # Player account / game id (optional but stored)
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

    # Pricing & title
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
            # ensure user & balance
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

            # charge
            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (Decimal(price), user_id))
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason, meta) VALUES(%s,%s,%s,%s)",
                (user_id, Decimal(-price), "order_charge", Json({"product": product, "usd": usd, "account_id": account_id}))
            )

            # create pending manual order carrying the price for future refund if rejected
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
            oid = cur.fetchone()[0]

        # optional: immediate user notification (order received)
        body = title + (f" | ID: {account_id}" if account_id else "")
        _notify_user(conn, user_id, oid, "تم استلام طلبك", body)

        
        _notify_owners_order_created(oid, f"طلب {p['service_name']}")
        return {"ok": True, "order_id": oid, "charged": float(price)}
    finally:
        put_conn(conn)

# Additional compat aliases for manual_paid (covering multiple potential paths from the app)
@app.post("/api/create/manual_paid")
async def create_manual_paid_alias1(request: Request):
    return await create_manual_paid(request)

@app.post("/api/orders/manual_paid/create")
async def create_manual_paid_alias2(request: Request):
    return await create_manual_paid(request)

@app.post("/api/orders/create/manual-paid")
async def create_manual_paid_alias3(request: Request):
    return await create_manual_paid(request)

@app.post("/api/createManualPaidOrder")
async def create_manual_paid_alias4(request: Request):
    return await create_manual_paid(request)

@app.post("/api/orders/createManualPaid")
async def create_manual_paid_alias5(request: Request):
    return await create_manual_paid(request)

@app.post("/api/orders/createManualPaidOrder")
async def create_manual_paid_alias6(request: Request):
    return await create_manual_paid(request)

@app.post("/api/manual_paid")
async def create_manual_paid_alias7(request: Request):
    return await create_manual_paid(request)

@app.post("/api/orders/manualPaid")
async def create_manual_paid_alias8(request: Request):
    return await create_manual_paid(request)

# =========================
# Approve/Deliver/Reject
# =========================
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
    _require_admin(_pick_admin_password(x_admin_password, password, body) or "")
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

            # manual/topup_card doesn't call provider
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
    _require_admin(_pick_admin_password(x_admin_password, password, data) or "")

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

            # Persist order as Done
            if current:
                if is_jsonb:
                    cur.execute("UPDATE public.orders SET status='Done', payload=%s WHERE id=%s", (Json(current), order_id))
                else:
                    cur.execute("UPDATE public.orders SET status='Done', payload=(%s)::jsonb::text WHERE id=%s", (json.dumps(current, ensure_ascii=False), order_id))
            else:
                cur.execute("UPDATE public.orders SET status='Done' WHERE id=%s", (order_id,))

            # Credit wallet for Asiacell direct topup (topup_card type)
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

        # Build notification
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

# Aliases for deliver / reject to match various admin clients
@app.post("/api/admin/orders/{oid}/execute")
async def admin_execute_alias(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_deliver(oid, request, x_admin_password, password)

@app.post("/api/admin/card/{oid}/execute")
async def admin_card_execute_alias(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_deliver(oid, request, x_admin_password, password)

@app.post("/api/admin/orders/{oid}/reject")
async def admin_reject(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    """
    Rejects the order and refunds balance once if order is paid.
    """
    data = await _read_json_object(request)
    _require_admin(_pick_admin_password(x_admin_password, password, data) or "")
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
                cur.execute(
                    """
                    INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                    VALUES(%s,%s,%s,%s)
                    """,
                    (user_id, Decimal(price), "order_refund", Json({"order_id": order_id, "reject": True}))
                )
                current["refunded"] = True
                current["refunded_amount"] = float(price)

            # Persist status & payload
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

@app.post("/api/admin/card/{oid}/reject")
async def admin_card_reject_alias(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_reject(oid, request, x_admin_password, password)

# =========================
# Admin pending buckets
# =========================

@app.get("/api/admin/pending/itunes")
def admin_pending_itunes(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    _require_admin(x_admin_password or password or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT o.id, o.title, o.quantity, o.price, o.status,
                       EXTRACT(EPOCH FROM o.created_at)*1000 AS created_at,
                       o.link, u.uid
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE o.status='Pending'
                  AND (LOWER(o.title) LIKE '%itunes%' OR o.title LIKE '%ايتونز%')
                ORDER BY o.id DESC
            """)
            rows = cur.fetchall()
        out = []
        for (oid, title, qty, price, status, created_at, link, uid) in rows:
            d = _row_to_order_dict((oid, title, qty, price, status, created_at, link))
            d["uid"] = uid
            out.append(d)
        return out
    finally:
        put_conn(conn)

@app.get("/api/admin/pending/pubg")
def admin_pending_pubg(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    _require_admin(x_admin_password or password or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT o.id, o.title, o.quantity, o.price, o.status,
                       EXTRACT(EPOCH FROM o.created_at)*1000 AS created_at,
                       o.link, u.uid,
                       COALESCE((COALESCE(NULLIF(o.payload,''),'{}')::jsonb->>'account_id'),'') AS account_id
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE o.status='Pending' AND (
                LOWER(o.title) LIKE '%pubg%' OR
                LOWER(o.title) LIKE '%bgmi%' OR
                LOWER(o.title) LIKE '%uc%' OR
                o.title LIKE '%شدات%' OR
                o.title LIKE '%بيجي%' OR
                o.title LIKE '%ببجي%'
            )
                ORDER BY o.id DESC
            """)
            rows = cur.fetchall()
        out = []
        for (oid, title, qty, price, status, created_at, link, uid, account_id) in rows:
            d = _row_to_order_dict((oid, title, qty, price, status, created_at, link))
            d["uid"] = uid
            if account_id:
                d["account_id"] = account_id
            out.append(d)
        return out
    finally:
        put_conn(conn)

@app.get("/api/admin/pending/ludo")
def admin_pending_ludo(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    _require_admin(x_admin_password or password or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT o.id, o.title, o.quantity, o.price, o.status,
                       EXTRACT(EPOCH FROM o.created_at)*1000 AS created_at,
                       o.link, u.uid,
                       COALESCE((COALESCE(NULLIF(o.payload,''),'{}')::jsonb->>'account_id'),'') AS account_id
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE o.status='Pending' AND (
                LOWER(o.title) LIKE '%ludo%' OR
                LOWER(o.title) LIKE '%yalla%' OR
                o.title LIKE '%يلا لودو%' OR
                o.title LIKE '%لودو%'
            )
                ORDER BY o.id DESC
            """)
            rows = cur.fetchall()
        out = []
        for (oid, title, qty, price, status, created_at, link, uid, account_id) in rows:
            d = _row_to_order_dict((oid, title, qty, price, status, created_at, link))
            d["uid"] = uid
            if account_id:
                d["account_id"] = account_id
            out.append(d)
        return out
    finally:
        put_conn(conn)

# Pending topup cards (Asiacell via card)
@app.get("/api/admin/pending/cards")
def admin_pending_cards(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    _require_admin(x_admin_password or password or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT o.id, u.uid, COALESCE((COALESCE(NULLIF(o.payload,''),'{}')::jsonb->>'card'), '') AS card,
                       EXTRACT(EPOCH FROM o.created_at)*1000 AS created_at
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE o.status='Pending' AND o.type='topup_card'
                ORDER BY o.id DESC
            """)
            rows = cur.fetchall()
        return [{"id": r[0], "uid": r[1], "card": r[2], "created_at": int(r[3] or 0)} for r in rows]
    finally:
        put_conn(conn)

# Pending balance purchase (Atheer/Asiacell/Korek vouchers)
@app.get("/api/admin/pending/balances")
def admin_pending_balances(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    _require_admin(x_admin_password or password or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(r"""
                SELECT o.id, o.title, o.quantity, o.price, o.status,
                       EXTRACT(EPOCH FROM o.created_at)*1000 AS created_at,
                       o.link, u.uid
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE o.status='Pending'
                  AND (
                        LOWER(o.title) LIKE '%asiacell%' OR
                        o.title LIKE '%أسيا%' OR
                        o.title LIKE '%اسياسيل%' OR
                        LOWER(o.title) LIKE '%korek%' OR
                        o.title LIKE '%كورك%' OR
                        o.title LIKE '%اثير%'
                  )
                  AND (
                        LOWER(o.title) LIKE '%voucher%' OR
                        LOWER(o.title) LIKE '%code%' OR
                        LOWER(o.title) LIKE '%card%' OR
                        o.title LIKE '%رمز%' OR
                        o.title LIKE '%كود%' OR
                        o.title LIKE '%بطاقة%' OR
                        o.title LIKE '%كارت%' OR
                        o.title LIKE '%شراء%'
                  )
                  AND (o.type IS NULL OR o.type <> 'topup_card')
                  AND NOT (
                        LOWER(o.title) LIKE '%topup%' OR
                        LOWER(o.title) LIKE '%top-up%' OR
                        LOWER(o.title) LIKE '%recharge%' OR
                        o.title LIKE '%شحن%' OR
                        o.title LIKE '%شحن عبر%' OR
                        o.title LIKE '%شحن اسيا%' OR
                        LOWER(o.title) LIKE '%direct%'
                  )
                  AND NOT (
                        LOWER(o.title) LIKE '%itunes%' OR
                        o.title LIKE '%ايتونز%'
                  )
                ORDER BY o.id DESC
            """)
            rows = cur.fetchall()
        out = []
        for (oid, title, qty, price, status, created_at, link, uid) in rows:
            d = _row_to_order_dict((oid, title, qty, price, status, created_at, link))
            d["uid"] = uid
            out.append(d)
        return out
    finally:
        put_conn(conn)

# =========================
# Admin: pending API services (compact list for Android UI)
# =========================
@app.get("/api/admin/pending/services")
def admin_pending_services_endpoint(
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None,
    limit: int = 100
):
    _require_admin(x_admin_password or password or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT
                    o.id,
                    o.created_at,
                    COALESCE(o.status, 'Pending') AS status,
                    o.title,
                    o.quantity,
                    o.price,
                    o.link,
                    u.uid,
                    o.service_id,
                    o.type,
                    o.payload
                FROM public.orders o
                JOIN public.users u ON u.id = o.user_id
                WHERE COALESCE(o.status, 'Pending') = 'Pending'
                ORDER BY COALESCE(o.created_at, NOW()) DESC
                LIMIT %s
            """, (int(limit),))
            rows = cur.fetchall()

        out: List[Dict[str, Any]] = []
        for (oid, created_at, status, title, qty, price, link, uid, service_id, otype, payload) in rows:
            # Only API/provider-like
            typ = str(otype or "").lower()
            is_api = typ in ("provider","api","smm","service") or (isinstance(payload, dict) and str(payload.get("source","")).lower()=="provider_form") or (service_id is not None)
            if not is_api:
                continue
            try:
                created_ms = int(created_at.timestamp() * 1000)
            except Exception:
                created_ms = int(time.time() * 1000)
            out.append({
                "id": int(oid),
                "title": str(title or "—"),
                "quantity": int(qty or 0),
                "price": float(price or 0),
                "link": link or "",
                "status": "Pending",
                "created_at": created_ms,
                "uid": uid or "",
                "account_id": (payload or {}).get("account_id") if isinstance(payload, dict) else ""
            })
        return {"list": out}
    finally:
        put_conn(conn)

# =========================
# Admin: wallet adjust + compatibility
# =========================
@app.post("/api/admin/users/{uid}/wallet/adjust")
async def admin_wallet_adjust(uid: str, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    data = await _read_json_object(request)
    _require_admin(_pick_admin_password(x_admin_password, password, data) or "")

    amount = data.get("amount")
    reason = (data.get("reason") or "manual_adjust").strip()
    no_notify = bool(data.get("no_notify") or False)

    if amount is None:
        raise HTTPException(400, "amount is required")
    try:
        amt = float(amount)
    except Exception:
        raise HTTPException(400, "amount must be a number")
    if amt == 0:
        return {"ok": True, "status": "noop"}

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = r[0]

            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (Decimal(amt), user_id))

            meta = {"admin": True}
            if no_notify:
                meta["no_notify"] = True
            cur.execute(
                """
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s,%s,%s,%s)
                """,
                (user_id, Decimal(amt), reason, Json(meta))
            )

        return {"ok": True, "status": "adjusted", "amount": amt, "reason": reason}
    finally:
        put_conn(conn)

# Single "change" endpoint (positive = topup, negative = deduct) to match older apps
@app.post("/api/admin/wallet/change")
async def admin_wallet_change(request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    data = await _read_json_object(request)
    _require_admin(_pick_admin_password(x_admin_password, password, data) or "")
    uid = (data.get("uid") or "").strip()
    if not uid:
        raise HTTPException(400, "uid required")
    try:
        amount = float(data.get("amount"))
    except Exception:
        raise HTTPException(400, "amount must be number")

    direction = "topup" if amount >= 0 else "deduct"
    if direction == "deduct":
        body = WalletCompatIn(uid=uid, amount=abs(amount), reason=data.get("reason"))
        return admin_wallet_deduct(body, x_admin_password or password or "")
    else:
        body = WalletCompatIn(uid=uid, amount=amount, reason=data.get("reason"))
        return admin_wallet_topup(body, x_admin_password or password or "")

@app.post("/api/admin/wallet/topup")
def admin_wallet_topup(body: WalletCompatIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    _require_admin(x_admin_password or password or "")
    uid = (body.uid or "").strip()
    if not uid:
        raise HTTPException(400, "uid required")
    try:
        amt = float(body.amount)
    except Exception:
        raise HTTPException(400, "amount must be number")
    if amt <= 0:
        raise HTTPException(400, "amount must be > 0")

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                cur.execute("INSERT INTO public.users(uid) VALUES(%s) RETURNING id", (uid,))
                user_id = cur.fetchone()[0]
            else:
                user_id = r[0]

            cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (Decimal(amt), user_id))
            cur.execute(
                """
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s,%s,%s,%s)
                """,
                (user_id, Decimal(amt), body.reason or "manual_topup", Json({"compat": "topup"}))
            )
        _push_user(conn, user_id, None, "تمت إضافة رصيد", f"تمت إضافة {amt} إلى رصيدك.")
        return {"ok": True, "status": "adjusted", "amount": amt, "direction": "topup"}
    finally:
        put_conn(conn)

@app.post("/api/admin/wallet/deduct")
def admin_wallet_deduct(body: WalletCompatIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    _require_admin(x_admin_password or password or "")
    uid = (body.uid or "").strip()
    if not uid:
        raise HTTPException(400, "uid required")
    try:
        amt = float(body.amount)
    except Exception:
        raise HTTPException(400, "amount must be number")
    if amt <= 0:
        raise HTTPException(400, "amount must be > 0")

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = r[0]

            cur.execute("UPDATE public.users SET balance=balance-%s WHERE id=%s", (Decimal(amt), user_id))
            cur.execute(
                """
                INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
                VALUES(%s,%s,%s,%s)
                """,
                (user_id, Decimal(-amt), body.reason or "manual_deduct", Json({"compat": "deduct"}))
            )
        _push_user(conn, user_id, None, "تم خصم رصيد", f"تم خصم {amt} من رصيدك.")
        return {"ok": True, "status": "adjusted", "amount": -amt, "direction": "deduct"}
    finally:
        put_conn(conn)

# =========================
# Admin stats: users count & balances
# =========================
@app.get("/api/admin/users/count")
def admin_users_count(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None, plain: int = 0):
    _require_admin(x_admin_password or password or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.users")
            n = int(cur.fetchone()[0])
        if str(plain) == "1":
            return n
        return {"ok": True, "count": n}
    finally:
        put_conn(conn)

@app.get("/api/admin/users/balances")
def admin_users_balances(
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None,
    q: str = "", limit: int = 100, offset: int = 0, sort: str = "balance_desc"
):
    """
    DEFAULT: returns a JSON ARRAY for UI compatibility.
    """
    _require_admin(x_admin_password or password or "")

    q = (q or "").strip()
    try:
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
    except Exception:
        limit, offset = 100, 0

    sort_map = {
        "balance_desc": "balance DESC",
        "balance_asc": "balance ASC",
        "created_desc": "created_at DESC",
        "created_asc": "created_at ASC",
        "uid_asc": "uid ASC",
        "uid_desc": "uid DESC",
    }
    order_by = sort_map.get(sort, "balance DESC")

    where = "WHERE TRUE"
    params = []
    if q:
        where += " AND (uid ILIKE %s)"
        params.append(f"%{q}%")

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, uid, balance, is_banned,
                       EXTRACT(EPOCH FROM created_at)*1000 AS created_at
                FROM public.users
                {where}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
                """,
                (*params, limit, offset)
            )
            rows = cur.fetchall()

        items = [
            {
                "id": r[0],
                "uid": r[1],
                "balance": float(r[2] or 0),
                "is_banned": bool(r[3]),
                "created_at": int(r[4] or 0),
            } for r in rows
        ]
        # Return ARRAY directly
        return items
    finally:
        put_conn(conn)

@app.get("/api/admin/users/balances_meta")
def admin_users_balances_meta(
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None,
    q: str = "", limit: int = 100, offset: int = 0, sort: str = "balance_desc"
):
    _require_admin(x_admin_password or password or "")

    q = (q or "").strip()
    try:
        limit_val = max(1, min(int(limit), 500))
        offset_val = max(0, int(offset))
    except Exception:
        limit_val, offset_val = 100, 0

    sort_map = {
        "balance_desc": "balance DESC",
        "balance_asc": "balance ASC",
        "created_desc": "created_at DESC",
        "created_asc": "created_at ASC",
        "uid_asc": "uid ASC",
        "uid_desc": "uid DESC",
    }
    order_by = sort_map.get(sort, "balance DESC")

    where = "WHERE TRUE"
    params = []
    if q:
        where += " AND (uid ILIKE %s)"
        params.append(f"%{q}%")

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM public.users {where}", params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f"""
                SELECT id, uid, balance, is_banned,
                       EXTRACT(EPOCH FROM created_at)*1000 AS created_at
                FROM public.users
                {where}
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
                """,
                (*params, limit_val, offset_val)
            )
            rows = cur.fetchall()
        items = [
            {
                "id": r[0],
                "uid": r[1],
                "balance": float(r[2] or 0),
                "is_banned": bool(r[3]),
                "created_at": int(r[4] or 0),
            } for r in rows
        ]
        return {
            "ok": True,
            "total": total,
            "limit": limit_val,
            "offset": offset_val,
            "sort": sort,
            "items": items,
            "data": items,
            "total_users": total
        }
    finally:
        put_conn(conn)

# =========================
# Service ID overrides (server-level)
# =========================
class SvcOverrideIn(BaseModel):
    ui_key: str
    service_id: Optional[int] = None

def _ensure_overrides_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.service_id_overrides(
            ui_key TEXT PRIMARY KEY,
            service_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

@app.get("/api/admin/service_ids/list")
def admin_list_service_ids(
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None
):
    _require_admin(x_admin_password or password or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_overrides_table(cur)
            cur.execute("SELECT ui_key, service_id FROM public.service_id_overrides ORDER BY ui_key")
            rows = cur.fetchall()
            return {"list": [{"ui_key": r[0], "service_id": int(r[1])} for r in rows]}
    finally:
        put_conn(conn)

@app.post("/api/admin/service_ids/set")
def admin_set_service_id(
    body: SvcOverrideIn,
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None
):
    _require_admin(x_admin_password or password or "")
    if not body.ui_key or not body.service_id or int(body.service_id) <= 0:
        raise HTTPException(422, "invalid payload")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_overrides_table(cur)
            cur.execute("""
                INSERT INTO public.service_id_overrides(ui_key, service_id)
                VALUES(%s,%s)
                ON CONFLICT (ui_key) DO UPDATE SET service_id=EXCLUDED.service_id, created_at=now()
            """, (body.ui_key, int(body.service_id)))
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.owner_fcm_tokens")
            c = cur.fetchone()[0]
        return {"ok": True, "owner_tokens": int(c)}
    finally:
        put_conn(conn)

@app.post("/api/admin/service_ids/clear")
def admin_clear_service_id(
    body: SvcOverrideIn,
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None
):
    _require_admin(x_admin_password or password or "")
    if not body.ui_key:
        raise HTTPException(422, "invalid payload")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_overrides_table(cur)
            cur.execute("DELETE FROM public.service_id_overrides WHERE ui_key=%s", (body.ui_key,))
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.owner_fcm_tokens")
            c = cur.fetchone()[0]
        return {"ok": True, "owner_tokens": int(c)}
    finally:
        put_conn(conn)

# =========================
# Pricing overrides (server-level)
# =========================
class PricingIn(BaseModel):
    ui_key: str
    price_per_k: Optional[float] = None
    min_qty: Optional[int] = None
    max_qty: Optional[int] = None
    mode: Optional[str] = None  # 'per_k' (default) or 'flat'

def _ensure_pricing_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.service_pricing_overrides(
            ui_key TEXT PRIMARY KEY,
            price_per_k NUMERIC(18,6) NOT NULL,
            min_qty INTEGER NOT NULL,
            max_qty INTEGER NOT NULL,
            mode TEXT NOT NULL DEFAULT 'per_k',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

def _ensure_pricing_mode_column(cur):
    try:
        cur.execute("ALTER TABLE public.service_pricing_overrides ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'per_k'")
    except Exception:
        pass

@app.get("/api/admin/pricing/list")
def admin_list_pricing(
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None
):
    _require_admin(x_admin_password or password or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_pricing_table(cur)
            cur.execute("SELECT ui_key, price_per_k, min_qty, max_qty, COALESCE(mode, 'per_k') FROM public.service_pricing_overrides ORDER BY ui_key")
            rows = cur.fetchall()
            out = [{"ui_key": r[0], "price_per_k": float(r[1]), "min_qty": int(r[2]), "max_qty": int(r[3]), "mode": (r[4] or "per_k")} for r in rows]
            return {"list": out}
    finally:
        put_conn(conn)

@app.post("/api/admin/pricing/set")
def admin_set_pricing(
    body: PricingIn,
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None
):
    _require_admin(x_admin_password or password or "")
    if not body.ui_key or body.price_per_k is None or body.min_qty is None or body.max_qty is None:
        raise HTTPException(422, "invalid payload")
    if body.min_qty < 0 or body.max_qty < body.min_qty:
        raise HTTPException(422, "invalid range")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_pricing_table(cur)
            _ensure_pricing_mode_column(cur)
            cur.execute("""
                INSERT INTO public.service_pricing_overrides(ui_key, price_per_k, min_qty, max_qty, mode, updated_at)
                VALUES(%s,%s,%s,%s,COALESCE(%s,'per_k'), now())
                ON CONFLICT (ui_key) DO UPDATE SET price_per_k=EXCLUDED.price_per_k, min_qty=EXCLUDED.min_qty, max_qty=EXCLUDED.max_qty, mode=COALESCE(EXCLUDED.mode,'per_k'), updated_at=now()
            """, (body.ui_key, Decimal(body.price_per_k), int(body.min_qty), int(body.max_qty), (body.mode or 'per_k')))
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.owner_fcm_tokens")
            c = cur.fetchone()[0]
        return {"ok": True, "owner_tokens": int(c)}
    finally:
        put_conn(conn)

@app.post("/api/admin/pricing/clear")
def admin_clear_pricing(
    body: PricingIn,
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None
):
    _require_admin(x_admin_password or password or "")
    if not body.ui_key:
        raise HTTPException(422, "invalid payload")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_pricing_table(cur)
            _ensure_pricing_mode_column(cur)
            cur.execute("DELETE FROM public.service_pricing_overrides WHERE ui_key=%s", (body.ui_key,))
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.owner_fcm_tokens")
            c = cur.fetchone()[0]
        return {"ok": True, "owner_tokens": int(c)}
    finally:
        put_conn(conn)


# ------------------------------
# Public pricing (read-only for clients)
# ------------------------------
@app.get("/api/public/pricing/version")
def public_pricing_version():
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_pricing_table(cur)
            try:
                _ensure_pricing_mode_column(cur)
            except Exception:
                pass
            cur.execute("SELECT COALESCE(EXTRACT(EPOCH FROM MAX(updated_at))*1000, 0) FROM public.service_pricing_overrides")
            v = cur.fetchone()[0] or 0
            return {"version": int(v)}
    finally:
        put_conn(conn)

@app.get("/api/public/pricing/bulk")
def public_pricing_bulk(keys: str):
    if not keys:
        return {"map": {}, "keys": []}
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    if not key_list:
        return {"map": {}, "keys": []}
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_pricing_table(cur)
            try:
                _ensure_pricing_mode_column(cur)
            except Exception:
                pass
            cur.execute(
                "SELECT ui_key, price_per_k, min_qty, max_qty, COALESCE(mode,'per_k'), EXTRACT(EPOCH FROM updated_at)*1000 FROM public.service_pricing_overrides WHERE ui_key = ANY(%s)",
                (key_list,)
            )
            rows = cur.fetchall()
            out = {}
            for r in rows:
                out[r[0]] = {
                    "price_per_k": float(r[1]),
                    "min_qty": int(r[2]),
                    "max_qty": int(r[3]),
                    "mode": r[4] or "per_k",
                    "updated_at": int(r[5] or 0)
                }
            return {"map": out, "keys": key_list}
    finally:
        put_conn(conn)


# =========================
# Per-order pricing override (PUBG/Ludo only)
# =========================
class OrderPricingIn(BaseModel):
    order_id: int
    price: Optional[float] = None  # flat price per order
    mode: Optional[str] = None     # reserved for future

def _ensure_order_pricing_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.order_pricing_overrides(
            order_id BIGINT PRIMARY KEY,
            price NUMERIC(18,6) NOT NULL,
            mode TEXT NOT NULL DEFAULT 'flat',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

@app.post("/api/admin/pricing/order/set")
def admin_set_order_pricing(
    body: OrderPricingIn,
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None
):
    _require_admin(x_admin_password or password or "")
    if not body.order_id or body.price is None:
        raise HTTPException(422, "invalid payload")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_order_pricing_table(cur)
            # fetch order to validate status and category
            cur.execute("SELECT id, title, status FROM public.orders WHERE id=%s", (int(body.order_id),))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "order not found")
            oid, sname, status = int(row[0]), str(row[1] or "").lower(), str(row[2] or "Pending")
            # only allow when Pending
            if status != "Pending":
                raise HTTPException(409, "order not pending")
            # allow only PUBG/Ludo
            if not (("pubg" in sname) or ("ببجي" in sname) or ("uc" in sname) or ("ludo" in sname) or ("لودو" in sname)):
                raise HTTPException(422, "not pubg/ludo order")
            cur.execute("""
                INSERT INTO public.order_pricing_overrides(order_id, price, mode, updated_at)
                VALUES(%s,%s,'flat', now())
                ON CONFLICT (order_id) DO UPDATE SET price=EXCLUDED.price, updated_at=now()
            """, (oid, Decimal(body.price)))
            # reflect immediately on orders.price for UI consistency
            cur.execute("UPDATE public.orders SET price=%s WHERE id=%s", (Decimal(body.price), oid))
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.owner_fcm_tokens")
            c = cur.fetchone()[0]
        return {"ok": True, "owner_tokens": int(c)}
    finally:
        put_conn(conn)

@app.post("/api/admin/pricing/order/clear")
def admin_clear_order_pricing(
    body: OrderPricingIn,
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None
):
    _require_admin(x_admin_password or password or "")
    if not body.order_id:
        raise HTTPException(422, "invalid payload")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_order_pricing_table(cur)
            cur.execute("DELETE FROM public.order_pricing_overrides WHERE order_id=%s", (int(body.order_id),))
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.owner_fcm_tokens")
            c = cur.fetchone()[0]
        return {"ok": True, "owner_tokens": int(c)}
    finally:
        put_conn(conn)

# =========================
# Per-order quantity setter (PUBG/Ludo only)
# =========================
class OrderQtyIn(BaseModel):
    order_id: int
    quantity: int
    reprice: Optional[bool] = False  # if True, will recompute price if a per_k rule exists

@app.post("/api/admin/pricing/order/set_qty")
def admin_set_order_quantity(
    body: OrderQtyIn,
    x_admin_password: Optional[str] = Header(None, alias="x-admin-password"),
    password: Optional[str] = None
):
    _require_admin(x_admin_password or password or "")
    if not body.order_id or body.quantity is None:
        raise HTTPException(422, "invalid payload")
    if body.quantity <= 0:
        raise HTTPException(422, "quantity must be > 0")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            # Validate order
            cur.execute("SELECT id, title, status FROM public.orders WHERE id=%s", (int(body.order_id),))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "order not found")
            oid, sname, status = int(row[0]), str(row[1] or "").lower(), str(row[2] or "Pending")
            if status != "Pending":
                raise HTTPException(409, "order not pending")
            if not (("pubg" in sname) or ("ببجي" in sname) or ("uc" in sname) or ("ludo" in sname) or ("لودو" in sname)):
                raise HTTPException(422, "not pubg/ludo order")

            # Update quantity
            cur.execute("UPDATE public.orders SET quantity=%s WHERE id=%s", (int(body.quantity), oid))

            # Optional: reprice if per_k rule exists
            if body.reprice:
                # Try service-specific override then category fallback
                cur.execute("SELECT price_per_k, min_qty, max_qty, COALESCE(mode,'per_k') FROM public.service_pricing_overrides WHERE ui_key=%s", (sname,))
                rowp = cur.fetchone()
                if not rowp:
                    key = None
                    if any(w in sname for w in ["pubg","ببجي","uc"]):
                        key = "cat.pubg"
                    elif any(w in sname for w in ["ludo","لودو"]):
                        key = "cat.ludo"
                    if key:
                        cur.execute("SELECT price_per_k, min_qty, max_qty, COALESCE(mode,'per_k') FROM public.service_pricing_overrides WHERE ui_key=%s", (key,))
                        rowp = cur.fetchone()
                if rowp:
                    ppk = float(rowp[0]); mn = int(rowp[1]); mx = int(rowp[2]); mode = (rowp[3] or 'per_k')
                    if mode == 'per_k':
                        if body.quantity < mn or body.quantity > mx:
                            raise HTTPException(400, f"quantity out of allowed range [{mn}-{mx}]")
                        eff_price = float(Decimal(body.quantity) * Decimal(ppk) / Decimal(1000))
                        cur.execute("UPDATE public.orders SET price=%s WHERE id=%s", (Decimal(eff_price), oid))

        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.owner_fcm_tokens")
            c = cur.fetchone()[0]
        return {"ok": True, "owner_tokens": int(c)}
    finally:
        put_conn(conn)

# =========================
# Topup cards alias routes (execute / reject) to match the app
# =========================
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

# --- Asiacell aliases (execute / reject) ---
@app.post("/api/admin/asiacell/{oid}/execute")
async def admin_execute_asiacell(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_deliver(oid, request, x_admin_password, password)

@app.post("/api/admin/asiacell/{oid}/reject")
async def admin_reject_asiacell(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return await admin_reject(oid, request, x_admin_password, password)

# =============== Run local ===============
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)

# ======================================================================
# Extra compatibility routes to match the app's newer paths
# (added by ChatGPT on 2025-10-12)
# ======================================================================

# ---- Pending buckets aliases ----
@app.get("/api/admin/pending/pubg_orders")
def _alias_pending_pubg(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return admin_pending_pubg(x_admin_password, password)

@app.get("/api/admin/pending/ludo_orders")
def _alias_pending_ludo(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return admin_pending_ludo(x_admin_password, password)

@app.get("/api/admin/pending/api")
@app.get("/api/admin/api/pending")
@app.get("/api/admin/pending/services_list")
@app.get("/api/admin/pending/provider")
def _alias_pending_services(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None, limit: int = 100):
    return admin_pending_services_endpoint(x_admin_password=x_admin_password, password=password, limit=limit)

# ---- Per-order pricing & quantity setters (PUBG/Ludo) ----
@app.post("/api/admin/orders/{oid}/set_price")
async def _alias_set_price(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    data = await _read_json_object(request)
    if "price" not in data:
        raise HTTPException(422, "price required")
    body = OrderPricingIn(order_id=oid, price=float(data["price"]))
    return admin_set_order_pricing(body, x_admin_password, password)

@app.post("/api/admin/orders/{oid}/set_quantity")
async def _alias_set_qty(oid: int, request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    data = await _read_json_object(request)
    if "quantity" not in data:
        raise HTTPException(422, "quantity required")
    body = OrderQtyIn(order_id=oid, quantity=int(data["quantity"]), reprice=bool(data.get("reprice", False)))
    return admin_set_order_quantity(body, x_admin_password, password)

@app.post("/api/admin/order/set_price")
async def _alias_set_price2(request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    data = await _read_json_object(request)
    oid = int(data.get("order_id", 0))
    price = data.get("price")
    if not oid or price is None:
        raise HTTPException(422, "order_id and price required")
    body = OrderPricingIn(order_id=oid, price=float(price))
    return admin_set_order_pricing(body, x_admin_password, password)

@app.post("/api/admin/order/set_qty")
async def _alias_set_qty2(request: Request, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    data = await _read_json_object(request)
    oid = int(data.get("order_id", 0))
    qty = data.get("quantity")
    if not oid or qty is None:
        raise HTTPException(422, "order_id and quantity required")
    body = OrderQtyIn(order_id=oid, quantity=int(qty), reprice=bool(data.get("reprice", False)))
    return admin_set_order_quantity(body, x_admin_password, password)

# ---- Service ID overrides aliases ----
@app.get("/api/admin/services/overrides")
def _alias_list_service_ids(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return admin_list_service_ids(x_admin_password, password)

@app.post("/api/admin/services/override/set")
def _alias_set_service_id(body: SvcOverrideIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return admin_set_service_id(body, x_admin_password, password)

@app.post("/api/admin/services/override/clear")
def _alias_clear_service_id(body: SvcOverrideIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return admin_clear_service_id(body, x_admin_password, password)

# ---- Pricing rules aliases ----
@app.get("/api/admin/pricing/overrides")
def _alias_list_pricing(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return admin_list_pricing(x_admin_password, password)

@app.post("/api/admin/pricing/override/set")
def _alias_set_pricing(body: PricingIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return admin_set_pricing(body, x_admin_password, password)

@app.post("/api/admin/pricing/override/clear")
def _alias_clear_pricing(body: PricingIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    return admin_clear_pricing(body, x_admin_password, password)




# ===== Owner FCM tokens register/unregister =====
class OwnerFcmIn(BaseModel):
    fcm: str

@app.post("/api/admin/fcm/register")
def api_admin_fcm_register(body: OwnerFcmIn, x_admin_password: str = Header(None), password: Optional[str] = None):
    pw = _pick_admin_password(x_admin_password, password, body.dict() if hasattr(body, "dict") else None)
    _require_admin(pw or "")
    token = (body.fcm or "").strip()
    if not token:
        raise HTTPException(422, "fcm required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("INSERT INTO public.owner_fcm_tokens(token) VALUES(%s) ON CONFLICT (token) DO NOTHING", (token,))
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.owner_fcm_tokens")
            c = cur.fetchone()[0]
        return {"ok": True, "owner_tokens": int(c)}
    finally:
        put_conn(conn)

@app.post("/api/admin/fcm/unregister")
def api_admin_fcm_unregister(body: OwnerFcmIn, x_admin_password: str = Header(None), password: Optional[str] = None):
    pw = _pick_admin_password(x_admin_password, password, body.dict() if hasattr(body, "dict") else None)
    _require_admin(pw or "")
    token = (body.fcm or "").strip()
    if not token:
        raise HTTPException(422, "fcm required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM public.owner_fcm_tokens WHERE token=%s", (token,))
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.owner_fcm_tokens")
            c = cur.fetchone()[0]
        return {"ok": True, "owner_tokens": int(c)}
    finally:
        put_conn(conn)

@app.get("/api/admin/fcm/list")


class OwnerFcmTestIn(BaseModel):
    title: str = "اختبار إشعار للمالك"
    body: str = "هذه رسالة اختبار FCM للمالك."
    order_id: Optional[int] = None

@app.post("/api/admin/fcm/test")
def api_admin_fcm_test(body: OwnerFcmTestIn, x_admin_password: str = Header(None), password: Optional[str] = None):
    pw = _pick_admin_password(x_admin_password, password, body.dict() if hasattr(body, "dict") else None)
    _require_admin(pw or "")
    conn = get_conn()
    tokens = []
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT token FROM public.owner_fcm_tokens")
            tokens = [r[0] for r in cur.fetchall() or []]
    finally:
        put_conn(conn)
    if not tokens:
        return {"ok": False, "error": "no owner tokens registered"}
    sent = 0
    for tk in tokens:
        try:
            _fcm_send_push(tk, body.title, body.body, body.order_id, extra_data={"for_owner": "1"})
            sent += 1
        except Exception as ex:
            logger.warning("owner test push failed: %s", ex)
    return {"ok": True, "sent": sent}


@app.get("/api/admin/fcm/debug")
def api_admin_fcm_debug(x_admin_password: str = Header(None), password: Optional[str] = None):
    pw = _pick_admin_password(x_admin_password, password, None)
    _require_admin(pw or "")
    cfg = _fcm_config_status()
    conn = get_conn()
    count = 0
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.owner_fcm_tokens")
            r = cur.fetchone()
            count = (r[0] if r else 0) or 0
    finally:
        put_conn(conn)
    return {"ok": True, "owner_tokens": count, "fcm": cfg}
def api_admin_fcm_list(x_admin_password: str = Header(None), password: Optional[str] = None):
    pw = _pick_admin_password(x_admin_password, password, None)
    _require_admin(pw or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT token FROM public.owner_fcm_tokens ORDER BY created_at DESC")
            rows = [r[0] for r in cur.fetchall() or []]
        return {"ok": True, "tokens": rows}
    finally:
        put_conn(conn)

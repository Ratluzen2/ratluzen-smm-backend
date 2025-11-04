from __future__ import annotations
import asyncio

from typing import Optional
from fastapi import Header, HTTPException

# ---- UI key normalization to tolerate Arabic variants/spaces ----
def _normalize_ui_key(s: Optional[str]) -> str:
    if not s:
        return ""
    try:
        import unicodedata
        t = unicodedata.normalize("NFKC", str(s)).strip().lower()
    except Exception:
        t = str(s).strip().lower()
    repl = {"أ":"ا","إ":"ا","آ":"ا","ى":"ي","ئ":"ي","ؤ":"و","ة":"ه","ـ":""}
    out = []
    for ch in t:
        out.append(repl.get(ch, ch))
    t = "".join(out)
    for ch in [" ", "\u200f","\u200e","\u202a","\u202b","\u202c","\u202d","\u202e","\t","\n","\r","-","_",".",","]:
        t = t.replace(ch, "")
    return t


# === Safety: prevent negative balances on deduct ===
def _can_deduct(balance: float, amount: float) -> bool:
    try:
        return float(balance) - float(amount) >= 0.0
    except Exception:
        return False
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

from fastapi import FastAPI, HTTPException, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# =========================
# Settings
# =========================
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_NEON")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is required")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "").strip()
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID", "").strip()  # optional override
OWNER_UID = os.getenv("OWNER_UID", "OWNER-0001").strip()

PROVIDER_API_URL = os.getenv("PROVIDER_API_URL", "https://kd1s.com/api/v2")
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "25a9ceb07be0d8b2ba88e70dcbe92e06")

POOL_MIN, POOL_MAX = 1, int(os.getenv("DB_POOL_MAX", "5"))
dbpool: pool.SimpleConnectionPool = pool.SimpleConnectionPool(POOL_MIN, POOL_MAX, dsn=DATABASE_URL)

def get_conn() -> psycopg2.extensions.connection:
    """Get a healthy connection from the pool (auto-reopen if closed)."""
    conn = dbpool.getconn()
    try:
        if getattr(conn, "closed", 0):
            raise Exception("connection closed")
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        try:
            # Remove the bad connection from pool and close it
            dbpool.putconn(conn, close=True)
        except Exception:
            pass
        # Get a fresh connection
        conn = dbpool.getconn()
    return conn

def put_conn(conn: psycopg2.extensions.connection) -> None:
    try:
        if conn is not None:
            dbpool.putconn(conn, close=False)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass

def _prune_bad_fcm_token(bad_token: str):
    """
    Remove invalid/blocked FCM token from user_devices and users.fcm_token (if matches).
    Safe to call from anywhere; opens its own DB connection.
    """
    if not bad_token:
        return
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM public.user_devices WHERE fcm_token=%s", (bad_token,))
            except Exception:
                pass
            try:
                cur.execute("UPDATE public.users SET fcm_token=NULL WHERE fcm_token=%s", (bad_token,))
            except Exception:
                pass
    except Exception as e:
        logger.exception("prune_bad_fcm_token failed: %s", e)
    finally:
        put_conn(conn)
# =========================
# Logging
# =========================
logger = logging.getLogger("smm")
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
        import jwt, time as _time
        now = int(_time.time())
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
    """
    Send using FCM HTTP v1. On invalid/blocked tokens, prune them from DB.
    """
    try:
        access_token = _fcm_get_access_token_v1(sa_info)
        if not access_token:
            logger.warning("FCM v1: could not obtain access token")
            return False
        pid = project_id or sa_info.get("project_id")
        if not pid:
            logger.warning("FCM v1: missing project_id")
            return False
        url = f"https://fcm.googleapis.com/v1/projects/{pid}/messages:send"
        message = {
            "message": {
                "token": fcm_token,
                "notification": {"title": title, "body": body},
                "data": {
                    "title": title,
                    "body": body,
                    "order_id": str(order_id or ""),
                }
            }
        }
        resp = requests.post(url, headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }, json=message, timeout=10)

        if resp.status_code in (200, 201):
            return True

        # Try to detect unregistered/invalid tokens and prune
        try:
            ej = resp.json().get("error", {})
        except Exception:
            ej = {}
        status = str(ej.get("status") or "").upper()
        message_txt = str(ej.get("message") or "")
        if resp.status_code in (400, 404) or status in ("INVALID_ARGUMENT", "NOT_FOUND"):
            if ("Requested entity was not found" in message_txt) or ("Invalid registration token" in message_txt) or ("UNREGISTERED" in message_txt.upper()):
                _prune_bad_fcm_token(fcm_token)
        logger.warning("FCM v1 send failed (%s): %s", resp.status_code, resp.text[:300])
        return False
    except Exception as ex:
        logger.exception("FCM v1 send exception: %s", ex)
        return False

def _fcm_send_legacy(fcm_token: str, title: str, body: str, order_id: Optional[int], server_key: str):
    """
    Send using Legacy HTTP API. If response indicates an invalid/blocked token, prune it.
    """
    try:
        headers = {
            "Authorization": f"key={server_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "to": fcm_token,
            "priority": "high",
            "notification": {"title": title, "body": body},
            "data": {"title": title, "body": body, "order_id": str(order_id or "")}
        }
        resp = requests.post("https://fcm.googleapis.com/fcm/send", headers=headers, json=payload, timeout=10)
        if resp.status_code not in (200, 201):
            logger.warning("FCM legacy send failed (%s): %s", resp.status_code, resp.text[:300])
            return False
        # Parse per-result errors
        try:
            obj = resp.json()
        except Exception:
            obj = {}
        try:
            results = obj.get("results") or []
            if results and isinstance(results, list):
                err = results[0].get("error")
                if err in ("NotRegistered", "InvalidRegistration", "MismatchSenderId"):
                    _prune_bad_fcm_token(fcm_token)
                    return False
        except Exception:
            pass
        return True
    except Exception as ex:
        logger.exception("FCM legacy send exception: %s", ex)
        return False

def _fcm_send_push(fcm_token: Optional[str], title: str, body: str, order_id: Optional[int]):
    """
    Wrapper that prefers v1; prunes invalid tokens automatically.
    """
    if not fcm_token:
        return False
    sa_json = (GOOGLE_APPLICATION_CREDENTIALS_JSON or "").strip()
    if sa_json:
        try:
            info = json.loads(sa_json)
            return _fcm_send_v1(fcm_token, title, body, order_id, info, project_id=(FCM_PROJECT_ID or None))
        except Exception as e:
            logger.info("Invalid GOOGLE_APPLICATION_CREDENTIALS_JSON: %s", e)
    if FCM_SERVER_KEY:
        return _fcm_send_legacy(fcm_token, title, body, order_id, FCM_SERVER_KEY)
    logger.warning("FCM not configured: missing credentials")
    return False

# =========================
# Schema & Triggers
# =========================
def ensure_schema():
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # global advisory lock to avoid race on first boot
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

                    # user_devices (multi-device FCM tokens)
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
                    # announcements (for app-wide news)
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
                            b := 'تم تحديث رصيدك. الرصيد الحالي: ' || (SELECT balance FROM public.users WHERE id=NEW.user_id) || ' دينار.';
                            PERFORM pg_notify('wallet_change', json_build_object(
                                'user_id', NEW.user_id,
                                'title', t,
                                'body',  b
                            )::text);
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



def ensure_announcements():
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS public.announcements(
                        id         BIGSERIAL PRIMARY KEY,
                        title      TEXT NULL,
                        body       TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NULL
                    );
                """)
                try:
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_announcements_created ON public.announcements(created_at DESC)")
                except Exception:
                    pass
    finally:
        put_conn(conn)
ensure_schema()

# =========================
# FastAPI
# =========================
app = FastAPI(title="SMM Backend", version="1.9.3")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# ===== Helpers =====

def _tokens_for_uid(cur, uid: str):
    """Return list of FCM tokens for a uid from user_devices or fallback to users.fcm_token"""
    try:
        cur.execute("SELECT fcm_token FROM public.user_devices WHERE uid=%s", (uid,))
        rows = cur.fetchall()
        toks = [r[0] for r in rows if r and r[0]]
        if toks:
            return toks
    except Exception:
        pass
    cur.execute("SELECT fcm_token FROM public.users WHERE uid=%s", (uid,))
    r = cur.fetchone()
    return [r[0]] if r and r[0] else []

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
                    "INSERT INTO public.user_notifications (user_id, order_id, title, body, status, created_at) "
                    "VALUES (%s,%s,%s,%s,'unread', NOW())",
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
                # enrich body with order title + user uid if available
                try:
                    cur.execute("""
                        SELECT o.title, u.uid
                        FROM public.orders o
                        LEFT JOIN public.users u ON u.id = o.user_id
                        WHERE o.id=%s
                    """, (order_id,))
                    row = cur.fetchone()
                    if row:
                        otitle = row[0] or ""
                        u_uid = row[1] or ""
                        n_body = f"طلب جديد رقم {order_id}: {otitle}" + (f" | UID: {u_uid}" if u_uid else "")
                except Exception:
                    pass

                owner_id = _ensure_owner_user_id(cur)
                cur.execute(
                    "INSERT INTO public.user_notifications(user_id, order_id, title, body, status, created_at) "
                    "VALUES (%s,%s,%s,%s,'unread', NOW())",
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
    """Extract a positive integer USD *pack* value from a flexible payload.

    This helper is used for iTunes / رصيد الهاتف فقط.
    For PUBG / Ludo we use separate helpers so that fractional prices مثل 2.50 أو 8.99
    لا تُقص إلى أعداد صحيحة.
    """
    # Primary fields where the client sends the USD pack value (5,10,15,...)
    for k in ("usd", "usd_amount", "amount", "amt"):
        if k in d and d[k] not in (None, ""):
            try:
                v = float(d[k])
            except Exception:
                continue
            if v <= 0:
                continue
            return int(v)

    # Fallbacks (rare): treat price_usd as pack size if no explicit usd/amount
    for k in ("price_usd", "priceUsd", "price"):
        if k in d and d[k] not in (None, ""):
            try:
                v = float(d[k])
            except Exception:
                continue
            if v <= 0:
                continue
            return int(v)

    return 0


def _parse_game_quantity(d: Dict[str, Any]) -> int:
    """Extract quantity for game services (PUBG UC / Ludo).

    Examples:
      650 شدة، 810 الماسة، 56468 ذهب
    """
    for k in (
        "quantity",
        "qty",
        "amount",
        "amount_uc",
        "amount_uc_value",
        "amount_gold",
        "amount_diamond",
        "units",
        "pack",
    ):
        if k in d and d[k] not in (None, ""):
            try:
                v = float(d[k])
            except Exception:
                continue
            if v <= 0:
                continue
            return int(v)
    return 0


def _parse_game_price(d: Dict[str, Any]) -> float:
    """Extract price (with decimals) for game services (PUBG / Ludo)."""
    # Preferred explicit price fields used by the app
    for k in ("price", "priceUsd", "price_usd", "usd_price"):
        if k in d and d[k] not in (None, ""):
            try:
                v = float(d[k])
            except Exception:
                continue
            if v <= 0:
                continue
            return float(v)

    # Backwards compatibility: some أقدم إصدارات كانت ترسل السعر في حقل usd/amount
    for k in ("usd", "usd_amount", "amount", "amt"):
        if k in d and d[k] not in (None, ""):
            try:
                v = float(d[k])
            except Exception:
                continue
            if v <= 0:
                continue
            return float(v)

    return 0.0




def _push_user(conn, user_id: int, order_id: Optional[int], title: str, body: str):
    """Store notification in DB then push FCM to all user's devices (user_devices + fallback)."""
    # 1) Insert row in user_notifications (unread)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.user_notifications (user_id, order_id, title, body, status, created_at) "
                "VALUES (%s,%s,%s,%s,'unread', NOW())",
                (user_id, order_id, title, body)
            )
    except Exception as e:
        logger.exception("push_user insert failed: %s", e)

    # 2) Collect tokens and send FCM
    tokens = []
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT uid FROM public.users WHERE id=%s", (user_id,))
            r = cur.fetchone()
            uid = r[0] if r else None
            if uid:
                tokens = _tokens_for_uid(cur, uid)
    except Exception as e:
        logger.exception("push_user DB read failed: %s", e)
    try:
        for t in tokens:
            _fcm_send_push(t, title, body, order_id)
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
    platform: Optional[str] = "android"

@app.post("/api/users/fcm_token")
def api_users_fcm_token(body: FcmTokenIn):
    uid = (body.uid or "").strip()
    fcm = (body.fcm or "").strip()
    platform = (body.platform or "android").strip().lower() or "android"
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

            # fallback single-token column
            cur.execute("UPDATE public.users SET fcm_token=%s WHERE id=%s", (fcm, user_id))

            # upsert into user_devices
            try:
                cur.execute("""
                    INSERT INTO public.user_devices(uid, fcm_token, platform)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (fcm_token) DO UPDATE SET uid=EXCLUDED.uid, platform=COALESCE(EXCLUDED.platform,'android'), updated_at=NOW()
                """, (uid, fcm, platform))
            except Exception:
                pass

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
            # exact match
            cur.execute("SELECT price_per_k, min_qty, max_qty, COALESCE(mode,'per_k') FROM public.service_pricing_overrides WHERE ui_key=%s", (service_name,))
            rowp = cur.fetchone()

        # normalization fallback on ui_key
        if not rowp and service_name:
            cur.execute("SELECT ui_key, price_per_k, min_qty, max_qty, COALESCE(mode,'per_k') FROM public.service_pricing_overrides")
            allp = cur.fetchall() or []
            sn = _normalize_ui_key(service_name)
            for ui_key, ppk, mn, mx, mode in allp:
                if _normalize_ui_key(ui_key) == sn:
                    rowp = (ppk, mn, mx, mode)
                    break

        # fallback by service_id mapping if present
        if not rowp and service_id:
            try:
                cur.execute("SELECT p.price_per_k, p.min_qty, p.max_qty, COALESCE(p.mode,'per_k') FROM public.service_id_overrides s JOIN public.service_pricing_overrides p ON p.ui_key = s.ui_key WHERE s.service_id=%s", (int(service_id),))
                rowp = cur.fetchone()
            except Exception:
                pass

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
        pass

    # charge if paid# charge if paid (use effective price)
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
        # create order & collect data inside txn
        with conn, conn.cursor() as cur:
            oid = _create_provider_order_core(
                cur, body.uid, body.service_id, body.service_name,
                body.link, body.quantity, body.price
            )
            # collect needed fields but DO NOT notify yet (commit first)
            cur.execute("SELECT user_id, title FROM public.orders WHERE id=%s", (oid,))
            row = cur.fetchone()
            user_id = row[0] if row else None
            title = row[1] if row else body.service_name

        # now outside transaction (COMMITTED): safe to notify
        if user_id:
            _notify_user(conn, user_id, oid, "تم استلام طلبك", f"تم استلام طلب {title}.")
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
            # Do all DB writes first
            with conn, conn.cursor() as cur:
                oid = _create_provider_order_core(cur, p["uid"], p["service_id"], p["service_name"], p["link"], p["quantity"], p["price"])
                # collect user_id for notify after commit
                cur.execute("SELECT user_id FROM public.orders WHERE id=%s", (oid,))
                ur = cur.fetchone()
                user_id = ur[0] if ur else None

            # After COMMIT: push notifications
            if user_id:
                _notify_user(conn, user_id, oid, "تم استلام طلبك", f"تم استلام طلب {p['service_name']}.")
            _notify_owner_new_order(conn, oid)
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
        _notify_owner_new_order(conn, oid)
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
    if len(digits) < 10:
        raise HTTPException(422, "invalid card length")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            oid = _asiacell_submit_core(cur, body.uid, digits)
            # collect user_id for notify after commit
            cur.execute("SELECT user_id FROM public.orders WHERE id=%s", (oid,))
            r = cur.fetchone()
            user_id = r[0] if r else None

        # After COMMIT: push notifications
        if user_id:
            _notify_user(conn, user_id, oid, "تم استلام طلبك", "تم استلام طلب كارت أسيا سيل.")
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
        if not uid or len(digits) < 10:
            raise HTTPException(422, "invalid payload")
        conn = get_conn()
        try:
            with conn, conn.cursor() as cur:
                oid = _asiacell_submit_core(cur, uid, digits)
                cur.execute("SELECT user_id FROM public.orders WHERE id=%s", (oid,))
                r = cur.fetchone()
                if r:
                    _notify_user(conn, r[0], oid, "تم استلام طلبك", "تم استلام طلب كارت أسيا سيل.")
            _notify_owner_new_order(conn, oid)
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
        return [{
            "id": row[0],
            "title": row[1],
            "quantity": row[2],
            "price": float(row[3] or 0),
            "status": row[4],
            "created_at": int(row[5] or 0),
            "link": row[6]
        } for row in rows]
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
@app.get("/api/notifications/by_uid")
def _alias_notifications_by_uid(uid: str, status: str = "unread", limit: int = 50):
    return list_user_notifications(uid=uid, status=status, limit=limit)

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
            logger.info("list_notifications request uid=%s status=%s limit=%s", uid, status, limit)
            cur.execute(f"""
                SELECT id, user_id, order_id, title, body, status,
                       EXTRACT(EPOCH FROM created_at)*1000 AS created_at,
                       EXTRACT(EPOCH FROM read_at)*1000   AS read_at
                FROM public.user_notifications
                {where}
                ORDER BY id DESC
                LIMIT %s
            """, (*params, limit))
            rows = cur.fetchall() or []
            logger.info("list_notifications uid=%s -> %s rows", uid, len(rows))
            return rows
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

    هذه الـ endpoint تُستخدم لكل الطلبات اليدوية التي تخصم من المحفظة مباشرة ثم تعيد المبلغ
    في حال قام المالك برفض الطلب لاحقًا.

    Body (flexible JSON), أمثلة للحقول المتوقعة:
      {
        "uid": "1234567",
        "product": "pubg_uc" | "ludo_diamond" | "ludo_gold" | "itunes" | "atheer" | "asiacell" | "korek",
        // لببجي/لودو:
        "quantity": 650,        // 650 شدة - أو 810 الماسة - أو 56468 ذهب (كميات)
        "price": 2.50,          // السعر بالدولار ويحتوي أجزاء
        // أو لإصدار أقدم:
        // "usd": 2.50           // في هذه الحالة نعتبره هو السعر
        // لخدمات الرصيد/ايتونز:
        // "usd": 5              // قيمة الرصيد بالدولار (5, 10, 15, ...)
        "account_id": "PLAYER_ID(optional)"
      }
    """
    data = await _read_json_object(request)
    uid = (data.get("uid") or "").strip()
    product_raw = (data.get("product") or data.get("type") or data.get("category") or data.get("title") or "").strip()

    # Player account / game id (optional but stored)
    account_id = (data.get("account_id") or data.get("accountId") or data.get("game_id") or "").strip()

    if not uid:
        raise HTTPException(422, "invalid payload")

    product = _normalize_product(product_raw, fallback_title=data.get("title") or "")

    telco_products = ("itunes", "atheer", "asiacell", "korek")
    game_products = ("pubg_uc", "ludo_diamond", "ludo_gold")

    usd = 0            # يستخدم مع ايتونز/الرصيد (5,10,15,...)
    game_qty = 0       # 60 شدة، 650 شدة، 810 الماسة، 56468 ذهب ...
    price = 0.0        # السعر الفعلي الذي سيتم خصمه من المحفظة (يدعم الكسور)
    title = ""

    # -------- Telco / iTunes (topups) --------
    if product in telco_products:
        usd = _parse_usd(data)
        if usd <= 0:
            raise HTTPException(422, "invalid usd for telco/itunes")

        # سعر افتراضي حسب كل 5$ (يمكن أن يتغير عبر overrides بالأسفل)
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

    # -------- PUBG / Ludo (games) --------
    elif product in game_products:
        # الكمية مثل 60 شدة / 810 الماسة / 56468 ذهب
        game_qty = _parse_game_quantity(data)
        if game_qty <= 0:
            # للتوافق مع إصدارات أقدم قد ترسل الكمية في usd أو amount فقط
            game_qty = _parse_usd(data)
        if game_qty <= 0:
            raise HTTPException(422, "invalid quantity for game service")

        # السعر الفعلي الذي يحتوي أجزاء
        game_price = _parse_game_price(data)
        if game_price <= 0:
            raise HTTPException(422, "invalid price for game service")

        price = float(game_price)
        # نخزّن أيضًا نسخة تقريبية في usd فقط للاستخدامات الثانوية (مثلاً الـpayload/meta القديمة)
        usd = int(price) if price > 0 else 0

        if product == "pubg_uc":
            title = f"شحن شدات ببجي {game_qty} شدة بسعر {price}$"
        elif product == "ludo_diamond":
            title = f"شراء الماسات لودو {game_qty} الماسة بسعر {price}$"
        elif product == "ludo_gold":
            title = f"شراء ذهب لودو {game_qty} ذهب بسعر {price}$"
    else:
        raise HTTPException(422, "invalid product")

    if account_id:
        title = f"{title} | ID: {account_id}"

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:

            # --- Dynamic pricing overrides for topup (iTunes/Atheer/Asiacell/Korek) ---
            # إذا كان هناك override مثل ui_key = "topup.<product>.<usd>" نستخدمه كسعر ثابت للبكج.
            override_row = None
            if product in telco_products:
                try:
                    _ensure_pricing_table(cur)
                    try:
                        _ensure_pricing_mode_column(cur)
                    except Exception:
                        pass
                    ui_key = f"topup.{product}.{usd}"
                    cur.execute(
                        "SELECT price_per_k, COALESCE(min_qty,0), COALESCE(max_qty,0), COALESCE(mode,'per_k') "
                        "FROM public.service_pricing_overrides WHERE ui_key=%s",
                        (ui_key,)
                    )
                    override_row = cur.fetchone()
                except Exception:
                    override_row = None

            # التحقق من قيم ايتونز/الرصيد: نسمح بقيم مخصّصة إذا وجد override
            if product in telco_products:
                allowed_telco = {5, 10, 15, 20, 25, 30, 40, 50, 100}
                if (usd not in allowed_telco) and (not override_row):
                    raise HTTPException(422, "invalid usd for telco/itunes")

            # حساب السعر النهائي والعنوان مع تطبيق override إن وجد (لخدمات الرصيد فقط)
            if product in telco_products:
                if override_row:
                    ppk, mn, mx, mode = float(override_row[0]), int(override_row[1] or 0), int(override_row[2] or 0), (override_row[3] or "per_k")
                    # في حالة الـ topup نعامل price_per_k كسعر ثابت للبكج
                    price = float(ppk)
                    effective_usd = int(mn) if mn and mn > 0 else int(usd)
                    usd = effective_usd
                    ar_label = {"itunes": "ايتونز", "atheer": "اثير", "asiacell": "اسياسيل", "korek": "كورك"}.get(product, product)
                    title = f"شراء رصيد {ar_label} {usd}$"
                else:
                    # إعادة حساب احتياطية في حال تغيّر usd
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

            # ---------------------------------------------------------------------------
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
            # meta: نحتفظ بكل من السعر والكمية لألعاب ببجي/لودو، و usd للبقية
            meta: Dict[str, Any] = {"product": product, "account_id": account_id}
            if product in telco_products:
                meta["usd"] = usd
            else:
                meta["usd"] = price  # للتوافق مع البيانات القديمة
                meta["game_qty"] = game_qty
                meta["price"] = price
            cur.execute(
                "INSERT INTO public.wallet_txns(user_id, amount, reason, meta) VALUES(%s,%s,%s,%s)",
                (user_id, Decimal(-price), "order_charge", Json(meta))
            )

            # create pending manual order carrying the price for future refund if rejected
            payload: Dict[str, Any] = {"product": product, "charged": float(price)}
            if product in telco_products:
                payload["usd"] = usd
            else:
                payload["usd"] = price
                payload["game_qty"] = game_qty
            if account_id:
                payload["account_id"] = account_id

            quantity_value = usd if product in telco_products else (game_qty or usd)
            cur.execute(
                """
                INSERT INTO public.orders(user_id, title, quantity, price, status, payload, type)
                VALUES(%s,%s,%s,%s,'Pending',%s,'manual')
                RETURNING id
                """
                ,
                (user_id, title, quantity_value, float(price), Json(payload))
            )
            oid = cur.fetchone()[0]

        # optional: immediate user notification (order received)
        body = title + (f" | ID: {account_id}" if account_id else "")
        _notify_user(conn, user_id, oid, "تم استلام طلبك", body)
        _notify_owner_new_order(conn, oid)

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

def _refund_if_needed(cur, user_id: int, price: float, order_id: int):
    # Correctly use the price parameter (eff_price might be used elsewhere).
    if price and price > 0:
        cur.execute("UPDATE public.users SET balance=balance+%s WHERE id=%s", (Decimal(price), user_id))
        cur.execute("""
            INSERT INTO public.wallet_txns(user_id, amount, reason, meta)
            VALUES(%s,%s,%s,%s)
        """, (user_id, Decimal(price), "order_refund", Json({"order_id": order_id})))

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
            d = {
                "id": oid, "title": title, "quantity": qty,
                "price": float(price or 0), "status": status,
                "created_at": int(created_at or 0), "link": link, "uid": uid
            }
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
            d = {
                "id": oid, "title": title, "quantity": qty,
                "price": float(price or 0), "status": status,
                "created_at": int(created_at or 0), "link": link, "uid": uid
            }
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
            d = {
                "id": oid, "title": title, "quantity": qty,
                "price": float(price or 0), "status": status,
                "created_at": int(created_at or 0), "link": link, "uid": uid
            }
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
            d = {
                "id": oid, "title": title, "quantity": qty,
                "price": float(price or 0), "status": status,
                "created_at": int(created_at or 0), "link": link, "uid": uid
            }
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
            cur.execute("SELECT id, balance FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id, bal_now = int(r[0]), float(r[1] or 0)
            if bal_now < amt:
                raise HTTPException(400, "insufficient balance")

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
        return {"ok": True}
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
        return {"ok": True}
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



class PricingClearIn(BaseModel):
    ui_key: str
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


# ===== Pricing version meta (for cache-busting on clear) =====
def _ensure_pricing_meta_table(cur):
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.service_pricing_meta(
                id INTEGER PRIMARY KEY,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """ )
        cur.execute("""
            INSERT INTO public.service_pricing_meta(id, updated_at)
            VALUES (1, now())
            ON CONFLICT (id) DO NOTHING
        """ )
    except Exception:
        pass

def _bump_pricing_version():
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_pricing_meta_table(cur)
            cur.execute("""
                UPDATE public.service_pricing_meta
                SET updated_at = NOW()
                WHERE id = 1
            """ )
    finally:
        put_conn(conn)
# =============================================================



def _ensure_pricing_bumps(cur):
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS public.pricing_bumps(
                id BIGSERIAL PRIMARY KEY,
                bumped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    except Exception:
        pass

def _bump_pricing_version(*args):
    """Bump pricing version. Compatible with two usages:
    - _bump_pricing_version()            -> updates meta + inserts bump row
    - _bump_pricing_version(cur)         -> inserts bump row using provided cursor
    """
    try:
        if args:
            cur = args[0]
            _ensure_pricing_bumps(cur)
            cur.execute("INSERT INTO public.pricing_bumps DEFAULT VALUES")
            return
        # No-arg path: open connection and update meta + bumps
        conn = get_conn()
        try:
            with conn, conn.cursor() as cur:
                _ensure_pricing_meta_table(cur)
                cur.execute("UPDATE public.service_pricing_meta SET updated_at = NOW() WHERE id = 1")
                _ensure_pricing_bumps(cur)
                cur.execute("INSERT INTO public.pricing_bumps DEFAULT VALUES")
        finally:
            put_conn(conn)
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
    if int(body.min_qty) < 0 or int(body.max_qty) < int(body.min_qty):
        raise HTTPException(422, "invalid range")

    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_pricing_table(cur)
            try:
                _ensure_pricing_mode_column(cur)
            except Exception:
                pass

            # BEFORE snapshot
            try:
                cur.execute("SELECT ui_key, price_per_k, min_qty, max_qty, COALESCE(mode,'per_k') FROM public.service_pricing_overrides WHERE ui_key=%s", (body.ui_key,))
                _before = cur.fetchone()
            except Exception:
                _before = None

            # Upsert
            cur.execute(
                """
                INSERT INTO public.service_pricing_overrides (ui_key, price_per_k, min_qty, max_qty, mode, updated_at)
                VALUES (%s, %s, %s, %s, COALESCE(%s,'per_k'), now())
                ON CONFLICT (ui_key)
                DO UPDATE SET
                    price_per_k = EXCLUDED.price_per_k,
                    min_qty     = EXCLUDED.min_qty,
                    max_qty     = EXCLUDED.max_qty,
                    mode        = COALESCE(EXCLUDED.mode,'per_k'),
                    updated_at  = now()
                """,
                (body.ui_key, Decimal(body.price_per_k), int(body.min_qty), int(body.max_qty), (body.mode or 'per_k'))
            )

            # AFTER snapshot
            try:
                cur.execute("SELECT ui_key, price_per_k, min_qty, max_qty, COALESCE(mode,'per_k') FROM public.service_pricing_overrides WHERE ui_key=%s", (body.ui_key,))
                _after = cur.fetchone()
            except Exception:
                _after = None

        # bump version for client cache refresh (support both unified and cursor-style implementations)
        try:
            _bump_pricing_version()
        except Exception:
            try:
                with get_conn() as c:
                    with c.cursor() as cur:
                        _bump_pricing_version(cur)  # type: ignore
            except Exception:
                pass

        try:
            _notify_pricing_change_via_tokens(conn, body.ui_key, _before, _after)
        except Exception as e:
            logger.exception("notify after set failed: %s", e)

        return {"ok": True}
    finally:
        put_conn(conn)


@app.post("/api/admin/pricing/clear")
def admin_clear_pricing(
    body: PricingClearIn,
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
            try:
                _ensure_pricing_mode_column(cur)
            except Exception:
                pass

            # BEFORE snapshot (for notification)
            try:
                cur.execute("SELECT ui_key, price_per_k, min_qty, max_qty, COALESCE(mode,'per_k') FROM public.service_pricing_overrides WHERE ui_key=%s", (body.ui_key,))
                _before = cur.fetchone()
            except Exception:
                _before = None

            # Delete override
            cur.execute("DELETE FROM public.service_pricing_overrides WHERE ui_key=%s", (body.ui_key,))

        # bump version for client cache refresh
        try:
            _bump_pricing_version()
        except Exception:
            try:
                with get_conn() as c:
                    with c.cursor() as cur:
                        _bump_pricing_version(cur)  # type: ignore
            except Exception:
                pass

        # Notify after commit
        try:
            _notify_pricing_change_via_tokens(conn, body.ui_key, _before, None)
        except Exception as e:
            logger.exception("notify after clear failed: %s", e)

        return {"ok": True}
    finally:
        put_conn(conn)


@app.get("/api/public/pricing/version")
def public_pricing_version():
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            # Ensure tables
            try:
                _ensure_pricing_table(cur)
            except Exception:
                pass
            try:
                _ensure_pricing_mode_column(cur)
            except Exception:
                pass
            # Try both meta & bumps styles
            v_overrides = 0
            v_meta = 0
            v_bumps = 0
            try:
                cur.execute("SELECT COALESCE(EXTRACT(EPOCH FROM MAX(updated_at))*1000, 0) FROM public.service_pricing_overrides")
                v_overrides = int((cur.fetchone() or [0])[0] or 0)
            except Exception:
                v_overrides = 0
            try:
                cur.execute("SELECT COALESCE(EXTRACT(EPOCH FROM updated_at)*1000, 0) FROM public.service_pricing_meta WHERE id=1")
                v_meta = int((cur.fetchone() or [0])[0] or 0)
            except Exception:
                v_meta = 0
            try:
                cur.execute("SELECT COALESCE(EXTRACT(EPOCH FROM MAX(bumped_at))*1000, 0) FROM public.pricing_bumps")
                v_bumps = int((cur.fetchone() or [0])[0] or 0)
            except Exception:
                v_bumps = 0
            v = max(v_overrides, v_meta, v_bumps)
            return {"version": int(v)}
    finally:
        put_conn(conn)


@app.get("/api/public/pricing/bulk")
def public_pricing_bulk(keys: str):
    if not keys:
        return {"map": {}, "keys": []}
    key_list_raw = [k.strip() for k in keys.split(",") if k.strip()]
    if not key_list_raw:
        return {"map": {}, "keys": []}
    # prepare normalized variants
    norm_map = {k: _normalize_ui_key(k) for k in key_list_raw}
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_pricing_table(cur)
            try:
                _ensure_pricing_mode_column(cur)
            except Exception:
                pass
            # Exact matches first
            cur.execute(
                """
                SELECT ui_key, price_per_k, min_qty, max_qty, COALESCE(mode,'per_k'),
                       EXTRACT(EPOCH FROM COALESCE(updated_at, NOW()))*1000 AS updated_at
                FROM public.service_pricing_overrides
                WHERE ui_key = ANY(%s)
                """,
                (key_list_raw,)
            )
            rows = cur.fetchall() or []
            by_ui = {ui_key: (ui_key, price_per_k, min_qty, max_qty, mode, updated_ms) for ui_key, price_per_k, min_qty, max_qty, mode, updated_ms in rows}

            # normalization fallback
            missing = [k for k in key_list_raw if k not in by_ui]
            if missing:
                cur.execute(
                    """
                    SELECT ui_key, price_per_k, min_qty, max_qty, COALESCE(mode,'per_k'),
                           EXTRACT(EPOCH FROM COALESCE(updated_at, NOW()))*1000 AS updated_at
                    FROM public.service_pricing_overrides
                    """
                )
                all_rows = cur.fetchall() or []
                by_norm = {_normalize_ui_key(ui_key): (ui_key, price_per_k, min_qty, max_qty, mode, updated_ms)
                           for ui_key, price_per_k, min_qty, max_qty, mode, updated_ms in all_rows}
                for mk in missing:
                    nk = norm_map.get(mk)
                    if nk and nk in by_norm:
                        ui_key, price_per_k, min_qty, max_qty, mode, updated_ms = by_norm[nk]
                        by_ui[mk] = (ui_key, price_per_k, min_qty, max_qty, mode, updated_ms)

            out = {}
            for original in key_list_raw:
                row = by_ui.get(original)
                if row:
                    (_k, price_per_k, min_qty, max_qty, mode, updated_ms) = row
                    out[original] = {
                        "price_per_k": float(price_per_k) if price_per_k is not None else None,
                        "min_qty": int(min_qty) if min_qty is not None else None,
                        "max_qty": int(max_qty) if max_qty is not None else None,
                        "mode": mode or "per_k",
                        "updated_at": int(updated_ms or 0)
                    }
            return {"map": out, "keys": key_list_raw}
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
        return {"ok": True}
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
        return {"ok": True}
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

        return {"ok": True}
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

# ======================================================================
# Extra compatibility routes to match the app's newer paths
# (kept from your previous version)
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


class TestPushIn(BaseModel):
    title: str = "طلب جديد (اختبار)"
    body: str = "هذا إشعار تجريبي للمالك"
    order_id: Optional[int] = None

@app.post("/api/test/push_owner")
def test_push_owner(p: TestPushIn):
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            owner_id = _ensure_owner_user_id(cur)
            cur.execute(
                "INSERT INTO public.user_notifications(user_id, order_id, title, body, status) VALUES (%s,%s,%s,%s,'unread')",
                (owner_id, p.order_id, p.title, p.body)
            )
            toks = _tokens_for_uid(cur, OWNER_UID)
        sent = 0
        for t in toks:
            _fcm_send_push(t, p.title, p.body, p.order_id)
            sent += 1
        return {"ok": True, "sent": sent, "owner_uid": OWNER_UID}
    finally:
        put_conn(conn)

# =============== Run local ===============
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)


# === Auto-refund helper for canceled/rejected orders ===
def _refund_order_if_needed(order_id: int) -> bool:
    try:
        ord_obj = db.get_order(order_id)
        if not ord_obj:
            return False
        if ord_obj.get("status") in ("Refunded",):
            return True
        if ord_obj.get("status") in ("Rejected", "Canceled", "Cancelled"):
            uid = ord_obj.get("uid")
            amt = float(ord_obj.get("price") or 0.0)
            already = ord_obj.get("refunded", False)
            if amt > 0 and uid and not already:
                db.add_balance(uid, amt)
                db.mark_refunded(order_id)
                return True
        return False
    except Exception as e:
        logging.exception("refund helper failed: %s", e)
        return False


# =========================
# Announcements + Provider balance (compat with app)
# =========================
from typing import Optional as _Optional

@app.post("/api/admin/announcement/create")
async def admin_announcement_create(request: Request, x_admin_password: _Optional[str] = Header(None, alias="x-admin-password"), password: _Optional[str] = None):
    # Body JSON: { "body": "...", "title": "..."? }
    # Requires: x-admin-password header or ?password= in query/body
    data = await _read_json_object(request)
    passwd = _pick_admin_password(x_admin_password, password, data)
    _require_admin(passwd or "")
    body = (data.get("body") or "").strip()
    title = (data.get("title") or "").strip() or None
    if not body:
        raise HTTPException(422, "body is required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            # 1) store the announcement
            cur.execute(
                "INSERT INTO public.announcements(title, body) VALUES(%s,%s) RETURNING id",
                (title, body)
            )
            ann_id = cur.fetchone()[0]

            # 2) bulk insert notifications for ALL users (no 'active' column dependency)
            cur.execute(
                """
                INSERT INTO public.user_notifications (user_id, order_id, title, body, status, created_at)
                SELECT id AS user_id, NULL, %s AS title, %s AS body, 'unread', NOW()
                FROM public.users
                """,
                (title or 'إعلان', body)
            )

            # 3) collect DISTINCT FCM tokens (no dependency on users.active)
            cur.execute(
                """
                SELECT DISTINCT d.fcm_token
                FROM public.user_devices d
                WHERE d.fcm_token IS NOT NULL AND d.fcm_token <> ''
                """
            )
            tokens = [r[0] for r in cur.fetchall()]

        # 4) fan-out FCM
        sent = 0
        for t in tokens:
            try:
                _fcm_send_push(t, title or 'إعلان', body, None)
                sent += 1
            except Exception as fe:
                logger.exception("announcement FCM send failed: %s", fe)
        logger.info("Announcement broadcast: id=%s, tokens_sent=%s", ann_id, sent)
        return {"ok": True, "id": ann_id, "broadcasted": True, "tokens": sent}
    finally:
        put_conn(conn)

@app.get("/api/public/announcements")
def public_announcements(limit: int = 50):
    # Returns: [ { "title": str|null, "body": str, "created_at": <epoch_ms> }, ... ]
    if limit <= 0 or limit > 500:
        limit = 50
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    title,
                    body,
                    (EXTRACT(EPOCH FROM created_at)*1000)::BIGINT AS created_at
                FROM public.announcements
                ORDER BY id DESC
                LIMIT %s
                """,
                (limit,)
            )
            rows = cur.fetchall() or []
            out = [{"id": None, "title": r[0], "body": r[1], "created_at": int(r[2]) if r[2] is not None else 0} for r in rows]
            return out
    finally:
        put_conn(conn)

@app.get("/api/admin/provider/balance")
def admin_provider_balance(x_admin_password: _Optional[str] = Header(None, alias="x-admin-password"), password: _Optional[str] = None):
    # Returns provider balance as JSON: { "balance": <number> }
    # Uses PROVIDER_API_URL / PROVIDER_API_KEY if configured (kd1s compatible).
    _require_admin(_pick_admin_password(x_admin_password, password) or "")
    bal = 0.0
    try:
        resp = requests.post(
            PROVIDER_API_URL,
            data={"key": PROVIDER_API_KEY, "action": "balance"},
            timeout=20
        )
        txt = (resp.text or "").strip()
        # Try JSON first
        try:
            import json as _json
            obj = _json.loads(txt)
            if isinstance(obj, dict):
                if "balance" in obj and obj["balance"] is not None:
                    bal = float(obj["balance"])
                elif isinstance(obj.get("data"), dict) and "balance" in obj["data"]:
                    bal = float(obj["data"]["balance"])
            if bal == 0.0:
                import re as _re
                m = _re.search(r"(\d+(?:\.\d+)?)", txt)
                if m:
                    bal = float(m.group(1))
        except Exception:
            try:
                bal = float(txt)
            except Exception:
                bal = 0.0
    except Exception:
        bal = 0.0
    return {"balance": bal}

@app.post("/api/test/push_user")
def test_push_user(uid: str, title: str = "إشعار تجريبي", body: str = "اختبار الإشعارات", x_admin_password: str = Header(None, alias="x-admin-password"), password: str | None = None):
    _require_admin(x_admin_password or (password or ""))
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM public.users WHERE uid=%s", (uid,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(404, "user not found")
            user_id = int(r[0])
        # store + push
        _push_user(conn, user_id, None, title, body)
        return {"ok": True}
    finally:
        put_conn(conn)


# =========================
# Admin: Announcements CRUD

# ======== Auto-Exec (Admin) - background daemon & endpoints ========
from pydantic import BaseModel
import asyncio, logging, os

def _ensure_settings_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.settings(
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

def _get_flag(cur, key: str, default: bool = False) -> bool:
    cur.execute("SELECT value FROM public.settings WHERE key=%s", (key,))
    r = cur.fetchone()
    if not r:
        return default
    v = r[0]
    try:
        if isinstance(v, dict):
            return bool(v.get("enabled", default))
        # If JSONB stored directly as bool
        return bool(v)
    except Exception:
        return default

def _set_flag(cur, key: str, enabled: bool) -> None:
    cur.execute("""
        INSERT INTO public.settings(key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
    """, (key, Json({"enabled": bool(enabled)})))

class AutoExecToggleIn(BaseModel):
    enabled: bool

class AutoExecRunIn(BaseModel):
    limit: int = 3
    only_when_enabled: bool = True

def _auto_exec_one_locked(cur):
    # pick one eligible API order
    cur.execute("""
        SELECT id, user_id, service_id, link, quantity, price, title, type
        FROM public.orders
        WHERE COALESCE(status,'Pending')='Pending'
        ORDER BY id ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """)
    r = cur.fetchone()
    if not r:
        return None
    (oid, user_id, service_id, link, qty, price, title, otype) = r

    # Non-provider/manual kinds are marked done immediately to avoid blocking the queue
    if otype in ('manual', 'topup_card') or service_id is None:
        cur.execute("UPDATE public.orders SET status='Done' WHERE id=%s", (oid,))
        return {"order_id": oid, "status": "Done", "skipped": True}

    # Claim the order atomically to prevent duplicate processing by other workers
    cur.execute("""
        UPDATE public.orders
        SET status='Processing'
        WHERE id=%s AND COALESCE(status,'Pending')='Pending'
        RETURNING id
    """, (oid,))
    claimed = cur.fetchone()
    if not claimed:
        # another worker took it
        return None

    return {
        "order_id": int(oid),
        "user_id": int(user_id),
        "service_id": int(service_id),
        "link": link or "",
        "quantity": int(qty or 0),
        "price": float(price or 0.0),
        "title": title or ""
    }

def _auto_exec_process_one(conn, rec):
    oid = rec["order_id"]; user_id = rec["user_id"]
    service_id = rec["service_id"]; link = rec["link"]; qty = rec["quantity"]; eff_price = rec["price"]
    try:
        resp = requests.post(
            PROVIDER_API_URL,
            data={"key": PROVIDER_API_KEY, "action": "add",
                  "service": str(service_id), "link": link, "quantity": str(qty)},
            timeout=25
        )
    except Exception:
        with conn, conn.cursor() as cur:
            _refund_if_needed(cur, user_id, eff_price, oid)
            cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (oid,))
        return {"order_id": oid, "status": "Rejected", "reason": "provider_unreachable"}

    if resp.status_code // 100 != 2:
        with conn, conn.cursor() as cur:
            _refund_if_needed(cur, user_id, eff_price, oid)
            cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (oid,))
        return {"order_id": oid, "status": "Rejected", "reason": "provider_http"}

    try:
        data = resp.json()
    except Exception:
        with conn, conn.cursor() as cur:
            _refund_if_needed(cur, user_id, eff_price, oid)
            cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (oid,))
        return {"order_id": oid, "status": "Rejected", "reason": "bad_provider_json"}

    provider_id = data.get("order") or data.get("order_id")
    if not provider_id:
        with conn, conn.cursor() as cur:
            _refund_if_needed(cur, user_id, eff_price, oid)
            cur.execute("UPDATE public.orders SET status='Rejected' WHERE id=%s", (oid,))
        return {"order_id": oid, "status": "Rejected", "reason": "no_provider_id"}

    with conn, conn.cursor() as cur:
        cur.execute("""
            UPDATE public.orders
            SET provider_order_id=%s, status='Processing'
            WHERE id=%s
        """, (str(provider_id), oid))
    try:
        _notify_user(conn, user_id, oid, "تم قبول طلبك", "تم تحويل طلبك إلى المعالجة.")
    except Exception:
        pass
    return {"order_id": oid, "status": "Processing", "provider_order_id": provider_id}

def _auto_exec_run(conn, limit: int = 3):
    processed = []
    for _ in range(max(1, min(int(limit or 1), 20))):
        with conn, conn.cursor() as cur:
            _ensure_settings_table(cur)
            rec = _auto_exec_one_locked(cur)
            if not rec or rec.get("skipped"):
                if rec and rec.get("skipped"):
                    processed.append(rec)
                # Nothing to do
                break
        out = _auto_exec_process_one(conn, rec)
        processed.append(out)
    return processed

# ---- endpoints ----
@app.get("/api/admin/auto_exec/status")
def admin_auto_exec_status(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    _require_admin(_pick_admin_password(x_admin_password, password) or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_settings_table(cur)
            enabled = _get_flag(cur, "auto_exec_api", False)
        return {"enabled": bool(enabled)}
    finally:
        put_conn(conn)

@app.post("/api/admin/auto_exec/toggle")
def admin_auto_exec_toggle(body: AutoExecToggleIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    _require_admin(_pick_admin_password(x_admin_password, password) or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_settings_table(cur)
            _set_flag(cur, "auto_exec_api", bool(body.enabled))
        # Wake up daemon (safe if already running)
        try:
            asyncio.create_task(_auto_exec_daemon())
        except Exception:
            pass
        return {"ok": True, "enabled": bool(body.enabled)}
    finally:
        put_conn(conn)

@app.post("/api/admin/auto_exec/run")
def admin_auto_exec_run(body: AutoExecRunIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    _require_admin(_pick_admin_password(x_admin_password, password) or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            _ensure_settings_table(cur)
            if body.only_when_enabled and not _get_flag(cur, "auto_exec_api", False):
                return {"ok": True, "enabled": False, "processed": []}
        processed = _auto_exec_run(conn, limit=body.limit)
        return {"ok": True, "enabled": True, "processed": processed}
    finally:
        put_conn(conn)

# ---- background daemon ----
_AUTOEXEC_DAEMON_STARTED = False
AUTOEXEC_IDLE_SLEEP = int(os.getenv("AUTOEXEC_IDLE_SLEEP", "5"))
AUTOEXEC_LOOP_SLEEP = int(os.getenv("AUTOEXEC_LOOP_SLEEP", "2"))
AUTOEXEC_LIMIT      = int(os.getenv("AUTOEXEC_LIMIT", "3"))

async def _auto_exec_daemon():
    global _AUTOEXEC_DAEMON_STARTED
    _AUTOEXEC_DAEMON_STARTED = True
    while True:
        try:
            conn = get_conn()
            try:
                with conn, conn.cursor() as cur:
                    _ensure_settings_table(cur)
                    enabled = _get_flag(cur, "auto_exec_api", False)
            finally:
                put_conn(conn)

            if not enabled:
                await asyncio.sleep(AUTOEXEC_IDLE_SLEEP)
                continue

            processed_any = False
            conn = get_conn()
            try:
                batch = _auto_exec_run(conn, limit=AUTOEXEC_LIMIT)
                processed_any = bool(batch)
            finally:
                put_conn(conn)

            await asyncio.sleep(0.5 if processed_any else AUTOEXEC_LOOP_SLEEP)

        except Exception as e:
            logging.exception("auto-exec daemon loop error: %s", e)
            await asyncio.sleep(3)

@app.on_event("startup")
async def _startup_autoexec():
    try:
        if not _AUTOEXEC_DAEMON_STARTED:
            asyncio.create_task(_auto_exec_daemon())
    except Exception as e:
        logging.exception("failed to start auto-exec daemon: %s", e)
# ======== /Auto-Exec (Admin) ========
# =========================
from fastapi import Header

@app.get("/api/admin/announcements")
def admin_announcements_list(limit: int = 200, x_admin_password: str | None = Header(None, alias="x-admin-password"), password: str | None = None):
    _require_admin(_pick_admin_password(x_admin_password, password) or "")
    if limit <= 0 or limit > 500: limit = 200
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, body,
                       (EXTRACT(EPOCH FROM created_at)*1000)::BIGINT AS created_at,
                       (EXTRACT(EPOCH FROM updated_at)*1000)::BIGINT AS updated_at
                FROM public.announcements
                ORDER BY id DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall() or []
            return [
                {
                    "id": int(r[0]),
                    "title": r[1],
                    "body": r[2],
                    "created_at": int(r[3]) if r[3] is not None else 0,
                    "updated_at": int(r[4]) if r[4] is not None else None,
                } for r in rows
            ]
    finally:
        put_conn(conn)

@app.post("/api/admin/announcements/{aid}/update")
@app.post("/api/admin/announcement/{aid}/update")
async def admin_announcement_update(aid: int, request: Request, x_admin_password: str | None = Header(None, alias="x-admin-password"), password: str | None = None):
    data = await _read_json_object(request)
    _require_admin(_pick_admin_password(x_admin_password, password, data) or "")
    title = data.get("title", None)
    body  = data.get("body",  None)
    if title is None and body is None:
        raise HTTPException(422, "title or body required")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            sets = []
            params = []
            if title is not None:
                sets.append("title=%s"); params.append(title)
            if body is not None:
                sets.append("body=%s");  params.append(body)
            sets.append("updated_at=NOW()")
            q = f"UPDATE public.announcements SET {', '.join(sets)} WHERE id=%s RETURNING id"
            params.append(aid)
            cur.execute(q, tuple(params))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "announcement not found")
        return {"ok": True, "id": aid, "updated": True}
    finally:
        put_conn(conn)

@app.post("/api/admin/announcements/{aid}/delete")
@app.post("/api/admin/announcement/{aid}/delete")
def admin_announcement_delete(aid: int, x_admin_password: str | None = Header(None, alias="x-admin-password"), password: str | None = None):
    _require_admin(_pick_admin_password(x_admin_password, password) or "")
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM public.announcements WHERE id=%s RETURNING 1", (aid,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "announcement not found")
        return {"ok": True, "id": aid, "deleted": True}
    finally:
        put_conn(conn)


def _label_for_ui_key(ui_key: str):
    """Return (category, label) from ui_key patterns like:
       topup.itunes.10, topup.asiacell.5000, topup.korek.10000, topup.zain.10000,
       topup.pubg.uc.60, topup.ludo.diamonds.100, cat.pubg, cat.ludo
    """
    try:
        k = (ui_key or "").lower()
        parts = k.split(".")
        def first_digits(ps):
            for p in ps[::-1]:
                if p.isdigit():
                    return p
            return None

        # Defaults
        category = "service"
        label = ui_key

        if not parts:
            return category, label

        if parts[0] in ("topup", "cat"):
            # iTunes
            if "itunes" in parts:
                category = "itunes"
                amt = first_digits(parts)
                label = f"iTunes ${amt}" if amt else "iTunes"
                return category, label

            # Phone balance
            if any(x in parts for x in ("asiacell", "zain", "korek", "atheer")):
                category = "phone"
                op_map = {"asiacell": "آسيا سيل", "zain": "زين", "korek": "كورك", "atheer": "أثير"}
                op = next((x for x in ("asiacell","zain","korek","atheer") if x in parts), None)
                amt = first_digits(parts)
                op_name = op_map.get(op, op or "الهاتف")
                label = f"رصيد {op_name}" + (f" {amt}" if amt else "")
                return category, label

            # PUBG / BGMI
            if any(x in parts for x in ("pubg", "bgmi", "uc")):
                category = "pubg"
                amt = first_digits(parts)
                label = f"PUBG UC {amt}" if amt else "PUBG UC"
                return category, label

            # Ludo
            if any("ludo" in x for x in parts):
                category = "ludo"
                # could be diamonds/gold
                if "diamonds" in parts:
                    base = "Ludo Diamonds"
                elif "gold" in parts:
                    base = "Ludo Gold"
                else:
                    base = "Ludo"
                amt = first_digits(parts)
                label = f"{base} {amt}" if amt else base
                return category, label

        return category, label
    except Exception:
        return "service", ui_key or "خدمة"


def _fmt_price(v, currency: str = "$"):
    try:
        f = float(v)
        return f"{f:g}{currency}"
    except Exception:
        return f"{v}{currency}" if v is not None else ""


def _notify_pricing_change_via_tokens(conn, ui_key: str, before: Optional[tuple], after: Optional[tuple]) -> None:
    """
    إشعار FCM عربي بصيغة موحّدة لكل الخدمات (آيتونز/أثير/آسيا سيل/كورك/زين/ببجي/لودو/خدمات الـ API):
      • رفع/تخفيض السعر:  تم رفع/تخفيض سعر {الباقة|الخدمة} من {السعر القديم} الى {السعر الجديد}
      • تغيير الكمية (للباقات اليدوية مثل آيتونز/الرصيد و PUBG/Ludo):
         تم تغيير كمية {الباقة القديمة} من {الباقة القديمة} الى {الباقة الجديدة}
      • تغيير الحدود (للخدمات المرتبطة بالـ API فقط):
         تم تغيير الحد الأدنى لخدمة {الاسم} من {قديمة} الى {جديدة}
         تم تغيير الحد الأقصى لخدمة {الاسم} من {قديمة} الى {جديدة}
    ملاحظة: لا نستخدم عبارة "بالألف" إطلاقاً.
    """
    try:
        def as_row_dict(r):
            if not r:
                return None
            return {
                "price_per_k": float(r[1]) if r[1] is not None else None,
                "min_qty": int(r[2]) if (len(r) > 2 and r[2] is not None) else None,
                "max_qty": int(r[3]) if (len(r) > 3 and r[3] is not None) else None,
                "mode": (r[4] or "per_k") if len(r) > 4 else "per_k",
            }

        parts = (ui_key or "").lower().split(".")

        def _svc_cat(ps):
            if "itunes" in ps: return "itunes"
            if any(op in ps for op in ("atheer","asiacell","korek","zain")): return "phone"
            if any(p in ps for p in ("pubg","bgmi","uc")): return "pubg"
            if "ludo" in ps:
                if "diamonds" in ps: return "ludo_dia"
                if "gold" in ps: return "ludo_gold"
                return "ludo"
            # treat all other keys as API services
            return "api"

        def _svc_name_ar(ps):
            # Arabic/English heuristics to mirror UI service labels for API services
            cat = _svc_cat(ps)
            # Manual categories keep their fixed names
            if cat == "itunes": return "آيتونز"
            if cat == "phone":
                if "atheer" in ps:   return "أثير"
                if "asiacell" in ps: return "آسيا سيل"
                if "korek" in ps:    return "كورك"
                if "zain" in ps:     return "زين"
                return "رصيد"
            if cat == "pubg": return "ببجي"
            if cat == "ludo_dia": return "ألماس لودو"
            if cat == "ludo_gold": return "ذهب لودو"
            if cat == "ludo": return "لودو"

            # API: build a nicer Arabic name from tokens
            s = " ".join(ps).lower()
            # platform detection
            is_tt = any(k in s for k in ["tiktok","tik","تيكتوك","تيك توك","تيك"])
            is_ig = any(k in s for k in ["instagram","insta","انستا","انستغرام","انستجرام"])
            is_tg = any(k in s for k in ["telegram","teleg","tg","تيليجرام","تلجرام","تلي"])
            is_yt = any(k in s for k in ["youtube","يوتيوب","يوتوب"])

            plat = None
            if is_tt: plat = "تيكتوك"
            elif is_ig: plat = "انستغرام"
            elif is_tg: plat = "تليجرام"
            elif is_yt: plat = "يوتيوب"

            # service types
            is_follow = any(k in s for k in ["followers","follower","subs","متابع","متابعين"])
            is_like   = any(k in s for k in ["likes","like","لايك","لايكات"])
            is_view   = any(k in s for k in ["views","view","مشاهد","مشاهدات"])
            is_live   = any(k in s for k in ["live","broadcast","stream","بث"])
            is_score  = any(k in s for k in ["score","سكور"])
            is_member = any(k in s for k in ["members","member","اعضاء","أعضاء"])
            is_chan   = any(k in s for k in ["channel","قناة","قناه"])
            is_group  = any(k in s for k in ["group","كروب","كروبات"])

            # special cases
            if is_score and is_live:
                return "رفع سكور البث"
            if is_score:
                return "رفع السكور"

            if is_tg and is_member:
                if is_chan and not is_group:
                    return "اعضاء قنوات تليجرام"
                if is_group and not is_chan:
                    return "اعضاء كروبات تليجرام"
                return "اعضاء تليجرام"

            if is_live and is_view:
                if plat == "تيكتوك": return "مشاهدات بث تيكتوك"
                if plat == "انستغرام": return "مشاهدات بث انستا"
                return "مشاهدات البث المباشر"

            if is_follow and plat: return f"متابعين {plat}"
            if is_like and plat:   return f"لايكات {plat}"
            if is_view and plat:   return f"مشاهدات {plat}"

            if plat:
                return f"خدمات {plat}"

            # fallback: if Arabic tokens exist in key, show them; else generic
            raw = " ".join(ps).replace("_", " ").replace(".", " ")
            import re as _re
            raw = _re.sub(r"\s+", " ", raw).strip()
            if _re.search(r"[\u0600-\u06FF]", raw):
                return raw
            return "خدمة"

        def _first_digits(ps):
            for p in reversed(ps):
                if p.isdigit():
                    return int(p)
            return None

        def _fmt_usd(v):
            try:
                f = float(v)
                if abs(f - round(f)) < 1e-9:
                    return f"{int(round(f))}$"
                return f"{f:g}$"
            except Exception:
                return f"{v}$"

        def pack_for(cat, svc, amount):
            if amount is None:
                return svc
            if cat in ("itunes","phone"):
                return f"{amount}${svc}"             # 5$أثير / 10$آيتونز
            if cat == "pubg":
                return f"{amount}UC{svc}"           # 60UCببجي
            if cat in ("ludo","ludo_dia","ludo_gold"):
                return f"{svc} {amount}"            # ألماس لودو 100
            # api: quantity term not used in messages; limits will be explicit below
            return svc

        # prepare snapshots
        b = as_row_dict(before)
        a = as_row_dict(after)
        cat = _svc_cat(parts)
        svc = _svc_name_ar(parts)
        ui_amt = _first_digits(parts)

        b_min = b.get("min_qty") if b else None
        b_max = b.get("max_qty") if b else None
        a_min = a.get("min_qty") if a else None
        a_max = a.get("max_qty") if a else None

        # For topup keys we store amount in ui_key, also we may use min_qty as amount override
        if b_min is None: b_min = ui_amt
        if a_min is None: a_min = ui_amt

        old_price = b.get("price_per_k") if b else None
        new_price = a.get("price_per_k") if a else None

        title = "تحديث التسعير"
        messages = []

        # 1) السعر: رفع/تخفيض (all categories)
        if (old_price is not None) and (new_price is not None) and abs(float(new_price) - float(old_price)) > 1e-9:
            direction = "رفع" if float(new_price) > float(old_price) else "تخفيض"
            # pick a representative pack for manual categories; API uses service name only
            if cat in ("itunes","phone","pubg","ludo","ludo_dia","ludo_gold"):
                ref_amount = a_min if a_min is not None else b_min
                pack = pack_for(cat, svc, ref_amount)
                messages.append(f"تم {direction} سعر {pack} من {_fmt_usd(old_price)} الى {_fmt_usd(new_price)}")
            else:
                messages.append(f"تم {direction} سعر {svc} من {_fmt_usd(old_price)} الى {_fmt_usd(new_price)} لكل الف")

        # 2) تغيّر "الكمية" للباقات اليدوية فقط (itunes/phone/pubg/ludo)
        if cat in ("itunes","phone","pubg","ludo","ludo_dia","ludo_gold"):
            if (b_min is not None) and (a_min is not None) and (int(b_min) != int(a_min)):
                prev_pack = pack_for(cat, svc, int(b_min))
                next_pack = pack_for(cat, svc, int(a_min))
                messages.append(f"تم تغيير كمية {prev_pack} من {prev_pack} الى {next_pack}")

        # 3) تغيّر الحدود (API فقط): الحد الأدنى/الأقصى
        if cat == "api":
            if (b_min is not None) and (a_min is not None) and (int(b_min) != int(a_min)):
                messages.append(f"تم تغيير الحد الأدنى لخدمة {svc} من {int(b_min)} الى {int(a_min)}")
            if (b_max is not None) and (a_max is not None) and (int(b_max) != int(a_max)):
                messages.append(f"تم تغيير الحد الأقصى لخدمة {svc} من {int(b_max)} الى {int(a_max)}")

        if not messages:
            messages.append(f"{svc} — تم التحديث")

        body = " — ".join(messages)

        # إرسال FCM
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT d.fcm_token FROM public.user_devices d WHERE d.fcm_token IS NOT NULL AND d.fcm_token <> ''")
            tokens = [r[0] for r in (cur.fetchall() or [])]

        sent = 0
        for t in tokens:
            try:
                _fcm_send_push(t, title, body, None)
                sent += 1
            except Exception as fe:
                logger.exception("pricing_change FCM send failed: %s", fe)

        logger.info("pricing.change.notify ui_key=%s tokens=%d sent=%d", ui_key, len(tokens), sent)
    except Exception as e:
        logger.exception("notify pricing change failed: %s", e)

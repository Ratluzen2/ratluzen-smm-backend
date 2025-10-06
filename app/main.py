import os
import asyncio
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
from pydantic import BaseModel

# ========== إعداد التطبيق ==========
app = FastAPI(title="Ratluzen SMM Backend", version="1.0.0")

# السماح للتطبيق (أندرويد) بالاتصال
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # يمكنك تضييقها لاحقًا على نطاقك
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== اتصال قاعدة البيانات (Neon) ==========
DB_URL = os.getenv("DATABASE_URL")  # وفّرها في هيروكو
_db_pool: Optional[asyncpg.Pool] = None

async def _create_tables(pool: asyncpg.Pool):
    # جدول بسيط للمستخدمين حسب الـ UID
    create_sql = """
    CREATE TABLE IF NOT EXISTS app_users (
        uid TEXT PRIMARY KEY,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    async with pool.acquire() as conn:
        await conn.execute(create_sql)

@app.on_event("startup")
async def on_startup():
    global _db_pool
    if not DB_URL:
        # سنسمح للتطبيق أن يعمل حتى بدون DB لتفادي التعطيل
        return
    # asyncpg يدعم سلاسل Neon مباشرة (مع sslmode=require)
    _db_pool = await asyncpg.create_pool(dsn=DB_URL, min_size=1, max_size=5)
    await _create_tables(_db_pool)

@app.on_event("shutdown")
async def on_shutdown():
    global _db_pool
    if _db_pool:
        await _db_pool.close()
        _db_pool = None

# ========== مسارات أساسية ==========
@app.get("/health")
async def health():
    # نفحص بشكل خفيف: التطبيق شغال، وقاعدة البيانات (إن وُجدت)
    db_ok = False
    try:
        if _db_pool:
            async with _db_pool.acquire() as conn:
                await conn.execute("SELECT 1;")
            db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok", "db": db_ok}

class UpsertUserBody(BaseModel):
    uid: str

@app.post("/api/users/upsert")
async def upsert_user(body: UpsertUserBody):
    """
    يُستدعى من التطبيق عند التشغيل الأول لحفظ UID.
    يعيد {ok: true} حتى لو لم توجد DB (حتى لا يتعطل التطبيق).
    """
    if not body.uid or not isinstance(body.uid, str):
        raise HTTPException(status_code=400, detail="Invalid uid")

    if not _db_pool:
        # لا نكسر التطبيق إذا ماكو DB
        return {"ok": True, "saved": False, "reason": "db_not_configured"}

    try:
        sql = """
        INSERT INTO app_users(uid) VALUES($1)
        ON CONFLICT (uid) DO UPDATE
        SET last_seen = NOW()
        """
        async with _db_pool.acquire() as conn:
            await conn.execute(sql, body.uid)
        return {"ok": True, "saved": True}
    except Exception as e:
        # لا نُسقط التطبيق
        return {"ok": True, "saved": False, "reason": str(e)}

# ========== مسارات مزود الخدمات (Balance/Status) ==========
from routes_provider import router as provider_router
app.include_router(provider_router)

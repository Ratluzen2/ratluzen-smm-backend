# app/main.py
import os
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# راوتر فحص رصيد مزوّد الخدمات
from .smm_balance_router import router as smm_router


# ========= إعداد اتصال قاعدة البيانات (Heroku/Neon) =========
def _build_async_db_url() -> str:
    raw = os.getenv("DATABASE_URL")
    if not raw:
        raise RuntimeError("Missing env var: DATABASE_URL")
    # تحويل postgres:// إلى postgresql+asyncpg://
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql://", 1)
    return "postgresql+asyncpg://" + raw.split("postgresql://", 1)[1]


ASYNC_DB_URL = _build_async_db_url()
engine: AsyncEngine = create_async_engine(
    ASYNC_DB_URL,
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "5")),
    pool_timeout=30,
    pool_recycle=1800,
    echo=False,
    future=True,
)

# ========= مخطط الجدول =========
CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    uid TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

UPSERT_USER_SQL = """
INSERT INTO users (uid) VALUES (:uid)
ON CONFLICT (uid) DO UPDATE SET last_seen = NOW();
"""

# ========= تطبيق FastAPI =========
app = FastAPI(title="Ratluzen SMM Backend", version="1.0.0")

# ضمّ راوتر رصيد المزوّد تحت /api/smm/*
app.include_router(smm_router, prefix="/api/smm")


# ========= أحداث التشغيل/الإيقاف =========
@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.execute(sa.text(CREATE_USERS_TABLE_SQL))

@app.on_event("shutdown")
async def on_shutdown():
    await engine.dispose()


# ========= نماذج =========
class UpsertUserIn(BaseModel):
    uid: str


# ========= نقاط API أساسية =========
@app.get("/")
async def root():
    return {"ok": True, "service": "ratluzen-smm-backend", "version": "1.0.0"}

@app.get("/health")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/users/upsert")
async def upsert_user(payload: UpsertUserIn):
    uid = (payload.uid or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="uid is required")
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text(UPSERT_USER_SQL), {"uid": uid})
        return {"ok": True, "uid": uid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")


# للتشغيل المحلي:
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)

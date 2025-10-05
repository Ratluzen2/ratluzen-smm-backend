# app/db.py
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncConnection
from sqlalchemy import text

def _make_async_db_url(url: str) -> str:
    # Heroku/Neon قد يعطون postgres:// — نحتاج asyncpg:
    # نحول postgres:// -> postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("متغير البيئة DATABASE_URL غير مضبوط!")

ASYNC_DB_URL = _make_async_db_url(DATABASE_URL)

engine: AsyncEngine = create_async_engine(
    ASYNC_DB_URL,
    echo=False,
    pool_pre_ping=True,
)

# إنشاء الجداول عند الإقلاع
CREATE_USERS_SQL = """
CREATE TABLE IF NOT EXISTS users (
  uid TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

CREATE_ORDERS_SQL = """
CREATE TABLE IF NOT EXISTS orders (
  id SERIAL PRIMARY KEY,
  uid TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
  service_name TEXT NOT NULL,
  quantity INTEGER NOT NULL,
  price NUMERIC(12,2) NOT NULL,
  link TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  provider_order_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text(CREATE_USERS_SQL))
        await conn.execute(text(CREATE_ORDERS_SQL))

async def get_db() -> AsyncGenerator[AsyncConnection, None]:
    # Transaction تلقائي لكل طلب
    async with engine.begin() as conn:
        yield conn

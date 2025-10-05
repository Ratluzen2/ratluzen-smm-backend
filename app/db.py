# app/db.py
import os
import ssl
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# سننشئ URL متوافق مع asyncpg ونزيل أي مفاتيح لا يدعمها (sslmode, channel_binding)
def _build_async_url() -> str:
    raw = os.getenv("DATABASE_URL") or os.getenv("NEON_DATABASE_URL")
    if not raw:
        raise RuntimeError("DATABASE_URL not set")

    # normalize scheme
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql://", 1)
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)

    parts = urlsplit(raw)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    # مفاتيح خاصة بـ libpq وليست مدعومة في asyncpg:
    q.pop("sslmode", None)
    q.pop("channel_binding", None)
    # لا نحتاج لوضع ssl في الURL؛ سنمرّره عبر connect_args
    new_query = urlencode(q)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


ASYNC_DATABASE_URL = _build_async_url()

# سياق SSL افتراضي مع التحقق من الشهادة (مطلوب ل Neon/Heroku)
_sslctx = ssl.create_default_context()

engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={"ssl": _sslctx},  # هذا يفرض SSL مع تحقق الشهادة
)

# جلسات
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# تهيئة الجداول عند الإقلاع
async def init_db():
    from .models import Base  # نتأكد من استيراد الموديلات
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# تبعية FastAPI: الحصول على Session
async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session

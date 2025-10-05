import os
import re
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def normalize_database_url(url: str) -> str:
    if not url:
        return url

    # 1) postgres:// → postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    # 2) أزل أي سائق صريح مثل +psycopg أو +pg8000 أو غيره
    #    مثال: postgresql+psycopg:// → postgresql://
    url = re.sub(r"^postgresql\+\w+://", "postgresql://", url, count=1, flags=re.IGNORECASE)

    # 3) أضمن sslmode=require موجود
    lower = url.lower()
    if lower.startswith("postgresql://") and "sslmode=" not in lower:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"

    return url

DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", ""))

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# اتصال متين على Heroku
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

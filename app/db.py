import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "")  # من Neon (يتضمن sslmode=require)

def _ensure_ssl(url: str) -> str:
    if not url:
        return url
    lower = url.lower()
    if "postgres" in lower and "sslmode=" not in lower:
        # أضف sslmode=require إذا لم يكن موجودًا
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}sslmode=require"
    return url

DATABASE_URL = _ensure_ssl(DATABASE_URL)

# تفادي انقطاع الاتصالات في هيروكو
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def normalize_database_url(url: str) -> str:
    if not url:
        return url
    # postgres:// → postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    # enforce sslmode=require
    if url.lower().startswith("postgresql://") and "sslmode=" not in url.lower():
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url

DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", ""))

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

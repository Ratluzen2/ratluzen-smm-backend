from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings

if not settings.DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

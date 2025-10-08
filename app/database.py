from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import settings

# ملاحظة: psycopg (v3) يستخدم sslmode من URL مباشرة
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

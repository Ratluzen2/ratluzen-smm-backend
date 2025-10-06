import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# --- DATABASE_URL ---
# على هيروكو تكون بصيغة postgres:// ويجب تحويلها إلى postgresql://
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# محرك واحد فقط للتطبيق كله
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

# جلسات
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

# Base واحدة مشتركة
Base = declarative_base()

# Dependency للـ FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

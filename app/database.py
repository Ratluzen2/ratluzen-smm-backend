# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

DATABASE_URL = settings.DATABASE_URL

# إعداد المحرك حسب نوع قاعدة البيانات
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    # على هيروكو عادة PostgreSQL
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# جلسة SQLAlchemy
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 👈 هذا كان مفقوداً
Base = declarative_base()

# تبعية الجلسة لفاستAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

__all__ = ["Base", "engine", "SessionLocal", "get_db"]

# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# خذ عنوان قاعدة البيانات من متغيرات البيئة (Neon / Heroku)
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DB_URL") or "sqlite:///./local.db"

# معاملات خاصة بالـ SQLite فقط
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# محرك SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args=connect_args,
)

# جلسات قاعدة البيانات
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# دالة الحقن مع FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

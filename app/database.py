# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# دعم صيغة Heroku القديمة postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

connect_args = {}
# في SQLite المحلي فقط
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

# ملاحظة: Base الحقيقي موجود الآن في app.models
# هذا الملف يعرِّف فقط أدوات الجلسة.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

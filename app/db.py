import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# احصل على رابط قاعدة البيانات من متغيرات البيئة في هيروكو (Config Vars)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is missing")

# ملاحظة: psycopg2-binary يتعامل بسلاسة مع ?sslmode=require لدى Neon/Heroku
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # يتحقق قبل كل طلب لتفادي انقطاع الاتصالات
    pool_size=5,
    max_overflow=5,
)

# مصنع جلسات SQLAlchemy (Sync)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Dependency للاستخدام مع FastAPI:
    from fastapi import Depends
    def endpoint(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db() -> None:
    """
    فحص اتصال القاعدة عند الإقلاع. (إنشاء الجداول ممكن يكون على Neon مسبقاً)
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        # اطبع للّوج فقط كي لا يمنع الإقلاع
        print(f"[init_db] database ping failed: {exc}")

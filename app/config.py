from pydantic import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    APP_NAME: str = "Ratluzan SMM Backend"

    # Admin auth (الهيدر x-admin-pass)
    ADMIN_PASS: str = os.getenv("ADMIN_PASS", "2000")

    # Secret (لو احتجته لاحقاً)
    SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET")

    # DB: Heroku Postgres (DATABASE_URL) أو SQLite محلياً
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./smm_backend.db")

    # مزود SMM الافتراضي
    SMM_API_URL: str = os.getenv("SMM_API_URL", "https://kd1s.com/apikd1s")
    SMM_API_KEY: str = os.getenv("SMM_API_KEY", "REPLACE_WITH_REAL_KEY")

    # روابط الدعم (اختياري)
    SUPPORT_TELEGRAM_URL: Optional[str] = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/your_support")
    SUPPORT_WHATSAPP_URL: Optional[str] = os.getenv("SUPPORT_WHATSAPP_URL", "https://wa.me/1234567890")

settings = Settings()

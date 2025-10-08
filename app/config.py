from pydantic import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    APP_NAME: str = "Ratluzan SMM Backend"

    # Auth
    SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET")
    OWNER_PIN: str = os.getenv("OWNER_PIN", "2000")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # DB (Heroku Postgres via DATABASE_URL; fallback SQLite)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./smm_backend.db")

    # Default SMM provider (can be overridden via provider_map.py)
    SMM_API_URL: str = os.getenv("SMM_API_URL", "https://kd1s.com/apikd1s")
    SMM_API_KEY: str = os.getenv("SMM_API_KEY", "REPLACE_WITH_REAL_KEY")

    # Support links for /config (APK uses them)
    SUPPORT_TELEGRAM_URL: Optional[str] = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/your_support")
    SUPPORT_WHATSAPP_URL: Optional[str] = os.getenv("SUPPORT_WHATSAPP_URL", "https://wa.me/1234567890")

settings = Settings()

from pydantic import BaseSettings, AnyHttpUrl
from typing import Optional
import os

class Settings(BaseSettings):
    APP_NAME: str = "SMM Backend"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET")
    OWNER_PIN: str = os.getenv("OWNER_PIN", "2000")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Database (Postgres on Heroku via DATABASE_URL; fallback to local SQLite)
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./smm_backend.db")

    # SMM Panel configuration
    SMM_API_URL: str = os.getenv("SMM_API_URL", "https://kd1s.com/apikd1s")  # Typical SMM API endpoint
    SMM_API_KEY: str = os.getenv("SMM_API_KEY", "REPLACE_WITH_REAL_KEY")

    # Support links (shown inside the app via /config)
    SUPPORT_TELEGRAM_URL: Optional[str] = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/your_support")
    SUPPORT_WHATSAPP_URL: Optional[str] = os.getenv("SUPPORT_WHATSAPP_URL", "https://wa.me/1234567890")

settings = Settings()

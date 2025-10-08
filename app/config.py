from pydantic import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    APP_NAME: str = "Ratluzan SMM Backend"

    # يقبل SECRET_KEY أو JWT_SECRET
    SECRET_KEY: str = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET", "CHANGE_ME_SECRET")

    # يقبل ADMIN_PASS أو ADMIN_PASSWORD
    ADMIN_PASS: str = os.getenv("ADMIN_PASS") or os.getenv("ADMIN_PASSWORD", "2000")

    # DB
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./smm_backend.db")

    # يقبل SMM_API_URL أو KD1S_API_URL
    SMM_API_URL: str = os.getenv("SMM_API_URL") or os.getenv("KD1S_API_URL", "https://kd1s.com/api/v2")

    # يقبل SMM_API_KEY أو KD1S_API_KEY
    SMM_API_KEY: str = os.getenv("SMM_API_KEY") or os.getenv("KD1S_API_KEY", "")

    # روابط دعم اختيارية
    SUPPORT_TELEGRAM_URL: Optional[str] = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/your_support")
    SUPPORT_WHATSAPP_URL: Optional[str] = os.getenv("SUPPORT_WHATSAPP_URL", "https://wa.me/1234567890")

settings = Settings()

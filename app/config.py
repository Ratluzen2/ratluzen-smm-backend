from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    APP_NAME: str = "ratluzen-smm-backend"
    DEBUG: bool = False

    # قاعدة البيانات (Neon / Postgres)
    DATABASE_URL: str

    # كلمة مرور المالك (تطابق ما في التطبيق: 2000)
    ADMIN_PASSWORD: str = Field(default="2000", alias="ADMIN_PASS")

    # مفاتيح مزود KD1S
    KD1S_API_KEY: str | None = None
    KD1S_API_URL: str = "https://kd1s.com/api/v2"

    # اختيارية: مفاتيح FCM إن أردت إرسال إشعارات Push من الباكند
    FCM_SERVER_KEY: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

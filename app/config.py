from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., description="Postgres URL, e.g. postgresql://...")
    ADMIN_PASSWORD: str = Field(default="2000")
    FCM_SERVER_KEY: str | None = None

    # مزود الخدمات (اختياري)
    PROVIDER_BASE_URL: str | None = None
    PROVIDER_KEY: str | None = None

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

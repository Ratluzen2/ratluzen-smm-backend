from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., description="PostgreSQL URL e.g. postgresql://user:pass@host/db?sslmode=require")
    ADMIN_PASSWORD: str = Field("2000", description="Admin pass used in 'x-admin-pass' header")
    KD1S_API_URL: str = Field("https://kd1s.com/api/v2", description="KD1S SMM API base")
    KD1S_API_KEY: str = Field("", description="KD1S SMM API key")
    FCM_SERVER_KEY: str = Field("", description="(Optional) Firebase server key")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

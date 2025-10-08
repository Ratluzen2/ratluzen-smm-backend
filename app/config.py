import os

class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://user:pass@localhost:5432/postgres"
    )
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "2000")
    FCM_SERVER_KEY: str | None = os.getenv("FCM_SERVER_KEY")

    KD1S_BASE: str = os.getenv("KD1S_BASE", "https://kd1s.com/api/v2").rstrip("/")
    KD1S_API_KEY: str = os.getenv("KD1S_API_KEY", "")

settings = Settings()

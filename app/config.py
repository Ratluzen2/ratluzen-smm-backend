import os

class Settings:
    SMM_API_URL: str = os.getenv("SMM_API_URL", "").strip()
    SMM_API_KEY: str = os.getenv("SMM_API_KEY", "").strip()
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "2000").strip()
    FCM_SERVER_KEY: str = os.getenv("FCM_SERVER_KEY", "").strip()

settings = Settings()

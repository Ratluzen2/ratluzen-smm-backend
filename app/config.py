import os

class Settings:
    # قاعدة البيانات (Neon / Heroku Postgres)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://neondb_owner:password@host/neondb?sslmode=require"
    )

    # كلمة مرور المالك (ترويسة x-admin-pass)
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "2000")

    # إعدادات مزوّد الخدمات SMM
    PROVIDER_URL: str = os.getenv("PROVIDER_URL", "").strip()  # مثال: https://provider.example.com
    PROVIDER_KEY: str = os.getenv("PROVIDER_KEY", "").strip()

    # FCM (اختياري)
    FCM_SERVER_KEY: str = os.getenv("FCM_SERVER_KEY", "").strip()

settings = Settings()

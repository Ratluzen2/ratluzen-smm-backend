import os

DATABASE_URL   = os.getenv("DATABASE_URL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2000")
JWT_SECRET     = os.getenv("JWT_SECRET", "change_me")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))

# يدعم الاسمين: PROVIDER_* أو SMM_API_*
PROVIDER_BASE  = (os.getenv("PROVIDER_BASE") or os.getenv("SMM_API_URL") or "").strip()
PROVIDER_KEY   = (os.getenv("PROVIDER_KEY")  or os.getenv("SMM_API_KEY")  or "").strip()

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "").strip()  # اختياري

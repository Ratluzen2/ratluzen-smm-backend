import os

# ====== بيئة التشغيل ======
DATABASE_URL   = os.getenv("DATABASE_URL", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2000")
JWT_SECRET     = os.getenv("JWT_SECRET", "change_me")
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "7"))

# ====== مزوّد SMM (عام) ======
# أمثلة شائعة: https://panel.com/api/v2 (POST form-data: key, action, service/link/quantity/order)
PROVIDER_BASE  = os.getenv("PROVIDER_BASE", "").strip()
PROVIDER_KEY   = os.getenv("PROVIDER_KEY", "").strip()

# CORS
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

# FCM (اختياري تماماً)
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "").strip()

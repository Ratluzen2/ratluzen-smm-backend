import os

APP_NAME = "Ratluzan SMM Backend"

# تقبل الاسمَين
SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET", "CHANGE_ME_SECRET")

# كلمة مرور لوحة الأدمن (الهيدر x-admin-pass أو ?key=)
ADMIN_PASS = os.getenv("ADMIN_PASS") or os.getenv("ADMIN_PASSWORD", "2000")

# قاعدة البيانات
DATABASE_URL = os.getenv("DATABASE_URL")  # ضعه بصيغة postgresql://...sslmode=require

# مزود الـSMM (KD1S متوافق مع action=balance/services/add/status)
SMM_API_URL = (os.getenv("SMM_API_URL") or os.getenv("KD1S_API_URL") or "https://kd1s.com/api/v2").rstrip("/")
SMM_API_KEY = os.getenv("SMM_API_KEY") or os.getenv("KD1S_API_KEY") or ""

# روابط دعم للتطبيق (تظهر في /api/config)
SUPPORT_TELEGRAM_URL = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/your_support")
SUPPORT_WHATSAPP_URL = os.getenv("SUPPORT_WHATSAPP_URL", "https://wa.me/1234567890")

import os

APP_NAME = "Ratluzan SMM Backend"

# سر JWT
SECRET_KEY = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET", "CHANGE_ME_SECRET")

# كلمة مرور لوحة المالك
ADMIN_PASS = os.getenv("ADMIN_PASS") or os.getenv("ADMIN_PASSWORD", "2000")

# قاعدة البيانات (نضمن postgresql:// + sslmode=require)
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
if DATABASE_URL and DATABASE_URL.startswith("postgresql://") and "sslmode=" not in DATABASE_URL:
    DATABASE_URL += ("&" if "?" in DATABASE_URL else "?") + "sslmode=require"

# مزوّد SMM (KD1S)
SMM_API_URL = (os.getenv("SMM_API_URL") or os.getenv("KD1S_API_URL") or "https://kd1s.com/api/v2").rstrip("/")
SMM_API_KEY = os.getenv("SMM_API_KEY") or os.getenv("KD1S_API_KEY") or ""
KD1S_API_URL = SMM_API_URL   # aliases ليعمل الاستيراد بالاسمين
KD1S_API_KEY = SMM_API_KEY

# روابط دعم (اختياري)
SUPPORT_TELEGRAM_URL = os.getenv("SUPPORT_TELEGRAM_URL", "https://t.me/your_support")
SUPPORT_WHATSAPP_URL = os.getenv("SUPPORT_WHATSAPP_URL", "https://wa.me/1234567890")

import os

def get_db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    # هيروكو تُرجع أحياناً postgres:// — نحولها للصيغة الصحيحة
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url and "asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url

KD_API_URL = os.getenv("KD_API_URL", "https://kd1s.com/api/v2")
KD_API_KEY = os.getenv("KD_API_KEY", "")  # ضع المفتاح في Config Vars بهيروكو
OWNER_PASS = os.getenv("OWNER_PASS", "2000")  # كلمة مرور المالك (كما بالتطبيق)
APPROVAL_REQUIRED = os.getenv("APPROVAL_REQUIRED", "true").lower() == "true"

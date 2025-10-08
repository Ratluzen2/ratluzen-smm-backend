from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import APP_NAME, SUPPORT_TELEGRAM_URL, SUPPORT_WHATSAPP_URL
from .models import ensure_schema
from .routers import routes_users, routes_provider, admin

app = FastAPI(title=APP_NAME, version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# health — يرد فوراً (بدون DB)
@app.get("/health")
def health(): return {"ok": True, "app": APP_NAME}
@app.get("/api/health")
def health_alias(): return {"ok": True, "app": APP_NAME}

# إعدادات للتطبيق
@app.get("/api/config")
def get_config():
    return {
        "ok": True,
        "data": {
            "app_name": APP_NAME,
            "support_telegram_url": SUPPORT_TELEGRAM_URL,
            "support_whatsapp_url": SUPPORT_WHATSAPP_URL,
        }
    }

# ضم الراوترات
app.include_router(routes_provider.router)
app.include_router(routes_users.router)
app.include_router(admin.router)

# إنشاء الجداول في خلفية الإقلاع (لا نحجب /health)
@app.on_event("startup")
def _init_db():
    try:
        ensure_schema()
    except Exception:
        # لا نمنع الإقلاع حتى لو فشل؛ المسارات الأخرى ستظهر الخطأ عند الاستخدام
        pass

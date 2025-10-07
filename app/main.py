# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from .database import engine
from .models import Base

# الراوترات
try:
    from .routers.smm import r as smm_router         # يحتوي prefix="/api"
except Exception as e:
    smm_router = None
    logging.exception("Failed to import smm router: %s", e)

try:
    from .routers.admin import r as admin_router     # يحتوي prefix="/admin"
except Exception as e:
    admin_router = None
    logging.exception("Failed to import admin router: %s", e)

# (اختياري) إن كان لديك راوتر إضافي للمزوّد
try:
    from .routers.routes_provider import r as provider_router  # غالبًا prefix="/provider"
except Exception as e:
    provider_router = None
    logging.info("provider router not present (optional): %s", e)

app = FastAPI(title="ratluzen-smm-backend", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # يمكنك تضييقها لاحقًا إن أردت
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# إنشاء الجداول عند التشغيل
@app.on_event("startup")
def on_startup() -> None:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        logging.exception("Failed to initialize database schema on startup")

# ضمّ الراوترات
if smm_router is not None:
    # smm.py معرف أصلاً بـ prefix="/api" فلا نضيف Prefix هنا
    app.include_router(smm_router)

if admin_router is not None:
    # نجعله تحت /api/admin ليتوافق مع التطبيق
    app.include_router(admin_router, prefix="/api")

if provider_router is not None:
    # إن وُجد، نضعه تحت /api/provider
    app.include_router(provider_router, prefix="/api")

# الجذر
@app.get("/")
def root():
    return {
        "ok": True,
        "name": "ratluzen-smm-backend",
        "routers": {
            "smm": bool(smm_router),
            "admin": bool(admin_router),
            "provider": bool(provider_router),
        },
    }

# Health check
@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        db_ok = True
    except Exception:
        logging.exception("DB health failed")
        db_ok = False
    return {"ok": True, "db": db_ok}

# Health عبر /api أيضًا (للاستخدام من التطبيق)
@app.get("/api/health")
def api_health():
    return health()

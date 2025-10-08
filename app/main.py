from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from .config import settings
from .routers import routes_users, routes_provider, admin
from . import smm_balance_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# نقاط عامة
app.include_router(routes_users.router)
app.include_router(routes_provider.router)

# نقاط الأدمن (x-admin-pass)
app.include_router(admin.router)
app.include_router(smm_balance_router.router)

# اختيارياً: /config
@app.get("/api/config")
def get_config():
    return {
        "ok": True,
        "data": {
            "app_name": settings.APP_NAME,
            "support_telegram_url": settings.SUPPORT_TELEGRAM_URL,
            "support_whatsapp_url": settings.SUPPORT_WHATSAPP_URL,
        }
    }

from fastapi import FastAPI
from .database import Base, engine
from .routers.smm import router as smm_router
from .routers.routes_provider import router as provider_router

# إنشاء الجداول عند الإقلاع (بسيط بدون Alembic)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="ratluzen-smm-backend")

# صحّة الخادم + upsert المستخدم
app.include_router(smm_router)

# مزوّد الخدمات + لوحات المالك
app.include_router(provider_router)

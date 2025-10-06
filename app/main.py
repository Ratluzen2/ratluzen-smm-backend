from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine
from .models import Base
from .routers.smm import r as public_router
from .routers.routes_provider import r as provider_router
from .routers.admin import r as admin_router

app = FastAPI(title="ratluzen-smm-backend", version="1.0.0")

# إنشاء الجداول تلقائياً عند الإقلاع
Base.metadata.create_all(bind=engine)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# مسارات
app.include_router(public_router, prefix="/api")
app.include_router(provider_router, prefix="/api")
app.include_router(admin_router, prefix="/api")

@app.get("/")
def root():
    return {"ok": True, "name": "ratluzen-smm-backend"}

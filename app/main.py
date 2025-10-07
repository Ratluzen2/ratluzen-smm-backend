from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from .database import engine
from .models import Base
from .routers import smm, admin

app = FastAPI(title="ratluzen-smm-backend", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# راوترات
app.include_router(smm.r, prefix="/api")
app.include_router(admin.r, prefix="/api")

@app.get("/")
def root():
    return {"ok": True, "name": "ratluzen-smm-backend"}

# Health
@app.get("/health")
def health():
    try:
        from .database import SessionLocal
        with SessionLocal() as db:
            db.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {"ok": True, "db": db_ok}

@app.get("/api/health")
def api_health():
    return health()

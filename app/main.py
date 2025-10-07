# app/main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging

from .database import engine
from .models import Base
from .routers.smm import r as public_router
from .routers.routes_provider import r as provider_router
from .routers.admin import r as admin_router


app = FastAPI(title="ratluzen-smm-backend", version="1.0.0")

# ---- CORS ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Startup: create tables ----
@app.on_event("startup")
def on_startup() -> None:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        logging.exception("Failed to initialize database schema on startup")

# ---- Global error handlers (تُظهر سبب الخطأ بدل 500 عام) ----
@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"ok": False, "error": "validation_error", "detail": exc.errors()},
    )

@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    logging.exception("Unhandled server error")
    # نعرض الرسالة لتسهيل التشخيص. أزل 'detail' لاحقًا إن أردت إخفاءها.
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "internal_error", "detail": str(exc)},
    )

# ---- Routers ----
app.include_router(public_router, prefix="/api")
app.include_router(provider_router, prefix="/api")
app.include_router(admin_router, prefix="/api")

# ---- Root ----
@app.get("/")
def root():
    return {"ok": True, "name": "ratluzen-smm-backend"}

# ---- Health ----
@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return {"ok": True, "db": db_ok}

@app.get("/api/health")
def api_health():
    return health()

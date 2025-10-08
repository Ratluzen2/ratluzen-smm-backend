# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from importlib import import_module

from .database import engine
from .models import Base

app = FastAPI(title="ratluzen-smm-backend", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _load_router(module_path: str):
    """
    يحاول قراءة المتغيّر router أو r من الموديول المحدد.
    يفيد إذا كانت بعض الراوترات تسمي المتغيّر r وأخرى router.
    """
    try:
        m = import_module(module_path, package=__package__)
    except Exception as e:
        raise ImportError(f"Failed to import module {module_path}: {e}") from e

    rtr = getattr(m, "router", None) or getattr(m, "r", None)
    if rtr is None:
        raise ImportError(
            f"Module {module_path} does not expose 'router' nor 'r'. "
            f"Please define 'router = APIRouter(...)' (or alias r = router) inside it."
        )
    return rtr

# إنشاء الجداول عند التشغيل
@app.on_event("startup")
def on_startup() -> None:
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        logging.exception("Failed to initialize database schema on startup")

# ضمّ الراوترات (ندعم router أو r في كل ملف)
# تأكد أن لديك الملفات التالية:
# app/routers/smm.py
# app/routers/routes_provider.py
# app/routers/admin.py
try:
    app.include_router(_load_router(".routers.smm"),            prefix="/api")
except Exception:
    logging.exception("Failed to include public (smm) router")

try:
    app.include_router(_load_router(".routers.routes_provider"), prefix="/api")
except Exception:
    logging.exception("Failed to include provider router")

try:
    app.include_router(_load_router(".routers.admin"),          prefix="/api")
except Exception:
    logging.exception("Failed to include admin router")

@app.get("/")
def root():
    return {"ok": True, "name": "ratluzen-smm-backend"}

# Health check بسيط
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

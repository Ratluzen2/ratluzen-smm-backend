from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import APP_NAME
from .models import ensure_schema
from .routers import routes_users, admin

app = FastAPI(title=APP_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/health")
def health(): return {"ok": True, "app": APP_NAME}

@app.get("/", include_in_schema=False)
def root():
    return JSONResponse({"ok": True, "app": APP_NAME, "docs": "/docs", "health": "/health"})

app.include_router(routes_users.router)
app.include_router(admin.router)

@app.on_event("startup")
def _init_db():
    try:
        ensure_schema()
    except Exception:
        pass

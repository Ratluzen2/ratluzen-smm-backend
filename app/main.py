from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import public, admin

app = FastAPI(title="SMM Backend", openapi_url="/api/openapi.json", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health():
    return {"ok": True}

app.include_router(public.router)
app.include_router(admin.router)

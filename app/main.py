# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers.routes_provider import router as provider_router

app = FastAPI(title="Ratlwzan API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"ok": True}

# API المزود (الرصيد/حالة الطلب)
app.include_router(provider_router)

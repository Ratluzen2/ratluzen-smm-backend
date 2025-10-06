# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# استيراد نسبي صحيح من مجلد routers
from .routers.routes_provider import router as provider_router

# إن كان لديك راوترات أخرى (مثلاً users/upsert أو غيره) ابقها كما هي:
try:
    from .smm_balance_router import router as balance_router  # إن كان موجوداً
except Exception:
    balance_router = None

app = FastAPI(title="Ratlwzan API", version="1.0.0")

# CORS – اسمح للتطبيق بالاتصال
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"ok": True}

# إرفاق الراوترات
app.include_router(provider_router)
if balance_router:
    app.include_router(balance_router)

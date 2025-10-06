from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.config import ALLOWED_ORIGINS
from app.routers import smm, admin

app = FastAPI(title="Ratluzén SMM Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # إنشاء الجداول تلقائيًا (بسيط — يمكنك لاحقًا استخدام Alembic)
    Base.metadata.create_all(bind=engine)

# تضمين المسارات
app.include_router(smm.router, prefix="/api", tags=["public"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])

@app.get("/health")
async def health():
    return {"ok": True}

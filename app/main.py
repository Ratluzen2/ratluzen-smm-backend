from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import init_db  # و get_db متوفّرة داخل db.py عند الحاجة

app = FastAPI(title="Ratluzen SMM API")

# CORS — عدّل origins إذا أردت تقييدها
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # فحص اتصال القاعدة عند الإقلاع
    init_db()

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat(timespec="seconds")}

# إن كان لديك راوترات إضافية (smm، orders، users)، يمكنك تضمينها هنا:
# from fastapi import Depends
# from sqlalchemy.orm import Session
# from app.db import get_db
# from app.routers.smm import router as smm_router
# app.include_router(smm_router, prefix="/api/smm", tags=["smm"])
#
# أمثلة لاحقاً:
# @app.post("/api/users/upsert")
# def upsert_user(uid: str, db: Session = Depends(get_db)):
#     ...

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import init_db  # و get_db موجودة الآن داخل db.py
from datetime import datetime

app = FastAPI(title="Ratluzen SMM API")

# CORS — عدّل الأصول إن أردت
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # فحص اتصال القاعدة
    init_db()

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat(timespec="seconds")}

# بقية الراوترات/النقاط عندك تبقى كما هي (إن وُجدت) وتستطيع حقن الجلسة:
# from fastapi import Depends
# from sqlalchemy.orm import Session
# from app.db import get_db
#
# @app.get("/users/me")
# def me(db: Session = Depends(get_db)):
#     ...

import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from . import models

# إنشاء الجداول (مرة واحدة عند الإقلاع)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="SMM Backend", version="1.0.0")

# CORS
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in ALLOWED_ORIGINS.split(",")] if ALLOWED_ORIGINS != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Health ----
@app.get("/")
def root():
    return {"ok": True, "service": "smm-backend"}

@app.get("/health")
def health(db: Session = Depends(get_db)):
    # اختبار اتصال قاعدة البيانات
    db.execute("SELECT 1")
    return {"status": "ok"}

# مسار فحص بديل لتوافق التطبيقات القديمة
@app.get("/api/health")
def health_alias(db: Session = Depends(get_db)):
    db.execute("SELECT 1")
    return {"status": "ok"}

# ---- مثال بسيط: إنشاء/تأكيد المستخدم بالـ UID ----
@app.post("/api/users/ensure")
def ensure_user(uid: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.uid == uid).first()
    if not user:
        user = models.User(uid=uid)
        db.add(user)
        db.commit()
        db.refresh(user)
    return {"uid": user.uid, "balance": user.balance, "role": user.role}

# ---- حفظ/جلب إشعارات ----
@app.post("/api/notices")
def create_notice(title: str, body: str, uid: str | None = None, for_owner: bool = False, db: Session = Depends(get_db)):
    n = models.Notice(title=title, body=body, uid=uid, for_owner=for_owner)
    db.add(n)
    db.commit()
    db.refresh(n)
    return {"id": n.id}

@app.get("/api/notices")
def list_notices(uid: str | None = None, for_owner: bool | None = None, db: Session = Depends(get_db)):
    q = db.query(models.Notice)
    if uid is not None:
        q = q.filter(models.Notice.uid == uid)
    if for_owner is not None:
        q = q.filter(models.Notice.for_owner == for_owner)
    q = q.order_by(models.Notice.id.desc()).limit(50)
    data = [{"id": x.id, "title": x.title, "body": x.body, "uid": x.uid, "for_owner": x.for_owner} for x in q.all()]
    return {"items": data}

# ---- حفظ توكن FCM ----
@app.post("/api/tokens/register")
def register_token(token: str, uid: str | None = None, for_owner: bool = False, db: Session = Depends(get_db)):
    exists = db.query(models.Token).filter(models.Token.token == token).first()
    if exists:
        # تحديث المالك/المستخدم ان تغير
        exists.uid = uid
        exists.for_owner = for_owner
        db.commit()
        return {"ok": True}
    t = models.Token(token=token, uid=uid, for_owner=for_owner)
    db.add(t)
    db.commit()
    return {"ok": True}

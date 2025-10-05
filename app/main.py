# app/main.py
from __future__ import annotations

import os
from typing import Dict, List, Optional

from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import event, select, func
from sqlalchemy.orm import Session

from .db import engine, SessionLocal
from .models import Base, User, Wallet, Service, Order

# -----------------------------------------------------------------------------
# إعداد التطبيق
# -----------------------------------------------------------------------------
app = FastAPI(title="Ratlwzan SMM API", version="1.0.0")

# CORS (اسمح للتطبيقات العميلة بالاتصال)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API KEY من إعدادات هيروكو (Config Vars)
API_KEY = os.getenv("API_KEY", "").strip()


# -----------------------------------------------------------------------------
# ربط السكيمـا "smm" + إنشاء الجداول عند الإقلاع
# -----------------------------------------------------------------------------
# نضبط search_path لكل اتصال جديد (حتى مع الـ pool)
@event.listens_for(engine, "connect")
def _set_search_path(dbapi_connection, connection_record):
    cur = dbapi_connection.cursor()
    try:
        cur.execute("SET search_path TO smm, public;")
    finally:
        cur.close()


@app.on_event("startup")
def _startup():
    # أنشئ سكيمـا smm إن لم تكن موجودة ثم الجداول
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS smm;")
        conn.exec_driver_sql("SET search_path TO smm, public;")
    Base.metadata.create_all(bind=engine)
    # ازرع خدمات افتراضية إن لم توجد
    with SessionLocal() as db:
        _seed_services_if_empty(db)


# -----------------------------------------------------------------------------
# أدوات مساعدة (DB + مصادقة)
# -----------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        # ضمان الـ search_path حتى على مستوى الـSession
        db.execute(func.set_config("search_path", "smm, public", True))
        yield db
    finally:
        db.close()


def require_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-KEY")):
    if API_KEY:
        if not x_api_key or x_api_key != API_KEY:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def _get_or_create_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        user = User(id=user_id, username=None, is_admin=False)
        db.add(user)
        db.commit()
        db.refresh(user)
    # أنشئ المحفظة إن لم تكن موجودة
    wallet = db.get(Wallet, user.id)
    if not wallet:
        wallet = Wallet(user_id=user.id, balance=0.0)
        db.add(wallet)
        db.commit()
    return user


def _seed_services_if_empty(db: Session):
    existing = db.execute(select(func.count(Service.id))).scalar_one()
    if existing and existing > 0:
        return
    # مجموعة أولية كافية للمزامنة مع التطبيق (يمكن توسيعها لاحقًا)
    seed: List[Service] = []
    def add(cat: str, name: str, price: float):
        seed.append(Service(category=cat, name=name, price=price))

    # TikTok/Instagram/Views/Likes/Score
    cat_a = "TikTok/Instagram/Views/Likes/Score"
    add(cat_a, "متابعين تيكتوك 1k", 3.50)
    add(cat_a, "متابعين تيكتوك 2k", 7.00)
    add(cat_a, "مشاهدات تيكتوك 10k", 0.80)
    add(cat_a, "لايكات تيكتوك 1k", 1.00)
    add(cat_a, "متابعين انستغرام 1k", 3.00)
    add(cat_a, "مشاهدات انستغرام 10k", 0.80)
    add(cat_a, "رفع سكور بثك1k", 2.00)

    # Telegram
    cat_t = "Telegram"
    add(cat_t, "اعضاء قنوات تلي 1k", 3.00)
    add(cat_t, "اعضاء كروبات تلي 1k", 3.00)

    # PUBG
    cat_p = "PUBG"
    add(cat_p, "ببجي 60 شدة", 2.00)
    add(cat_p, "ببجي 660 شدة", 15.00)

    # iTunes
    cat_i = "iTunes"
    add(cat_i, "شراء رصيد 5 ايتونز", 9.00)
    add(cat_i, "شراء رصيد 10 ايتونز", 18.00)

    # Mobile (اثير/اسيا/كورك)
    cat_m = "Mobile"
    add(cat_m, "شراء رصيد 10دولار اثير", 10.00)
    add(cat_m, "شراء رصيد 10دولار اسيا", 10.00)
    add(cat_m, "شراء رصيد 10دولار كورك", 10.00)

    # Ludo
    cat_l = "Ludo"
    add(cat_l, "لودو 810 الماسة", 3.00)
    add(cat_l, "لودو 2280 الماسة", 7.00)

    db.add_all(seed)
    db.commit()


# -----------------------------------------------------------------------------
# نماذج الطلب/الاستجابة (Pydantic)
# -----------------------------------------------------------------------------
class WalletAmount(BaseModel):
    user_id: int = Field(..., ge=1)
    amount: float = Field(..., gt=0)


class OrderCreate(BaseModel):
    user_id: int = Field(..., ge=1)
    category: str
    service_name: str
    qty: int = Field(..., gt=0)
    price: float = Field(..., gt=0)
    link: Optional[str] = None


# -----------------------------------------------------------------------------
# المسارات
# -----------------------------------------------------------------------------
@app.get("/health")
def health(db: Session = Depends(get_db)):
    # اختبار بسيط لقاعدة البيانات
    try:
        db.execute(select(func.now()))
        db_ok = True
    except Exception:
        db_ok = False
    return {"ok": True, "db": db_ok, "schema": "smm"}


@app.get("/services")
def get_services(db: Session = Depends(get_db)):
    """
    يعيد الخدمات مجمعة حسب الفئة بالشكل الذي يتوقعه تطبيق الأندرويد:
    {
      "buckets": {
        "Category": [{"name": "...", "base_price": ...}, ...],
        ...
      }
    }
    """
    rows = db.execute(select(Service.category, Service.name, Service.price).order_by(Service.category, Service.id)).all()
    buckets: Dict[str, List[Dict[str, float]]] = {}
    for cat, name, price in rows:
        buckets.setdefault(cat, []).append({"name": name, "base_price": float(price)})
    return {"buckets": buckets}


@app.get("/wallet/{user_id}")
def get_wallet(user_id: int, db: Session = Depends(get_db)):
    user = _get_or_create_user(db, user_id)
    wallet = db.get(Wallet, user.id)
    bal = float(wallet.balance if wallet else 0.0)
    return {"user_id": user.id, "balance": bal}


@app.post("/wallet/deposit")
def deposit(req: WalletAmount, db: Session = Depends(get_db), _=Depends(require_api_key)):
    user = _get_or_create_user(db, req.user_id)
    wallet = db.get(Wallet, user.id)
    wallet.balance = float(wallet.balance) + float(req.amount)
    db.add(wallet)
    db.commit()
    return {"user_id": user.id, "balance": float(wallet.balance)}


@app.post("/wallet/withdraw")
def withdraw(req: WalletAmount, db: Session = Depends(get_db), _=Depends(require_api_key)):
    user = _get_or_create_user(db, req.user_id)
    wallet = db.get(Wallet, user.id)
    if float(wallet.balance) < float(req.amount):
        raise HTTPException(status_code=400, detail="Insufficient balance")
    wallet.balance = float(wallet.balance) - float(req.amount)
    db.add(wallet)
    db.commit()
    return {"user_id": user.id, "balance": float(wallet.balance)}


@app.post("/orders", status_code=201)
def create_order(req: OrderCreate, db: Session = Depends(get_db), _=Depends(require_api_key)):
    _get_or_create_user(db, req.user_id)  # يضمن وجود المستخدم ومحفظته
    order = Order(
        user_id=req.user_id,
        category=req.category,
        service_name=req.service_name,
        qty=req.qty,
        price=req.price,
        link=req.link or "",
        status="pending",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return {
        "id": order.id,
        "user_id": order.user_id,
        "status": order.status,
        "price": float(order.price),
        "qty": order.qty,
    }


@app.get("/orders/{user_id}")
def list_orders(user_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        select(Order.id, Order.category, Order.service_name, Order.qty, Order.price, Order.status, Order.created_at)
        .where(Order.user_id == user_id)
        .order_by(Order.id.desc())
    ).all()
    return [
        {
            "id": r.id,
            "category": r.category,
            "service_name": r.service_name,
            "qty": r.qty,
            "price": float(r.price),
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

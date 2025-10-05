import os, time
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from .db import SessionLocal, engine
from .models import Base, User, Wallet, Moderator, Order, PriceOverride, QtyOverride, CardSubmission

# إنشاء الجداول عند الإقلاع
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ratlwzan Services API", version="1.0.0")

# السماح لتطبيق الأندرويد بالاتصال مباشرة
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # يمكنك تضييقها لاحقًا
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY  = os.getenv("API_KEY", "change-me")   # ضع قيمة قوية في Heroku
OWNER_PIN = os.getenv("OWNER_PIN", "123456")   # نفس PIN في التطبيق لو أردت

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def require_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")
    return True

# ------- نماذج الطلب/الرد
class ServiceItem(BaseModel):
    name: str
    base_price: float

class ServicesResponse(BaseModel):
    buckets: Dict[str, List[ServiceItem]]

class CreateOrderReq(BaseModel):
    user_id: int = 1
    category: str = "smm"
    service_name: str
    qty: int
    price: float
    link: str = ""

class OrderDTO(BaseModel):
    id: int
    user_id: int
    category: str
    service_name: str
    qty: int
    price: float
    status: str
    link: str
    ts: int

    @staticmethod
    def from_model(o: Order) -> "OrderDTO":
        return OrderDTO(
            id=o.id, user_id=o.user_id, category=o.category, service_name=o.service_name,
            qty=o.qty, price=o.price, status=o.status, link=o.link, ts=o.ts
        )

class AmountReq(BaseModel):
    user_id: int = 1
    amount: float

class CardReq(BaseModel):
    user_id: int = 1
    digits: str

class OverrideReq(BaseModel):
    service: str
    value: float | int

class ModReq(BaseModel):
    user_id: int

# ------- خدمات ثابتة (مطابقة لخرائط التطبيق)
SERVICES: Dict[str, Dict[str, float]] = {
    "TikTok/Instagram/Views/Likes/Score": {
        "متابعين تيكتوك 1k": 3.50, "متابعين تيكتوك 2k": 7.0, "متابعين تيكتوك 3k": 10.50, "متابعين تيكتوك 4k": 14.0,
        "مشاهدات تيكتوك 1k": 0.10, "مشاهدات تيكتوك 10k": 0.80, "مشاهدات تيكتوك 20k": 1.60, "مشاهدات تيكتوك 30k": 2.40, "مشاهدات تيكتوك 50k": 3.20,
        "متابعين انستغرام 1k": 3.0, "متابعين انستغرام 2k": 6.0, "متابعين انستغرام 3k": 9.0, "متابعين انستغرام 4k": 12.0,
        "لايكات تيكتوك 1k": 1.0, "لايكات تيكتوك 2k": 2.0, "لايكات تيكتوك 3k": 3.0, "لايكات تيكتوك 4k": 4.0,
        "لايكات انستغرام 1k": 1.0, "لايكات انستغرام 2k": 2.0, "لايكات انستغرام 3k": 3.0, "لايكات انستغرام 4k": 4.0,
        "مشاهدات انستغرام 10k": 0.80, "مشاهدات انستغرام 20k": 1.60, "مشاهدات انستغرام 30k": 2.40, "مشاهدات انستغرام 50k": 3.20,
        "مشاهدات بث تيكتوك 1k": 2.0, "مشاهدات بث تيكتوك 2k": 4.0, "مشاهدات بث تيكتوك 3k": 6.0, "مشاهدات بث تيكتوك 4k": 8.0,
        "مشاهدات بث انستغرام 1k": 2.0, "مشاهدات بث انستغرام 2k": 4.0, "مشاهدات بث انستغرام 3k": 6.0, "مشاهدات بث انستغرام 4k": 8.0,
        "رفع سكور بثك1k": 2.0, "رفع سكور بثك2k": 4.0, "رفع سكور بثك3k": 6.0, "رفع سكور بثك10k": 20.0
    },
    "Telegram": {
        "اعضاء قنوات تلي 1k": 3.0, "اعضاء قنوات تلي 2k": 6.0, "اعضاء قنوات تلي 3k": 9.0, "اعضاء قنوات تلي 4k": 12.0, "اعضاء قنوات تلي 5k": 15.0,
        "اعضاء كروبات تلي 1k": 3.0, "اعضاء كروبات تلي 2k": 6.0, "اعضاء كروبات تلي 3k": 9.0, "اعضاء كروبات تلي 4k": 12.0, "اعضاء كروبات تلي 5k": 15.0
    },
    "PUBG": {
        "ببجي 60 شدة": 2.0, "ببجي 120 شده": 4.0, "ببجي 180 شدة": 6.0, "ببجي 240 شدة": 8.0, "ببجي 325 شدة": 9.0,
        "ببجي 660 شدة": 15.0, "ببجي 1800 شدة": 40.0
    },
    "iTunes": {
        "شراء رصيد 5 ايتونز": 9.0, "شراء رصيد 10 ايتونز": 18.0, "شراء رصيد 15 ايتونز": 27.0, "شراء رصيد 20 ايتونز": 36.0,
        "شراء رصيد 25 ايتونز": 45.0, "شراء رصيد 30 ايتونز": 54.0, "شراء رصيد 35 ايتونز": 63.0, "شراء رصيد 40 ايتونز": 72.0,
        "شراء رصيد 45 ايتونز": 81.0, "شراء رصيد 50 ايتونز": 90.0
    },
    "Mobile": {
        "شراء رصيد 2دولار اثير": 2.0, "شراء رصيد 5دولار اثير": 5.0, "شراء رصيد 10دولار اثير": 10.0, "شراء رصيد 15دولار اثير": 15.0, "شراء رصيد 40دولار اثير": 40.0,
        "شراء رصيد 2دولار اسيا": 2.0, "شراء رصيد 5دولار اسيا": 5.0, "شراء رصيد 10دولار اسيا": 10.0, "شراء رصيد 15دولار اسيا": 15.0, "شراء رصيد 40دولار اسيا": 40.0,
        "شراء رصيد 2دولار كورك": 2.0, "شراء رصيد 5دولار كورك": 5.0, "شراء رصيد 10دولار كورك": 10.0, "شراء رصيد 15دولار كورك": 15.0, "شراء رصيد 40دولار كورك": 40.0
    },
    "Ludo": {
        "لودو 810 الماسة": 3.0, "لودو 2280 الماسة": 7.0, "لودو 5080 الماسة": 13.0, "لودو 12750 الماسة": 28.0,
        "لودو 66680 ذهب": 3.0, "لودو 219500 ذهب": 7.0, "لودو 1443000 ذهب": 13.0, "لودو 3627000 ذهب": 28.0
    }
}

# --------- Helpers
def ensure_user(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if not u:
        u = User(id=user_id, name=f"user-{user_id}")
        db.add(u)
        db.flush()
    w = db.get(Wallet, user_id)
    if not w:
        w = Wallet(user_id=user_id, balance=0.0)
        db.add(w)
    db.commit()
    return u

# --------- Routes
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/services", response_model=ServicesResponse)
def get_services(db: Session = Depends(get_db)):
    # تطبيق Overrides من قاعدة البيانات على النسخة الراجعة (اختياري للعرض)
    buckets: Dict[str, List[ServiceItem]] = {}
    # اجلب الـoverrides
    price_map = {p.service: p.price for p in db.execute(select(PriceOverride)).scalars()}
    for bucket, items in SERVICES.items():
        lst: List[ServiceItem] = []
        for name, base in items.items():
            lst.append(ServiceItem(name=name, base_price=float(price_map.get(name, base))))
        buckets[bucket] = lst
    return ServicesResponse(buckets=buckets)

@app.get("/wallet/{user_id}")
def get_wallet(user_id: int, db: Session = Depends(get_db)):
    u = ensure_user(db, user_id)
    return {"user_id": user_id, "balance": db.get(Wallet, user_id).balance}

@app.post("/wallet/deposit")
def deposit(req: AmountReq, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    ensure_user(db, req.user_id)
    w = db.get(Wallet, req.user_id)
    w.balance = max(0.0, (w.balance or 0.0) + max(0.0, req.amount))
    db.add(w); db.commit()
    return {"ok": True, "balance": w.balance}

@app.post("/wallet/withdraw")
def withdraw(req: AmountReq, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    ensure_user(db, req.user_id)
    w = db.get(Wallet, req.user_id)
    if req.amount > (w.balance or 0.0):
        raise HTTPException(400, "insufficient balance")
    w.balance -= req.amount
    db.add(w); db.commit()
    return {"ok": True, "balance": w.balance}

@app.post("/orders", response_model=OrderDTO)
def create_order(req: CreateOrderReq, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    ensure_user(db, req.user_id)
    o = Order(
        user_id=req.user_id, category=req.category, service_name=req.service_name,
        qty=req.qty, price=req.price, status="pending", link=req.link, ts=int(time.time()*1000)
    )
    db.add(o); db.commit(); db.refresh(o)
    return OrderDTO.from_model(o)

@app.get("/orders", response_model=List[OrderDTO])
def list_orders(user_id: Optional[int] = None, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    q = select(Order).order_by(Order.id.desc())
    if user_id is not None:
        q = q.where(Order.user_id == user_id)
    rows = db.execute(q).scalars().all()
    return [OrderDTO.from_model(o) for o in rows]

@app.post("/card/submit")
def submit_card(req: CardReq, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    ensure_user(db, req.user_id)
    now = int(time.time() * 1000)
    # منع التكرار لنفس الرقم
    existing = db.execute(
        select(CardSubmission).where(CardSubmission.user_id == req.user_id, CardSubmission.digits == req.digits)
    ).scalars().all()
    if len(existing) >= 2:
        raise HTTPException(400, "duplicate card submitted too many times")

    # مكافحة السبام خلال نافذة 120 ثانية / 5 مرات
    window_ms = 120_000
    since = now - window_ms
    recent_count = db.execute(
        select(CardSubmission).where(CardSubmission.user_id == req.user_id, CardSubmission.ts >= since)
    ).scalars().all()
    if len(recent_count) >= 5:
        raise HTTPException(429, "too many submissions recently")

    sub = CardSubmission(user_id=req.user_id, digits=req.digits, ts=now)
    db.add(sub); db.commit()
    return {"ok": True, "message": "submitted"}

# ------- Owner APIs (تتطلب X-API-KEY)
@app.post("/owner/price_override")
def set_price_override(req: OverrideReq, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    row = db.execute(select(PriceOverride).where(PriceOverride.service == req.service)).scalar_one_or_none()
    if row:
        row.price = float(req.value)
    else:
        row = PriceOverride(service=req.service, price=float(req.value))
        db.add(row)
    db.commit()
    return {"ok": True}

@app.post("/owner/qty_override")
def set_qty_override(req: OverrideReq, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    row = db.execute(select(QtyOverride).where(QtyOverride.service == req.service)).scalar_one_or_none()
    if row:
        row.qty = int(req.value)
    else:
        row = QtyOverride(service=req.service, qty=int(req.value))
        db.add(row)
    db.commit()
    return {"ok": True}

@app.post("/owner/moderators/add")
def add_moderator(req: ModReq, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    if not db.get(Moderator, req.user_id):
        db.add(Moderator(user_id=req.user_id)); db.commit()
    return {"ok": True}

@app.post("/owner/moderators/remove")
def remove_moderator(req: ModReq, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    row = db.get(Moderator, req.user_id)
    if row:
        db.delete(row); db.commit()
    return {"ok": True}

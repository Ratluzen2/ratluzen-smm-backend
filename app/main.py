# app/main.py
from typing import Any, Dict, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db import init_db, get_db
from app.routers.smm import router as smm_router

app = FastAPI(title="Ratluzen SMM Backend", version="1.0.0")

# CORS — للسماح لتطبيق الأندرويد
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # يمكنك تضييقها لاحقاً
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _startup() -> None:
    await init_db()

# ========== نماذج Pydantic ==========
class UpsertUser(BaseModel):
    uid: str = Field(..., description="UID الخاص بالمستخدم")

class OrderCreate(BaseModel):
    uid: str = Field(..., description="UID الخاص بالمستخدم")
    service_name: str = Field(..., description="اسم الخدمة المعروضة داخل التطبيق")
    quantity: int = Field(..., ge=1)
    price: float = Field(..., ge=0)
    link: str = Field(..., description="الرابط/المعرف")
    # اختياري: لو عندك mapping إلى مزود SMM
    service_id: Optional[int] = Field(None, description="ID الخدمة في مزود SMM (اختياري)")

# ========== مسارات أساسية ==========
@app.get("/api/health")
async def health(db: AsyncConnection = Depends(get_db)) -> Dict[str, Any]:
    await db.execute(text("SELECT 1"))
    return {"ok": True}

@app.post("/api/users/upsert")
async def users_upsert(body: UpsertUser, db: AsyncConnection = Depends(get_db)) -> Dict[str, Any]:
    if not body.uid.strip():
        raise HTTPException(status_code=400, detail="uid فارغ")
    await db.execute(
        text("INSERT INTO users(uid) VALUES (:u) ON CONFLICT (uid) DO NOTHING"),
        {"u": body.uid.strip()},
    )
    return {"ok": True, "uid": body.uid.strip()}

@app.post("/api/orders")
async def create_order(body: OrderCreate, db: AsyncConnection = Depends(get_db)) -> Dict[str, Any]:
    # تأكد أن المستخدم موجود
    await db.execute(
        text("INSERT INTO users(uid) VALUES (:u) ON CONFLICT (uid) DO NOTHING"),
        {"u": body.uid.strip()},
    )

    # إنشاء الطلب محلياً
    result = await db.execute(
        text("""
            INSERT INTO orders(uid, service_name, quantity, price, link)
            VALUES (:uid, :svc, :q, :p, :lnk)
            RETURNING id
        """),
        {"uid": body.uid.strip(), "svc": body.service_name, "q": body.quantity, "p": body.price, "lnk": body.link},
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=500, detail="فشل إنشاء الطلب")
    order_id = row[0]

    # لو أرسلت service_id نطلب من مزود SMM مباشرة ونخزن provider_order_id
    if body.service_id is not None:
        from app.providers.smm_client import SmmClient  # import متأخر لتفادي كلفة الإقلاع
        try:
            c = SmmClient()
            j = await c.add_order(service_id=body.service_id, link=body.link, quantity=body.quantity)
            provider_order_id: Optional[str] = None
            if isinstance(j, dict) and "order" in j:
                provider_order_id = str(j["order"])
                await db.execute(
                    text("UPDATE orders SET provider_order_id = :po WHERE id = :oid"),
                    {"po": provider_order_id, "oid": order_id},
                )
        except Exception:
            # لا نفشل الطلب المحلي — فقط نسجّل أنه لم يُرفع للمزوّد
            pass

    return {"ok": True, "id": order_id}

@app.get("/api/orders/{order_id}")
async def get_order(order_id: int, db: AsyncConnection = Depends(get_db)) -> Dict[str, Any]:
    res = await db.execute(
        text("SELECT id, uid, service_name, quantity, price, link, status, provider_order_id, created_at FROM orders WHERE id = :i"),
        {"i": order_id}
    )
    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="الطلب غير موجود")
    cols = ["id", "uid", "service_name", "quantity", "price", "link", "status", "provider_order_id", "created_at"]
    return dict(zip(cols, row))

# ضمّ راوتر الـ SMM تحت /api/smm
app.include_router(smm_router, prefix="/api/smm", tags=["smm"])

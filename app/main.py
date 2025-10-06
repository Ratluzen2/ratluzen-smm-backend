from fastapi import FastAPI, Depends, HTTPException, Body, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database import Base, engine, get_session
from app.models import User, Order, Notice, TopupCard
from app.config import KD_API_KEY, KD_API_URL, OWNER_PASS, APPROVAL_REQUIRED
from app.provider_map import SERVICE_ID, PRICE_PER_K
import httpx, math

app = FastAPI(title="Ratluzen SMM Backend")

# لو حبيت تفتح من أي مكان (Android لا يحتاج CORS، لكن لا ضرر)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/health")
async def health():
    return {"ok": True, "app": "ratluzen", "provider_key_loaded": bool(KD_API_KEY)}

# =============== أدوات مساعدة ===============
async def ensure_user(sess: AsyncSession, uid: str) -> User:
    res = await sess.execute(select(User).where(User.uid == uid))
    user = res.scalar_one_or_none()
    if not user:
        user = User(uid=uid, balance=0.0)
        sess.add(user)
        await sess.flush()
    return user

async def add_notice(sess: AsyncSession, title: str, body: str, uid: str | None, for_owner: bool):
    n = Notice(uid=uid, title=title, body=body, for_owner=for_owner)
    sess.add(n)
    await sess.flush()

def compute_price(service_key: str, quantity: int) -> float:
    ppk = PRICE_PER_K.get(service_key, 0.0)
    price = (quantity / 1000.0) * ppk
    return math.ceil(price * 100) / 100.0

# =============== مستخدمون ===============
@app.post("/api/users/upsert")
async def upsert_user(payload: dict = Body(...), sess: AsyncSession = Depends(get_session)):
    uid = (payload.get("uid") or "").strip()
    if not uid:
        raise HTTPException(400, "uid required")
    user = await ensure_user(sess, uid)
    await sess.commit()
    return {"ok": True, "uid": user.uid, "balance": user.balance}

# =============== إشعارات ===============
@app.get("/api/app/notices")
async def list_notices(uid: str | None = Query(None), owner: int = Query(0), sess: AsyncSession = Depends(get_session)):
    if owner == 1:
        res = await sess.execute(select(Notice).where(Notice.for_owner == True).order_by(Notice.id.desc()).limit(200))
    else:
        if not uid:
            raise HTTPException(400, "uid required")
        res = await sess.execute(select(Notice).where(Notice.for_owner == False, Notice.uid == uid).order_by(Notice.id.desc()).limit(200))
    items = []
    for n in res.scalars().all():
        items.append({"id": n.id, "title": n.title, "body": n.body, "created_at": str(n.created_at)})
    return {"ok": True, "items": items}

# =============== محفظة ===============
@app.get("/api/wallet/balance")
async def wallet_balance(uid: str = Query(...), sess: AsyncSession = Depends(get_session)):
    user = await ensure_user(sess, uid)
    await sess.commit()
    return {"ok": True, "uid": uid, "balance": user.balance}

@app.post("/api/wallet/topup_card")
async def submit_topup_card(
    payload: dict = Body(...),
    sess: AsyncSession = Depends(get_session)
):
    uid = (payload.get("uid") or "").strip()
    provider = (payload.get("provider") or "asiacell").strip()
    card_number = (payload.get("card_number") or "").strip()
    if not uid or not card_number:
        raise HTTPException(400, "uid and card_number required")
    await ensure_user(sess, uid)
    tc = TopupCard(uid=uid, provider=provider, card_number=card_number, status="pending")
    sess.add(tc)
    await add_notice(sess, "كارت جديد", f"Provider={provider} | Card={card_number} | UID={uid}", None, True)
    await add_notice(sess, "تم استلام كارتك", "أُرسل الكارت للمراجعة.", uid, False)
    await sess.commit()
    return {"ok": True, "card_id": tc.id}

# (للمالك) قبول/رفض كارت
@app.post("/api/admin/cards/{card_id}/accept")
async def accept_card(card_id: int, amount: float = Body(..., embed=True),
                      x_owner_auth: str = Header(""), sess: AsyncSession = Depends(get_session)):
    if x_owner_auth != OWNER_PASS:
        raise HTTPException(401, "unauthorized")
    res = await sess.execute(select(TopupCard).where(TopupCard.id == card_id))
    card = res.scalar_one_or_none()
    if not card or card.status != "pending":
        raise HTTPException(404, "not pending")
    # أضف رصيد
    u = await ensure_user(sess, card.uid)
    u.balance = (u.balance or 0.0) + float(amount)
    card.status = "accepted"; card.amount = float(amount)
    await add_notice(sess, "شحن رصيد", f"تم شحن رصيدك بمبلغ {amount}$", card.uid, False)
    await sess.commit()
    return {"ok": True}

@app.post("/api/admin/cards/{card_id}/reject")
async def reject_card(card_id: int, reason: str = Body("", embed=True),
                      x_owner_auth: str = Header(""), sess: AsyncSession = Depends(get_session)):
    if x_owner_auth != OWNER_PASS:
        raise HTTPException(401, "unauthorized")
    res = await sess.execute(select(TopupCard).where(TopupCard.id == card_id))
    card = res.scalar_one_or_none()
    if not card or card.status != "pending":
        raise HTTPException(404, "not pending")
    card.status = "rejected"
    await add_notice(sess, "رفض كارت", f"عُذراً، تم رفض الكارت: {reason}", card.uid, False)
    await sess.commit()
    return {"ok": True}

@app.get("/api/admin/cards/pending")
async def list_pending_cards(x_owner_auth: str = Header(""), sess: AsyncSession = Depends(get_session)):
    if x_owner_auth != OWNER_PASS: raise HTTPException(401, "unauthorized")
    res = await sess.execute(select(TopupCard).where(TopupCard.status == "pending").order_by(TopupCard.id.desc()).limit(200))
    items = [{"id": c.id, "uid": c.uid, "provider": c.provider, "card_number": c.card_number, "created_at": str(c.created_at)} for c in res.scalars().all()]
    return {"ok": True, "items": items}

# =============== مزوّد KD: رصيد/حالة ===============
@app.get("/api/provider/balance")
async def provider_balance():
    if not KD_API_KEY:
        raise HTTPException(500, "KD_API_KEY not configured")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(KD_API_URL, data={"key": KD_API_KEY, "action": "balance"})
        return {"ok": True, "raw": r.json()}

@app.post("/api/provider/status")
async def provider_status(payload: dict = Body(...)):
    if not KD_API_KEY:
        raise HTTPException(500, "KD_API_KEY not configured")
    order_id = str(payload.get("order_id", "")).strip()
    if not order_id:
        raise HTTPException(400, "order_id required")
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(KD_API_URL, data={"key": KD_API_KEY, "action":"status", "order": order_id})
        return {"ok": True, "raw": r.json()}

# =============== طلب خدمة من التطبيق ===============
@app.post("/api/provider/order")
async def queue_or_place_order(payload: dict = Body(...), sess: AsyncSession = Depends(get_session)):
    """
    تُستدعى من التطبيق كما هي.
    - تحفظ الطلب في قاعدة البيانات كـ pending مع خصم السعر من رصيد المستخدم.
    - لا تُرسل للـ KD مباشرة إذا كان APPROVAL_REQUIRED=true (وضع الطلبات المعلقة).
    - إذا كان false تُرسل فوراً.
    """
    uid = (payload.get("uid") or "").strip()   # رجاءً حدّث الواجهة لإرسال uid هنا
    service_key = (payload.get("service_key") or "").strip()
    link = (payload.get("link") or "").strip()
    quantity = int(payload.get("quantity") or 0)
    if not uid or not service_key or not link or quantity <= 0:
        raise HTTPException(400, "uid, service_key, link, quantity required")

    if service_key not in SERVICE_ID:
        raise HTTPException(400, "unknown service_key")
    sid = SERVICE_ID[service_key]
    price = compute_price(service_key, quantity)

    # تأكد من المستخدم والرصيد
    user = await ensure_user(sess, uid)
    if user.balance < price:
        raise HTTPException(400, "insufficient balance")

    # أنشئ الطلب وخصم الرصيد
    user.balance = round(user.balance - price, 2)
    order = Order(uid=uid, service_key=service_key, service_id=sid, link=link, quantity=quantity, price=price)
    sess.add(order)
    await add_notice(sess, "طلب معلّق", f"استلمنا طلب {service_key} ({quantity}) وسيُراجع قريباً.", uid, False)
    await add_notice(sess, "طلب خدمات جديد", f"{service_key} x{quantity} | UID={uid}", None, True)

    if not APPROVAL_REQUIRED:
        # إرسال مباشر إلى KD
        if not KD_API_KEY:
            raise HTTPException(500, "KD_API_KEY not configured")
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(KD_API_URL, data={
                "key": KD_API_KEY, "action": "add",
                "service": sid, "link": link, "quantity": quantity
            })
            data = r.json()
            if "order" in data:
                order.provider_order_id = str(data["order"])
                order.status = "processing"
                await add_notice(sess, "تم إرسال الطلب", f"رقم المزود: {order.provider_order_id}", uid, False)
            else:
                # فشل — أعد الرصيد وعلّم الطلب failed
                user.balance = round(user.balance + price, 2)
                order.status = "failed"
                await add_notice(sess, "فشل إرسال الطلب", f"يرجى المحاولة لاحقاً.", uid, False)

    await sess.commit()
    return {"ok": True, "queued": APPROVAL_REQUIRED, "order_id": order.id}

# =============== لوحة المالك: تنفيذ/رفض الطلبات المعلقة (الخدمات) ===============
@app.get("/api/admin/orders/pending")
async def admin_list_pending(x_owner_auth: str = Header(""), sess: AsyncSession = Depends(get_session)):
    if x_owner_auth != OWNER_PASS: raise HTTPException(401, "unauthorized")
    res = await sess.execute(select(Order).where(Order.status == "pending").order_by(Order.id.desc()).limit(200))
    out = []
    for o in res.scalars().all():
        out.append({
            "id": o.id, "uid": o.uid, "service_key": o.service_key, "service_id": o.service_id,
            "quantity": o.quantity, "price": o.price, "link": o.link, "created_at": str(o.created_at)
        })
    return {"ok": True, "items": out}

@app.post("/api/admin/orders/{order_id}/approve")
async def admin_approve(order_id: int, x_owner_auth: str = Header(""), sess: AsyncSession = Depends(get_session)):
    if x_owner_auth != OWNER_PASS: raise HTTPException(401, "unauthorized")
    res = await sess.execute(select(Order).where(Order.id == order_id))
    o = res.scalar_one_or_none()
    if not o or o.status != "pending":
        raise HTTPException(404, "not pending")
    if not KD_API_KEY:
        raise HTTPException(500, "KD_API_KEY not configured")

    # أرسل للـ KD
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.post(KD_API_URL, data={
            "key": KD_API_KEY, "action": "add",
            "service": o.service_id, "link": o.link, "quantity": o.quantity
        })
        data = r.json()
        if "order" in data:
            o.provider_order_id = str(data["order"])
            o.status = "processing"
            await add_notice(sess, "تم إرسال طلبك", f"رقم المزود: {o.provider_order_id}", o.uid, False)
            await add_notice(sess, "تمت الموافقة", f"Order #{o.id} أُرسل للمزود.", None, True)
        else:
            # فشل الإرسال — أعد الرصيد وعلّم فشل
            res_u = await sess.execute(select(User).where(User.uid == o.uid))
            u = res_u.scalar_one()
            u.balance = round(u.balance + o.price, 2)
            o.status = "failed"
            await add_notice(sess, "تعذّر تنفيذ الطلب", "تم رد المبلغ لرصيدك.", o.uid, False)
    await sess.commit()
    return {"ok": True, "provider_order_id": o.provider_order_id}

@app.post("/api/admin/orders/{order_id}/reject")
async def admin_reject(order_id: int, reason: str = Body(""), x_owner_auth: str = Header(""), sess: AsyncSession = Depends(get_session)):
    if x_owner_auth != OWNER_PASS: raise HTTPException(401, "unauthorized")
    res = await sess.execute(select(Order).where(Order.id == order_id))
    o = res.scalar_one_or_none()
    if not o or o.status != "pending":
        raise HTTPException(404, "not pending")
    # رد الرصيد وعلّم مرفوض
    res_u = await sess.execute(select(User).where(User.uid == o.uid))
    u = res_u.scalar_one()
    u.balance = round(u.balance + o.price, 2)
    o.status = "rejected"
    await add_notice(sess, "رفض الطلب", f"عذراً، تم رفض طلبك. السبب: {reason}", o.uid, False)
    await add_notice(sess, "رُفض الطلب", f"Order #{o.id} رُفض.", None, True)
    await sess.commit()
    return {"ok": True}

# (اختياري) تحديث حالة الطلب من KD (يمكن للمالك نداءها يدوياً)
@app.post("/api/admin/orders/{order_id}/refresh")
async def admin_refresh(order_id: int, x_owner_auth: str = Header(""), sess: AsyncSession = Depends(get_session)):
    if x_owner_auth != OWNER_PASS: raise HTTPException(401, "unauthorized")
    res = await sess.execute(select(Order).where(Order.id == order_id))
    o = res.scalar_one_or_none()
    if not o or not o.provider_order_id:
        raise HTTPException(404, "no provider_order_id")
    if not KD_API_KEY:
        raise HTTPException(500, "KD_API_KEY not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(KD_API_URL, data={"key": KD_API_KEY, "action":"status", "order": o.provider_order_id})
        data = r.json()
        # مجرد مثال: لو status == Completed نغلق الطلب
        st = str(data.get("status", "")).lower()
        if "completed" in st or "success" in st or "finished" in st:
            o.status = "completed"
            await add_notice(sess, "اكتمل طلبك", f"Order #{o.id} اكتمل.", o.uid, False)
            await add_notice(sess, "أُغلق الطلب", f"Order #{o.id} اكتمل.", None, True)
        await sess.commit()
    return {"ok": True, "raw": data}

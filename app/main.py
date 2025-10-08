import uuid
from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .database import Base, engine, get_db
from .config import settings
from .models import User, Order
from .schemas import (APIResponse, OwnerLoginIn, TokenOut, RegisterUserIn, UserOut, 
                      CreateOrderIn, OrderOut, OrderStatusOut, AppConfigOut)
from .auth import create_access_token, owner_only
from .smm_client import SMMClient

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME, version="1.0.0")

# CORS for APK
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", response_model=APIResponse)
async def health():
    return APIResponse(ok=True, data={"app": settings.APP_NAME})

@app.get("/config", response_model=APIResponse)
async def get_config():
    return APIResponse(
        ok=True,
        data=AppConfigOut(
            support_telegram_url=settings.SUPPORT_TELEGRAM_URL,
            support_whatsapp_url=settings.SUPPORT_WHATSAPP_URL,
            app_name=settings.APP_NAME,
        ).dict()
    )

# -------- Owner auth (PIN -> JWT) --------
@app.post("/owner/login", response_model=APIResponse)
async def owner_login(payload: OwnerLoginIn):
    if payload.pin != settings.OWNER_PIN:
        raise HTTPException(status_code=401, detail="Wrong PIN")
    token = create_access_token({"role": "owner"})
    return APIResponse(ok=True, data=TokenOut(access_token=token).dict())

# -------- UID register --------
@app.post("/users/register", response_model=APIResponse)
def register_user(payload: RegisterUserIn, db: Session = Depends(get_db)):
    # Upsert (insert if not exists)
    user = db.get(User, payload.uid)
    if user is None:
        user = User(uid=payload.uid)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # race condition fallback
            user = db.get(User, payload.uid)
            if user is None:
                raise
    return APIResponse(ok=True, data=UserOut(uid=user.uid).dict())

# -------- Server status (also checks SMM API reachability) --------
@app.get("/server/ping", response_model=APIResponse)
async def server_ping():
    client = SMMClient()
    try:
        # A light call (services or balance); balance is lighter
        res = await client.balance()
        return APIResponse(ok=True, data={"upstream_ok": True, "balance_sample": res})
    except Exception as e:
        return APIResponse(ok=False, error=f"Upstream error: {str(e)}")

# -------- SMM API passthroughs --------
@app.get("/smm/balance", response_model=APIResponse)
async def smm_balance(_: dict = Depends(owner_only)):
    client = SMMClient()
    try:
        res = await client.balance()
        return APIResponse(ok=True, data=res)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.get("/smm/services", response_model=APIResponse)
async def smm_services(_: dict = Depends(owner_only)):
    client = SMMClient()
    try:
        res = await client.services()
        return APIResponse(ok=True, data=res)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/smm/order", response_model=APIResponse)
async def create_order(payload: CreateOrderIn, db: Session = Depends(get_db)):
    # Ensure user exists
    user = db.get(User, payload.uid)
    if user is None:
        # Auto-register if not present
        user = User(uid=payload.uid)
        db.add(user)
        db.commit()

    client = SMMClient()
    try:
        created = await client.add_order(service=payload.service, link=payload.link, quantity=payload.quantity)
        panel_order_id = int(created.get("order"))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to create panel order: {str(e)}")

    order = Order(
        id=str(uuid.uuid4()),
        uid=payload.uid,
        panel_order_id=panel_order_id,
        service=payload.service,
        quantity=payload.quantity,
        link=payload.link,
        status="pending"
    )
    db.add(order)
    db.commit()

    return APIResponse(
        ok=True,
        data=OrderOut(
            id=order.id, uid=order.uid, panel_order_id=order.panel_order_id,
            service=order.service, quantity=order.quantity, link=order.link, status=order.status
        ).dict()
    )

@app.get("/smm/order/{order_id}", response_model=APIResponse)
async def order_status(order_id: str, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    client = SMMClient()
    try:
        res = await client.status(order.panel_order_id)
        # Typical response: {"status":"Completed","charge":"0.05","start_count":"...","remains":"..."}
        order.status = res.get("status", order.status)
        try:
            order.charge = float(res.get("charge")) if "charge" in res and res.get("charge") is not None else order.charge
        except Exception:
            pass
        db.commit()
    except Exception as e:
        # Keep local status if upstream fails
        return APIResponse(ok=False, error=f"Upstream error: {str(e)}", data=OrderStatusOut(
            order_id=order.id,
            panel_order_id=order.panel_order_id,
            status=order.status,
            charge=order.charge
        ).dict())

    return APIResponse(ok=True, data=OrderStatusOut(
        order_id=order.id,
        panel_order_id=order.panel_order_id,
        status=order.status,
        charge=order.charge
    ).dict())

@app.get("/smm/order/by-uid/{uid}", response_model=APIResponse)
def list_orders(uid: str, db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.uid == uid).order_by(Order.created_at.desc()).limit(100).all()
    return APIResponse(ok=True, data=[
        {"id": o.id, "panel_order_id": o.panel_order_id, "service": o.service, "quantity": o.quantity, "status": o.status, "created_at": o.created_at.isoformat() if o.created_at else None}
        for o in q
    ])

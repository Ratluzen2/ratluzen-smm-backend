from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, ServiceOrder, Notice
from ..provider_map import PRICING, SERVICE_MAP, calc_price

r = APIRouter(prefix="/provider")

@r.post("/order")
def create_service_order(uid: str, service_key: str, link: str, quantity: int, db: Session = Depends(get_db)):
    if service_key not in PRICING:
        raise HTTPException(400, "unknown service_key")
    rule = PRICING[service_key]
    if not (rule["min"] <= quantity <= rule["max"]):
        raise HTTPException(400, f"quantity must be between {rule['min']} and {rule['max']}")
    if service_key not in SERVICE_MAP:
        raise HTTPException(400, "service_code not found")

    user = db.query(User).filter_by(uid=uid).first()
    if not user:
        raise HTTPException(404, "user not found")
    if user.is_banned:
        raise HTTPException(403, "user banned")

    price = calc_price(service_key, quantity)
    if user.balance < price:
        raise HTTPException(402, "insufficient_balance")

    # خصم الرصيد
    user.balance = round(user.balance - price, 2)
    db.add(user)

    order = ServiceOrder(
        uid=uid,
        service_key=service_key,
        service_code=SERVICE_MAP[service_key],
        link=link,
        quantity=quantity,
        unit_price_per_k=float(rule["pricePerK"]),
        price=price,
        status="pending"
    )
    db.add(order)

    # إشعار للمستخدم + للمالك (سِجل داخلي)
    db.add(Notice(title=f"طلب جديد ({service_key})",
                  body=f"الكمية: {quantity}\nالسعر: ${price}\nسيراجعه المالك قريباً.",
                  for_owner=False, uid=uid))
    db.add(Notice(title=f"طلب خدمات معلّق",
                  body=f"UID={uid} | {service_key} | qty={quantity} | price=${price}",
                  for_owner=True))

    db.commit(); db.refresh(order)
    return {"ok": True, "orderId": order.id, "price": price}

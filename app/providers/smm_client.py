import httpx
from typing import Any, Dict
from app.config import PROVIDER_BASE, PROVIDER_KEY

def _check_ready():
    if not PROVIDER_BASE or not PROVIDER_KEY:
        raise RuntimeError("Provider base/key not configured")

async def provider_balance() -> Dict[str, Any]:
    _check_ready()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(PROVIDER_BASE, data={"key": PROVIDER_KEY, "action": "balance"})
        r.raise_for_status()
        return r.json()

async def create_provider_order(service_id: int, link: str, quantity: int) -> Dict[str, Any]:
    _check_ready()
    payload = {
        "key": PROVIDER_KEY,
        "action": "add",
        "service": service_id,
        "link": link,
        "quantity": quantity
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(PROVIDER_BASE, data=payload)
        r.raise_for_status()
        return r.json()

async def provider_order_status(order_id: str) -> Dict[str, Any]:
    _check_ready()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(PROVIDER_BASE, data={"key": PROVIDER_KEY, "action": "status", "order": order_id})
        r.raise_for_status()
        return r.json()

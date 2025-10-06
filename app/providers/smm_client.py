import httpx
from typing import Any
from ..config import get_settings
from ..provider_map import PROVIDER_SERVICE_IDS

_settings = get_settings()

def place_order(service_key: str, link: str, quantity: int) -> dict[str, Any]:
    """
    ينشئ طلب عند المزوّد ويرجع json كما يرسله المزوّد.
    يعتمد على خريطة service_key -> service_id.
    """
    service_id = PROVIDER_SERVICE_IDS.get(service_key)
    if not service_id:
        return {"error": f"Unknown service_key: {service_key}"}

    payload = {
        "key": _settings.SMM_API_KEY,
        "action": "add",
        "service": service_id,
        "link": link,
        "quantity": quantity,
    }
    r = httpx.post(_settings.SMM_API_URL, data=payload, timeout=30.0)
    r.raise_for_status()
    return r.json()

def check_status(order_id: str) -> dict[str, Any]:
    payload = {"key": _settings.SMM_API_KEY, "action": "status", "order": order_id}
    r = httpx.post(_settings.SMM_API_URL, data=payload, timeout=30.0)
    r.raise_for_status()
    return r.json()

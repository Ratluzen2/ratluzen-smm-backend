# app/providers/smm_client.py
import os
import httpx
from typing import Any, Dict, List, Optional

SMM_API_URL = os.environ.get("SMM_API_URL", "").rstrip("/")
SMM_API_KEY = os.environ.get("SMM_API_KEY", "")

class SmmClient:
    """
    عميل عام للوحات SMM المتوافقة مع API v2:
    - action=balance / services / add / status
    - إرسال POST form-data: key, action, ...
    """
    def __init__(self, base_url: str = SMM_API_URL, api_key: str = SMM_API_KEY, timeout: float = 25.0):
        if not base_url or not api_key:
            raise RuntimeError("SMM_API_URL/SMM_API_KEY غير مضبوطة في Heroku.")
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout

    async def _post(self, data: Dict[str, Any]) -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for _ in range(3):  # إعادة محاولة خفيفة
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(self.base_url, data=data)
                    resp.raise_for_status()
                    try:
                        j = resp.json()
                    except Exception:
                        return {"raw": resp.text}
                    if isinstance(j, dict):
                        return j
                    return {"raw": j}
            except Exception as e:
                last_exc = e
        raise last_exc or RuntimeError("فشل التواصل مع مزود SMM")

    async def get_balance(self) -> Dict[str, Any]:
        return await self._post({"key": self.api_key, "action": "balance"})

    async def get_services(self) -> List[Dict[str, Any]]:
        j = await self._post({"key": self.api_key, "action": "services"})
        if isinstance(j, list):
            return j
        if isinstance(j, dict) and isinstance(j.get("services"), list):
            return j["services"]
        if isinstance(j, dict) and isinstance(j.get("raw"), list):
            return j["raw"]
        return []

    async def add_order(self, service_id: int, link: str, quantity: int) -> Dict[str, Any]:
        data = {
            "key": self.api_key,
            "action": "add",
            "service": service_id,
            "link": link,
            "quantity": quantity,
        }
        return await self._post(data)

    async def get_status(self, order_id: str) -> Dict[str, Any]:
        return await self._post({"key": self.api_key, "action": "status", "order": order_id})

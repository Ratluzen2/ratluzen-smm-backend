import httpx
from typing import Dict, Any
from ..provider_map import get_provider

class SMMClient:
    def __init__(self):
        p = get_provider()
        self.api_url = p["api_url"]
        self.api_key = p["api_key"]

    async def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = {"key": self.api_key}
        data.update(payload)
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(self.api_url, data=data)
            r.raise_for_status()
            return r.json()

    async def balance(self) -> Dict[str, Any]:
        return await self._post({"action": "balance"})

    async def services(self) -> Dict[str, Any]:
        return await self._post({"action": "services"})

    async def add_order(self, service: int, link: str, quantity: int) -> Dict[str, Any]:
        return await self._post({"action": "add", "service": service, "link": link, "quantity": quantity})

    async def status(self, order_id: int) -> Dict[str, Any]:
        return await self._post({"action": "status", "order": order_id})

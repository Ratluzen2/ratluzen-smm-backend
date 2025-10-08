import httpx
from ..config import SMM_API_URL, SMM_API_KEY

class SMMClient:
    def __init__(self):
        self.url = SMM_API_URL
        self.key = SMM_API_KEY

    async def _post(self, payload: dict):
        data = {"key": self.key}
        data.update(payload)
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(self.url, data=data)
            r.raise_for_status()
            return r.json()

    async def balance(self):  return await self._post({"action": "balance"})
    async def services(self): return await self._post({"action": "services"})
    async def add(self, service: int, link: str, quantity: int):
        return await self._post({"action": "add", "service": service, "link": link, "quantity": quantity})
    async def status(self, order_id: int):
        return await self._post({"action": "status", "order": order_id})

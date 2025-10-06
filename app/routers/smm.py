import os
import httpx

# خذ القيم من بيئة هيروكو
PANEL_URL = (os.getenv("SMM_PANEL_URL") or os.getenv("PROVIDER_BASE_URL") or "").rstrip("/")
API_KEY   = os.getenv("SMM_API_KEY") or os.getenv("PROVIDER_API_KEY")

class SMMProvider:
    def __init__(self, base_url: str | None = None, key: str | None = None):
        self.base_url = (base_url or PANEL_URL).rstrip("/")
        self.key = key or API_KEY

    def _form(self, action: str, **extra):
        data = {"key": self.key, "action": action}
        data.update(extra)
        return data

    async def get_balance(self) -> dict:
        if not self.base_url or not self.key:
            return {"ok": False, "error": "Missing SMM_PANEL_URL or SMM_API_KEY"}
        url = f"{self.base_url}/api/v2"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, data=self._form("balance"))
        try:
            j = r.json()
        except Exception:
            return {"ok": False, "error": f"bad response ({r.status_code})", "text": r.text[:400]}
        return {
            "ok": True,
            "balance": j.get("balance"),
            "currency": j.get("currency"),
            "raw": j,
        }

    async def get_order_status(self, order_id: str) -> dict:
        if not self.base_url or not self.key:
            return {"ok": False, "error": "Missing SMM_PANEL_URL or SMM_API_KEY"}
        url = f"{self.base_url}/api/v2"
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, data=self._form("status", order=order_id))
        try:
            j = r.json()
        except Exception:
            return {"ok": False, "error": f"bad response ({r.status_code})", "text": r.text[:400]}
        return {"ok": True, "raw": j}

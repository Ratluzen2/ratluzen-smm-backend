# app/smm_balance_router.py
import os
from fastapi import APIRouter, HTTPException
import httpx

router = APIRouter()

# متغيّرات البيئة التي ستضعها في هيروكو:
# SMM_API_URL  مثال: https://panel.example.com/api/v2
# SMM_API_KEY  مفتاح الـ API من المزوّد
# SMM_STYLE    اختياري: "standard" (POST مع action=balance) أو "get" (GET)

def _env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise HTTPException(status_code=500, detail=f"Missing env var: {name}")
    return v

@router.get("/balance")
async def get_balance():
    api_url = _env("SMM_API_URL").strip()
    api_key = _env("SMM_API_KEY").strip()
    style = os.getenv("SMM_STYLE", "standard").strip().lower()

    try:
        timeout = httpx.Timeout(10.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if style == "get":
                # بعض اللوحات تقبل GET
                r = await client.get(api_url, params={"key": api_key, "action": "balance"})
            else:
                # النمط القياسي لأغلب لوحات SMM: POST على /api/v2
                r = await client.post(api_url, data={"key": api_key, "action": "balance"})

        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Panel HTTP {r.status_code}: {r.text[:300]}")

        # إن كان JSON نُعيده كما هو؛ وإن كان نصًا نُعيده خامًا
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

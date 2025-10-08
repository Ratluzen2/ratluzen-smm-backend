from fastapi import APIRouter
from ..providers.smm_client import SMMClient

router = APIRouter(prefix="/api", tags=["provider"])

@router.get("/server/ping")
async def server_ping():
    # استدعاء خفيف للتأكد من عمل المزود (اختياري)
    try:
        _ = await SMMClient().balance()
        return {"ok": True, "data": {"upstream_ok": True}}
    except Exception:
        return {"ok": False, "error": "upstream error"}

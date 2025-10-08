from fastapi import APIRouter
import json, time, urllib.parse, urllib.request
from ..config import SMM_API_URL, SMM_API_KEY

router = APIRouter(prefix="/api", tags=["provider"])

# -------- helpers --------
def _post_form(url: str, payload: dict, timeout=15):
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "ignore")
        return json.loads(raw)

def _smm_balance_safe():
    if not SMM_API_KEY:
        return {"ok": False, "error": "no_api_key"}
    try:
        return {"ok": True, "data": _post_form(SMM_API_URL, {"key": SMM_API_KEY, "action": "balance"})}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# -------- server status (تستخدمه شاشة الحالة) --------
@router.get("/server/ping")
def server_ping():
    smm = _smm_balance_safe()
    return {"ok": True, "upstream_ok": bool(smm.get("ok")), "balance_sample": smm.get("data")}

# -------- services (تستخدمها شاشة الخدمات في التطبيق) --------
_SERVICES_CACHE = {"ts": 0.0, "data": []}
_TTL = 600  # 10 دقائق

def _fetch_services():
    if not SMM_API_KEY:
        return []
    try:
        res = _post_form(SMM_API_URL, {"key": SMM_API_KEY, "action": "services"}, timeout=30)
        # KD1S يعيد قائمة خدمات مباشرة — نرجعها كما هي
        if isinstance(res, list):
            return res
        # حالات نادرة: يعيد dict فيه 'services'
        return list(res.get("services", []))
    except Exception:
        return []

@router.get("/services")
def list_services():
    now = time.time()
    if now - _SERVICES_CACHE["ts"] > _TTL or not _SERVICES_CACHE["data"]:
        _SERVICES_CACHE["data"] = _fetch_services()
        _SERVICES_CACHE["ts"] = now
    # مهم: التطبيق يتوقع مصفوفة، لذا نرجّع [] عند الفشل بدل رسالة خطأ
    return _SERVICES_CACHE["data"]

# (اختياري) تفريغ الكاش يدويًا
@router.get("/services/refresh")
def refresh_services():
    _SERVICES_CACHE["data"] = _fetch_services()
    _SERVICES_CACHE["ts"] = time.time()
    return {"ok": True, "count": len(_SERVICES_CACHE["data"])}

from fastapi import APIRouter
import json, urllib.parse, urllib.request
from ..config import SMM_API_URL, SMM_API_KEY

router = APIRouter(prefix="/api", tags=["provider"])

def _smm_balance_safe():
    if not SMM_API_KEY:
        return {"ok": False, "error": "no_api_key"}
    try:
        data = urllib.parse.urlencode({"key": SMM_API_KEY, "action": "balance"}).encode()
        req = urllib.request.Request(SMM_API_URL, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            return {"ok": True, "data": json.loads(raw)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/server/ping")
def server_ping():
    # التطبيق يعتبر 2xx = متصل؛ نعطي always 200 ونشير لحالة المزوّد
    smm = _smm_balance_safe()
    return {"ok": True, "upstream_ok": bool(smm.get("ok")), "balance_sample": smm.get("data")}

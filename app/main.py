# app/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import json
import re
import httpx

app = FastAPI(title="Ratluzen SMM Backend")

# ------------------------------
# Healthcheck
# ------------------------------
@app.get("/health")
async def health():
    return {"ok": True}

# ------------------------------
# Upsert UID (الواجهة التي يستدعيها التطبيق)
# حالياً بدون قاعدة بيانات، مجرد تأكيد. لاحقاً يمكن ربط DB.
# ------------------------------
class UpsertBody(BaseModel):
    uid: str

@app.post("/api/users/upsert")
async def upsert_user(body: UpsertBody):
    # TODO: اربطها بـ DB إن رغبت لاحقاً
    return {"ok": True, "uid": body.uid}

# ------------------------------
# مساعد لقراءة متغيرات مزود الخدمات
# يجب ضبطها في Heroku:
#   SMM_API_URL  مثال: https://example.com/api/v2
#   SMM_API_KEY  مفتاح مزود الخدمات
# ------------------------------
def _get_smm_env():
    url = os.getenv("SMM_API_URL", "").strip()
    key = os.getenv("SMM_API_KEY", "").strip()
    if not url or not key:
        raise HTTPException(status_code=500, detail="SMM_API_URL أو SMM_API_KEY غير مضبوطة")
    return url, key

# ------------------------------
# فحص رصيد API (مسار يستدعيه التطبيق)
# يحاول التعامل مع JSON أو نص عادي من أغلب مزودي v2
# ------------------------------
@app.get("/api/smm/balance")
async def smm_balance():
    url, key = _get_smm_env()
    payload = {"key": key, "action": "balance"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # أغلب مزودي v2 يقبلون POST، وإن لزم بدّلها إلى GET
            r = await client.post(url, data=payload)
            r.raise_for_status()

        ct = r.headers.get("content-type", "")
        text = r.text

        # 1) JSON صريح
        if "application/json" in ct:
            data = r.json()
            bal = data.get("balance") or data.get("Balance")
            cur = data.get("currency") or data.get("Currency")
            if bal is not None:
                return {"ok": True, "balance": str(bal), "currency": (cur or "").upper()}

        # 2) JSON كنص
        try:
            data = json.loads(text)
            bal = data.get("balance") or data.get("Balance")
            cur = data.get("currency") or data.get("Currency")
            if bal is not None:
                return {"ok": True, "balance": str(bal), "currency": (cur or "").upper()}
        except Exception:
            pass

        # 3) نص عادي منسق "Balance: 12.34 USD" أو مشابه
        m = re.search(r'([\d.]+)\s*([A-Za-z]{3})?', text)
        if m:
            return {"ok": True, "balance": m.group(1), "currency": (m.group(2) or "").upper()}

        # إن لم نعرف الشكل نرجع النص الخام للمساعدة على التشخيص
        return {"ok": False, "raw": text}

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"SMM call failed: {e}")

# app/providers/smm_client.py
from __future__ import annotations

import os
import json
import re
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException


class SmmClient:
    """
    عميل بسيط للتعامل مع أغلب لوحات SMM الشائعة (api/v2).
    يتكفّل ببناء الطلب، التعامل مع الأخطاء، وتوحيد الرد.
    """

    def __init__(self) -> None:
        self.api_url: str = (
            os.getenv("SMM_API_URL")
            or os.getenv("PROVIDER_API_URL")
            or ""
        )
        self.api_key: str = (
            os.getenv("SMM_API_KEY")
            or os.getenv("PROVIDER_API_KEY")
            or ""
        )
        if not self.api_url or not self.api_key:
            raise HTTPException(
                status_code=500,
                detail="Provider API is not configured (missing SMM_API_URL/SMM_API_KEY).",
            )

        # بعض المزودين يتحسسون من الـ UA
        self.headers = {
            "User-Agent": "RatlwzanApp/1.0 (+https://herokuapp.com)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, */*;q=0.8",
        }

    async def _post(self, data: Dict[str, Any]) -> Dict[str, Any]:
        form = {"key": self.api_key}
        form.update(data)

        try:
            async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
                resp = await client.post(self.api_url, data=form, headers=self.headers)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Provider connection error: {e}")

        # حاول JSON أولاً
        parsed: Dict[str, Any]
        text = resp.text.strip()

        if "application/json" in resp.headers.get("content-type", ""):
            try:
                parsed = resp.json()
            except Exception:
                parsed = {}
        else:
            # أحيانًا يرجع المزود نصًا فقط… جرّب JSON ثم key:value
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = self._parse_key_value_text(text)

        if resp.status_code >= 400:
            # أعد خام الرد ليسهل التشخيص من الطرف الآخر
            raise HTTPException(status_code=resp.status_code, detail={"raw": parsed or text})

        # إن بقي فارغًا أعد الخام
        if not parsed:
            parsed = {"raw": text}

        return parsed

    @staticmethod
    def _parse_key_value_text(text: str) -> Dict[str, Any]:
        """
        يحاول تحويل نص مثل:
          balance: 12.34
          currency: USD
        أو سطر واحد: "balance:12.34;currency:USD"
        إلى dict.
        """
        out: Dict[str, Any] = {}
        # ادعم سطر واحد مفصول بفواصل أو فاصلة منقوطة
        if ";" in text or "," in text:
            parts = re.split(r"[;,]\s*", text)
        else:
            parts = text.splitlines()

        for p in parts:
            if ":" in p:
                k, v = p.split(":", 1)
                out[k.strip().lower()] = v.strip()
        return out

    async def get_balance(self) -> Dict[str, Any]:
        data = await self._post({"action": "balance"})
        # توحيد الحقول
        balance = (
            data.get("balance")
            or data.get("balance_amount")
            or data.get("funds")
            or data.get("raw")
        )
        currency = data.get("currency") or data.get("curr") or None
        return {"ok": True, "balance": balance, "currency": currency, "provider_raw": data}

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        data = await self._post({"action": "status", "order": str(order_id)})
        # أشهر الحقول المعروفة
        status = data.get("status") or data.get("state") or data.get("order_status")
        remains = data.get("remains") or data.get("remains_count") or data.get("left")
        charge = data.get("charge") or data.get("price")
        start_count = data.get("start_count") or data.get("start")

        return {
            "ok": True,
            "order_id": order_id,
            "status": status,
            "remains": remains,
            "charge": charge,
            "start_count": start_count,
            "provider_raw": data,
        }

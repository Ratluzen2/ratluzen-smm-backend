# --- Admin compatible aliases (fix 404 for app) ---
from fastapi import Depends, HTTPException
from fastapi import Body, Path, Query, Header
from typing import Optional
from datetime import datetime, timedelta
import asyncpg

ADMIN_HEADER = "x-admin-pass"

async def require_admin(x_admin_pass: Optional[str] = Header(None, convert_underscores=False)):
    # استبدل التحقق بما هو عندك
    if (x_admin_pass or "").strip() != (os.getenv("ADMIN_PASS") or "2000"):
        raise HTTPException(status_code=401, detail="unauthorized")
    return True

# alias: /api/admin/users/balances  -> يرجع قائمة الأرصدة + الإجمالي
@app.get("/api/admin/users/balances")
async def admin_users_balances(_: bool = Depends(require_admin)):
    async with app.state.pool.acquire() as conn:
        rows = await conn.fetch("SELECT uid, balance FROM users ORDER BY updated_at DESC NULLS LAST")
        total = sum([float(r["balance"] or 0) for r in rows])
        return {
            "list": [{"uid": r["uid"], "balance": float(r["balance"] or 0)} for r in rows],
            "total": total
        }

# alias: /api/admin/users/count  -> يرجع الإجمالي والنشط خلال ساعة
@app.get("/api/admin/users/count")
async def admin_users_count(_: bool = Depends(require_admin)):
    async with app.state.pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        active = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE last_active >= (NOW() AT TIME ZONE 'utc') - INTERVAL '1 hour'"
        )
        return {"total": int(total or 0), "active_last_hour": int(active or 0)}

# alias: /api/admin/users/{uid}/topup  -> نفس /api/admin/wallet/topup
@app.post("/api/admin/users/{uid}/topup")
async def admin_user_topup(
    uid: str = Path(...),
    amount: float = Body(..., embed=True),
    _: bool = Depends(require_admin)
):
    async with app.state.pool.acquire() as conn:
        async with conn.transaction():
            rec = await conn.fetchrow("SELECT balance FROM users WHERE uid=$1", uid)
            if not rec:
                await conn.execute("INSERT INTO users(uid, balance, last_active) VALUES ($1, 0, NOW())", uid)
                bal = 0.0
            else:
                bal = float(rec["balance"] or 0)
            new_bal = bal + float(amount)
            await conn.execute(
                "UPDATE users SET balance=$1, updated_at=NOW(), last_active=NOW() WHERE uid=$2",
                new_bal, uid
            )
            await conn.execute(
                "INSERT INTO wallet_logs(uid, action, amount, created_at) VALUES ($1,'topup',$2,NOW())",
                uid, float(amount)
            )
    return {"ok": True, "balance": new_bal}

# alias: /api/admin/users/{uid}/deduct  -> نفس /api/admin/wallet/deduct
@app.post("/api/admin/users/{uid}/deduct")
async def admin_user_deduct(
    uid: str = Path(...),
    amount: float = Body(..., embed=True),
    _: bool = Depends(require_admin)
):
    async with app.state.pool.acquire() as conn:
        async with conn.transaction():
            rec = await conn.fetchrow("SELECT balance FROM users WHERE uid=$1", uid)
            if not rec:
                raise HTTPException(status_code=404, detail="user not found")
            bal = float(rec["balance"] or 0)
            if bal < amount:
                raise HTTPException(status_code=400, detail="insufficient balance")
            new_bal = bal - float(amount)
            await conn.execute(
                "UPDATE users SET balance=$1, updated_at=NOW(), last_active=NOW() WHERE uid=$2",
                new_bal, uid
            )
            await conn.execute(
                "INSERT INTO wallet_logs(uid, action, amount, created_at) VALUES ($1,'deduct',$2,NOW())",
                uid, float(amount)
            )
    return {"ok": True, "balance": new_bal}

# alias: /api/admin/pending/cards  -> يعيد نفس نتيجة /api/admin/pending/topups
@app.get("/api/admin/pending/cards")
async def admin_pending_cards(_: bool = Depends(require_admin)):
    async with app.state.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, uid, card_number, status, created_at
            FROM topup_cards
            WHERE status='pending'
            ORDER BY created_at ASC
        """)
        # نرجع شكلًا متوافقًا مع الواجهة
        return [
            {
                "id": str(r["id"]),
                "title": f"كارت أسيا سيل ({r['uid']})",
                "quantity": 0,
                "price": 0.0,
                "payload": r["card_number"],
                "status": "Pending",
                "created_at": int(r["created_at"].timestamp() * 1000)
            } for r in rows
        ]

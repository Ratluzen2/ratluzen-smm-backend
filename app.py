import os, time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from psycopg_pool import ConnectionPool

app = FastAPI(title="SMM Mobile Backend")
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")
pool = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=5, max_idle=60, timeout=60,
                      kwargs={"sslmode":"require","connect_timeout":10})

def q(sql, params=(), fetch=None):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if fetch == "one": r = cur.fetchone(); conn.commit(); return r
            if fetch == "all": r = cur.fetchall(); conn.commit(); return r
            conn.commit(); return None

class LoginReq(BaseModel):
    user_id: int
    username: str | None = None

@app.get("/health")
def health(): return {"ok": True}

@app.post("/auth/login")
def login(body: LoginReq):
    q("""INSERT INTO users (user_id, full_name, username)
         VALUES (%s,%s,%s)
         ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username""",
      (body.user_id, body.username or "Unknown", body.username or "NoUsername"))
    return {"token": "dummy", "is_admin": False, "is_moderator": False}

@app.get("/services")
def services():  # نموذج مبسّط
    return [
        {"name":"متابعين تيكتوك 1k","price":3.5,"category":"smm"},
        {"name":"مشاهدات تيكتوك 10k","price":0.8,"category":"smm"}
    ]

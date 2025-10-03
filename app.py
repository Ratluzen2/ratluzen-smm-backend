import os, json, time
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from psycopg_pool import ConnectionPool
import requests

API_URL = os.getenv("API_URL", "https://kd1s.com/api/v2")
API_KEY = os.getenv("API_KEY", "25a9ceb07be0d8b2ba88e70dcbe92e06")
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")

pool = ConnectionPool(conninfo=DATABASE_URL, max_size=6, kwargs={"sslmode":"require"})

def kd1s_post(payload: dict) -> dict:
    data = {"key": API_KEY, **payload}
    r = requests.post(API_URL, data=data, timeout=60)
    r.raise_for_status()
    return r.json()

app = FastAPI(title="SMM Backend", version="1.0.0")

# ==== نماذج ====
class RegisterBody(BaseModel):
    device_id: str
    username: Optional[str] = None

class AddOrderBody(BaseModel):
    device_id: str
    service: int
    link: str
    quantity: int

# ==== DB helpers ====
def q(query: str, params: tuple = ()):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            try:
                return cur.fetchall()
            except:
                return []

def q1(query: str, params: tuple = ()):
    rows = q(query, params)
    return rows[0] if rows else None

# ==== bootstrap بسيط (يجعل الجداول إن لم توجد) ====
BOOTSTRAP_SQL = """
create extension if not exists pgcrypto;

create table if not exists app_users(
  id bigserial primary key,
  device_id text unique,
  telegram_id bigint,
  name text,
  is_admin boolean default false,
  balance numeric(14,4) default 0,
  currency text default 'USD',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists services_cache(
  service int primary key,
  name text,
  category text,
  rate numeric(14,4),
  min int,
  max int,
  type text,
  created_at timestamptz default now()
);

create table if not exists orders(
  id bigserial primary key,
  user_id bigint references app_users(id) on delete cascade,
  provider_order_id text,
  service_id int,
  link text,
  quantity int,
  status text,
  charge numeric(14,4),
  start_count int,
  remains int,
  raw_json jsonb,
  created_at timestamptz default now()
);

create table if not exists wallet_tx(
  id bigserial primary key,
  user_id bigint references app_users(id) on delete cascade,
  amount numeric(14,4) not null,  -- (+) إيداع / (-) خصم
  type text not null check (type in ('deposit','withdraw','charge','refund','bonus')),
  ref text,
  meta jsonb,
  created_at timestamptz default now()
);

create index if not exists idx_orders_user on orders(user_id);
create index if not exists idx_wallet_user on wallet_tx(user_id);

create or replace view leaderboard_month as
select user_id, sum(case when amount<0 then -amount else 0 end) as spent
from wallet_tx
where date_trunc('month', created_at)=date_trunc('month', now())
group by user_id
order by spent desc;
"""

@app.on_event("startup")
def boot():
    q(BOOTSTRAP_SQL)

# ==== Endpoints ====
@app.get("/health")
def health():
    return {"ok": True, "time": time.time()}

@app.post("/api/register")
def register(body: RegisterBody):
    row = q1("select id, balance, currency from app_users where device_id=%s", (body.device_id,))
    if row:
        q("update app_users set name=coalesce(%s,name), updated_at=now() where device_id=%s",
          (body.username, body.device_id))
    else:
        q("insert into app_users(device_id, name) values(%s,%s)", (body.device_id, body.username))
    row = q1("select id, device_id, balance, currency from app_users where device_id=%s", (body.device_id,))
    return {"id": row[0], "device_id": row[1], "balance": float(row[2]), "currency": row[3]}

@app.get("/api/user/{device_id}/balance")
def user_balance(device_id: str):
    row = q1("select balance, currency from app_users where device_id=%s", (device_id,))
    if not row:
        raise HTTPException(404, "user not found")
    return {"balance": float(row[0]), "currency": row[1]}

@app.post("/api/wallet/deposit")
def wallet_deposit(device_id: str, amount: float, note: Optional[str]=None):
    u = q1("select id from app_users where device_id=%s", (device_id,))
    if not u: raise HTTPException(404, "user not found")
    uid = u[0]
    q("insert into wallet_tx(user_id, amount, type, ref, meta) values(%s,%s,'deposit',%s,%s)",
      (uid, amount, note, json.dumps({})))
    q("update app_users set balance=balance+%s, updated_at=now() where id=%s", (amount, uid))
    return {"ok": True}

@app.get("/api/wallet/transactions")
def wallet_transactions(device_id: str, limit: int = 50):
    u = q1("select id from app_users where device_id=%s", (device_id,))
    if not u: raise HTTPException(404, "user not found")
    uid = u[0]
    rows = q("""select amount, type, ref, created_at
                from wallet_tx where user_id=%s
                order by id desc limit %s""", (uid, limit))
    out = []
    for r in rows:
        out.append({"amount": float(r[0]), "type": r[1], "ref": r[2], "created_at": r[3].isoformat()})
    return out

@app.get("/api/services")
def services(force: bool = False):
    # من الكاش
    if not force:
        cached = q("select service, name, category, rate, min, max, type from services_cache order by service limit 3000")
        if cached:
            return {"fromCache": True, "services": [
                {"service": r[0], "name": r[1], "category": r[2], "rate": float(r[3]) if r[3] is not None else None,
                 "min": r[4], "max": r[5], "type": r[6]} for r in cached
            ]}
    # من المزود
    data = kd1s_post({"action":"services"})
    # خزّن
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("delete from services_cache")
            for s in data:
                cur.execute("""insert into services_cache(service,name,category,rate,min,max,type)
                               values(%s,%s,%s,%s,%s,%s,%s)
                               on conflict (service) do update set
                               name=excluded.name, category=excluded.category, rate=excluded.rate,
                               min=excluded.min, max=excluded.max, type=excluded.type, created_at=now()""",
                            (s.get("service"), s.get("name"), s.get("category"), s.get("rate"),
                             s.get("min"), s.get("max"), s.get("type")))
    return {"fromCache": False, "services": data}

@app.post("/api/order/add")
def order_add(body: AddOrderBody):
    u = q1("select id, balance from app_users where device_id=%s", (body.device_id,))
    if not u: raise HTTPException(404, "user not found")
    uid, balance = u[0], float(u[1])

    provider = kd1s_post({"action":"add", "service":body.service, "link":body.link, "quantity":body.quantity})
    provider_order_id = str(provider.get("order") or provider.get("order_id") or "")
    charge = float(provider.get("charge") or 0)

    # خصم محلي (اختياري: علّق هذا لو لا تريد الخصم)
    if charge > 0 and balance >= charge:
        q("insert into wallet_tx(user_id, amount, type, ref, meta) values(%s,%s,'charge',%s,%s)",
          (uid, -charge, provider_order_id, json.dumps({"service":body.service,"link":body.link,"qty":body.quantity})))
        q("update app_users set balance=balance-%s where id=%s", (charge, uid))

    q("""insert into orders(user_id, provider_order_id, service_id, link, quantity, charge, status, raw_json)
         values(%s,%s,%s,%s,%s,%s,%s,%s)""",
      (uid, provider_order_id, body.service, body.link, body.quantity, charge, provider.get("status") or "pending", json.dumps(provider)))
    return {"ok": True, "order": provider_order_id, "charge": charge}

@app.get("/api/order/{provider_order_id}/status")
def order_status(provider_order_id: str):
    data = kd1s_post({"action":"status", "order":provider_order_id})
    q("""update orders set status=%s, remains=%s, raw_json=%s where provider_order_id=%s""",
      (data.get("status"), data.get("remains"), json.dumps(data), provider_order_id))
    return data

@app.get("/api/orders/{device_id}")
def orders_list(device_id: str, limit: int = 50):
    u = q1("select id from app_users where device_id=%s", (device_id,))
    if not u: raise HTTPException(404, "user not found")
    uid = u[0]
    rows = q("""select provider_order_id, service_id, link, quantity, status, charge, remains, created_at
                from orders where user_id=%s order by id desc limit %s""", (uid, limit))
    out = []
    for r in rows:
        out.append({
            "order": r[0], "service": r[1], "link": r[2], "quantity": r[3],
            "status": r[4], "charge": float(r[5]) if r[5] is not None else None,
            "remains": r[6], "created_at": r[7].isoformat()
        })
    return out

@app.get("/api/leaderboard")
def leaderboard(limit: int = 20):
    rows = q("""select a.id, a.name, coalesce(l.spent,0) as spent
                from app_users a
                left join leaderboard_month l on l.user_id=a.id
                order by spent desc
                limit %s""", (limit,))
    return [{"user_id": r[0], "name": r[1], "spent": float(r[2])} for r in rows]

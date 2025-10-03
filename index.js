// index.js
const express = require("express");
const cors = require("cors");
const axios = require("axios");
const db = require("./db");

const PORT = process.env.PORT || 3000;

// مفاتيح المزود kd1s (يُستَخدم ما في Heroku وإن لم يوجد تُستَخدم القيم الافتراضية)
const API_URL = process.env.API_URL || "https://kd1s.com/api/v2";
const API_KEY = process.env.API_KEY || "25a9ceb07be0d8b2ba88e70dcbe92e06";

const app = express();
app.use(cors());
app.use(express.json());

// إنشاء الجداول تلقائيًا عند الإقلاع
const bootstrapSQL = `
create extension if not exists pgcrypto;

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  device_id text unique,
  telegram_id bigint unique,
  username text,
  is_admin boolean default false,
  balance numeric(14,6) default 0,
  currency text default 'USD',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists services_cache (
  service_id bigint primary key,
  name text,
  category text,
  rate numeric(14,6),
  min_qty int,
  max_qty int,
  dripfeed boolean,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists orders (
  id bigserial primary key,
  user_id uuid references users(id) on delete set null,
  provider_order_id bigint,
  service_id bigint,
  link text,
  quantity int,
  charge numeric(14,6),
  status text,
  remains int,
  raw_json jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists wallet_transactions (
  id bigserial primary key,
  user_id uuid references users(id) on delete cascade,
  kind text,
  amount numeric(14,6),
  note text,
  created_at timestamptz default now()
);

create table if not exists leaderboard (
  id bigserial primary key,
  user_id uuid references users(id) on delete cascade,
  total_spent numeric(14,6) default 0,
  updated_at timestamptz default now()
);

create index if not exists idx_orders_user_id on orders(user_id);
create index if not exists idx_wallet_user_id on wallet_transactions(user_id);
`;

async function kd1sPost(formObj) {
  const params = new URLSearchParams({ key: API_KEY, ...formObj });
  const { data } = await axios.post(API_URL, params);
  return data;
}

app.get("/api/health", (_req, res) => res.json({ ok: true }));

// تسجيل المستخدم بالجهاز
app.post("/api/register", async (req, res) => {
  try {
    const { device_id, username } = req.body;
    if (!device_id) return res.status(400).json({ error: "device_id required" });
    const q = `
      insert into users(device_id, username)
      values ($1, $2)
      on conflict (device_id) do update set username=excluded.username, updated_at=now()
      returning *;
    `;
    const { rows } = await db.query(q, [device_id, username || null]);
    res.json(rows[0]);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// رصيد المستخدم المحلي
app.get("/api/user/:deviceId/balance", async (req, res) => {
  try {
    const { deviceId } = req.params;
    const { rows } = await db.query("select balance, currency from users where device_id=$1", [deviceId]);
    if (!rows[0]) return res.status(404).json({ error: "user not found" });
    res.json(rows[0]);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// رصيد المزود kd1s (للمالك/للاختبار)
app.get("/api/provider/balance", async (_req, res) => {
  try {
    const data = await kd1sPost({ action: "balance" });
    res.json(data); // {balance, currency}
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// تحديث/جلب الخدمات + تخزينها ككاش
app.get("/api/services", async (req, res) => {
  try {
    const force = req.query.force === "true";
    if (!force) {
      const { rows } = await db.query("select * from services_cache order by service_id limit 3000");
      if (rows.length) return res.json({ fromCache: true, services: rows });
    }
    const data = await kd1sPost({ action: "services" }); // قائمة من العناصر
    // خزن
    const client = await db.pool.connect();
    try {
      await client.query("begin");
      await client.query("delete from services_cache");
      for (const s of data) {
        await client.query(
          `insert into services_cache(service_id, name, category, rate, min_qty, max_qty, dripfeed)
           values ($1,$2,$3,$4,$5,$6,$7)
           on conflict (service_id) do update set
           name=excluded.name, category=excluded.category, rate=excluded.rate,
           min_qty=excluded.min_qty, max_qty=excluded.max_qty, dripfeed=excluded.dripfeed, updated_at=now()`,
          [s.service, s.name, s.category, s.rate, s.min, s.max, !!s.dripfeed]
        );
      }
      await client.query("commit");
    } catch (e) {
      await client.query("rollback"); throw e;
    } finally { client.release(); }
    res.json({ fromCache: false, services: data });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// إنشاء طلب
app.post("/api/order/add", async (req, res) => {
  try {
    const { device_id, service, link, quantity } = req.body;
    if (!device_id || !service || !link || !quantity) return res.status(400).json({ error: "missing fields" });

    const { rows: urows } = await db.query("select id from users where device_id=$1", [device_id]);
    if (!urows[0]) return res.status(404).json({ error: "user not found" });
    const userId = urows[0].id;

    const data = await kd1sPost({ action: "add", service, link, quantity }); // {order:..., charge:...} غالبًا
    const providerOrderId = data.order || null;

    const ins = `
      insert into orders(user_id, provider_order_id, service_id, link, quantity, charge, status, raw_json)
      values ($1,$2,$3,$4,$5,$6,$7,$8)
      returning *;
    `;
    const { rows } = await db.query(ins, [
      userId, providerOrderId, service, link, quantity,
      data.charge ? Number(data.charge) : null,
      "pending", data
    ]);
    res.json({ ok: true, order: rows[0], provider: data });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// حالة طلب من المزود
app.get("/api/order/:providerOrderId/status", async (req, res) => {
  try {
    const order = req.params.providerOrderId;
    const data = await kd1sPost({ action: "status", order });
    // تحديث محليًا إن وُجد
    await db.query(
      "update orders set status=$1, remains=$2, updated_at=now(), raw_json=$3 where provider_order_id=$4",
      [data.status || null, data.remains || null, data, order]
    );
    res.json(data);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// قائمة طلبات مستخدم
app.get("/api/orders/:deviceId", async (req, res) => {
  try {
    const { deviceId } = req.params;
    const q = `
      select o.* from orders o
      join users u on u.id=o.user_id
      where u.device_id=$1
      order by o.id desc
      limit 100;
    `;
    const { rows } = await db.query(q, [deviceId]);
    res.json(rows);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

(async function start() {
  try {
    await db.query(bootstrapSQL);
    app.listen(PORT, () => console.log("SMM backend running on", PORT));
  } catch (e) {
    console.error("Boot error:", e);
    process.exit(1);
  }
})();

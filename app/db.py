import os, re
from psycopg2.pool import SimpleConnectionPool
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")

# تحويل postgres:// إلى postgresql:// (بعض المنصات ترسله بالشكل القديم)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# أضف sslmode=require إن لم يوجد (Neon/Heroku)
if "sslmode=" not in DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{sep}sslmode=require"

# إنشاء Pool بحجم معقول
pool = SimpleConnectionPool(minconn=1, maxconn=8, dsn=DATABASE_URL)

def get_conn():
    return pool.getconn()

def put_conn(conn):
    if conn:
        pool.putconn(conn)

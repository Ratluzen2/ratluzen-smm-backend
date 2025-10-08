import os
from psycopg2.pool import SimpleConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")

# تحويل postgres:// إلى postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# إضافة sslmode=require إن لم يوجد
if "sslmode=" not in DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{sep}sslmode=require"

pool = SimpleConnectionPool(minconn=1, maxconn=8, dsn=DATABASE_URL)

def get_conn():
    return pool.getconn()

def put_conn(conn):
    if conn:
        pool.putconn(conn)

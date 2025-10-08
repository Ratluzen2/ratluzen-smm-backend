import os
from psycopg2.pool import SimpleConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required")

# تطبيع البروتوكول
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

# تأكيد SSL
if DATABASE_URL.startswith("postgresql://") and "sslmode=" not in DATABASE_URL:
    DATABASE_URL += ("&" if "?" in DATABASE_URL else "?") + "sslmode=require"

pool = SimpleConnectionPool(minconn=1, maxconn=8, dsn=DATABASE_URL)

def get_conn():
    return pool.getconn()

def put_conn(conn):
    if conn:
        pool.putconn(conn)

import os
import ssl
import psycopg2
from psycopg2.pool import SimpleConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL")  # مثال: postgres://user:pass@host/db
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is required")

# Neon يحتاج SSL
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

_pool: SimpleConnectionPool | None = None

def _ensure_pool():
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=DATABASE_URL,
            sslmode="require",
        )

def get_conn():
    _ensure_pool()
    assert _pool is not None
    return _pool.getconn()

def put_conn(conn):
    if _pool and conn:
        _pool.putconn(conn)

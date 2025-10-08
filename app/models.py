from .db import get_conn, put_conn

DDL = [
    """
    CREATE TABLE IF NOT EXISTS public.users (
      id SERIAL PRIMARY KEY,
      uid TEXT UNIQUE NOT NULL,
      balance NUMERIC DEFAULT 0,
      created_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.orders (
      id SERIAL PRIMARY KEY,
      user_id INT REFERENCES public.users(id) ON DELETE CASCADE,
      title TEXT NOT NULL,
      service_id INT,
      link TEXT,
      quantity INT DEFAULT 0,
      price NUMERIC DEFAULT 0,
      status TEXT DEFAULT 'Pending',
      created_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.wallet_txns (
      id SERIAL PRIMARY KEY,
      user_id INT REFERENCES public.users(id) ON DELETE CASCADE,
      amount NUMERIC NOT NULL,
      reason TEXT,
      meta JSONB DEFAULT '{}'::jsonb,
      created_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.asiacell_cards (
      id SERIAL PRIMARY KEY,
      user_id INT REFERENCES public.users(id) ON DELETE CASCADE,
      card_number TEXT NOT NULL,
      status TEXT DEFAULT 'Pending',
      created_at TIMESTAMPTZ DEFAULT now()
    )
    """
]

def ensure_schema():
    conn = get_conn()
    try:
        with conn, conn.cursor() as cur:
            for sql in DDL:
                cur.execute(sql)
    finally:
        put_conn(conn)

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

raw_url = os.environ["DATABASE_URL"]
# هيروكو/نيون قد يقدمان postgres://؛ SQLAlchemy يتطلب postgresql://
if raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql://", 1)
# إجبار SSL
if "sslmode=" not in raw_url:
    raw_url += ("&sslmode=require" if "?" in raw_url else "?sslmode=require")

engine = create_engine(raw_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

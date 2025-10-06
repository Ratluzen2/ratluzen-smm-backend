# app/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

raw_url = os.environ["DATABASE_URL"]
if raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql://", 1)
if "sslmode=" not in raw_url:
    raw_url += ("&sslmode=require" if "?" in raw_url else "?sslmode=require")

engine = create_engine(raw_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# Heroku's DATABASE_URL may start with 'postgres://' which SQLAlchemy dislikes; fix to 'postgresql://'
db_url = settings.DATABASE_URL.replace("postgres://", "postgresql://")

engine = create_engine(db_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

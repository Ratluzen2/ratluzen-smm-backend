from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, BigInteger, UniqueConstraint

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), default="user")
    wallet = relationship("Wallet", uselist=False, back_populates="user")

class Wallet(Base):
    __tablename__ = "wallets"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    balance = Column(Float, default=0.0)
    user = relationship("User", back_populates="wallet")

class Moderator(Base):
    __tablename__ = "moderators"
    user_id = Column(Integer, primary_key=True)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    category = Column(String(50))
    service_name = Column(String(200))
    qty = Column(Integer, default=0)
    price = Column(Float, default=0.0)
    status = Column(String(30), default="pending")
    link = Column(Text, default="")
    ts = Column(BigInteger)

class PriceOverride(Base):
    __tablename__ = "price_overrides"
    id = Column(Integer, primary_key=True)
    service = Column(String(200), unique=True, index=True)
    price = Column(Float, default=0.0)

class QtyOverride(Base):
    __tablename__ = "qty_overrides"
    id = Column(Integer, primary_key=True)
    service = Column(String(200), unique=True, index=True)
    qty = Column(Integer, default=1000)

class CardSubmission(Base):
    __tablename__ = "card_submissions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    digits = Column(String(80), index=True)
    ts = Column(BigInteger, index=True)
    __table_args__ = (UniqueConstraint('user_id','digits', name='uq_user_digits'),)

# app/models.py
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, func, MetaData
)
from sqlalchemy.orm import declarative_base, relationship

# <- مهم: نجعل كل الجداول داخل schema "smm"
metadata = MetaData(schema="smm")
Base = declarative_base(metadata=metadata)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")

class Wallet(Base):
    __tablename__ = "wallets"
    user_id = Column(Integer, ForeignKey("smm.users.id", ondelete="CASCADE"), primary_key=True)
    balance = Column(Float, default=0.0)
    user = relationship("User", back_populates="wallet")

class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    price = Column(Float, nullable=False)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("smm.users.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(50), nullable=False)
    service_name = Column(String(120), nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    link = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="orders")

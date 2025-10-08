from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Float, Text, Boolean
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"
    uid = Column(String, primary_key=True, index=True)
    balance = Column(Float, default=0.0)
    is_banned = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True, index=True)  # uuid4
    uid = Column(String, ForeignKey("users.uid"), index=True, nullable=False)
    title = Column(String, nullable=False)        # اسم الخدمة/العنصر للعرض
    quantity = Column(Integer, default=0)
    price = Column(Float, default=0.0)
    payload = Column(Text, default="")            # رابط/ID إضافي
    status = Column(String, default="Pending")    # Pending/Processing/Done/Rejected/Refunded
    kind = Column(String, default="manual")       # provider/manual/itunes/pubg/ludo
    panel_order_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CardSubmission(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    uid = Column(String, index=True, nullable=False)
    card_number = Column(String, nullable=False)
    status = Column(String, default="Pending")    # Pending/Accepted/Rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ItunesOrder(Base):
    __tablename__ = "itunes_orders"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    uid = Column(String, index=True, nullable=False)
    amount = Column(Integer, default=0)
    gift_code = Column(String, nullable=True)
    status = Column(String, default="Pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PubgOrder(Base):
    __tablename__ = "pubg_orders"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    uid = Column(String, index=True, nullable=False)
    pkg = Column(Integer, default=0)
    pubg_id = Column(String, default="")
    status = Column(String, default="Pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class LudoOrder(Base):
    __tablename__ = "ludo_orders"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    uid = Column(String, index=True, nullable=False)
    kind = Column(String, default="")   # الماسات/الذهب
    pack = Column(Integer, default=0)
    ludo_id = Column(String, default="")
    status = Column(String, default="Pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

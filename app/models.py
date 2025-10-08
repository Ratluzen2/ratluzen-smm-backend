from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Float, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    uid = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    orders = relationship("Order", back_populates="user")

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True, index=True)  # uuid4
    uid = Column(String, ForeignKey("users.uid"), index=True, nullable=False)
    panel_order_id = Column(Integer, index=True, nullable=True)
    service = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)
    link = Column(Text, nullable=False)
    status = Column(String, nullable=True)
    charge = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="orders")

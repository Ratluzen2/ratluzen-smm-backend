from sqlalchemy import Column, Integer, String, Text, Numeric, Boolean, ForeignKey, BigInteger, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base

# حالات الطلب
ORDER_STATUS = ("PENDING", "REVIEW", "DONE", "REJECTED", "REFUNDED")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    uid = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    wallet = relationship("Wallet", uselist=False, back_populates="user")

class Wallet(Base):
    __tablename__ = "wallets"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    balance = Column(Numeric(12, 2), default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="wallet")

class WalletLedger(Base):
    __tablename__ = "wallet_ledger"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    delta = Column(Numeric(12, 2), nullable=False)
    reason = Column(Text)
    ref = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True)  # ord_xxx
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    type = Column(String, nullable=False)  # provider | manual
    service_id = Column(BigInteger)
    title = Column(Text, nullable=False)
    quantity = Column(Integer)
    price = Column(Numeric(12, 2), nullable=False)
    payload = Column(JSONB)
    status = Column(String, nullable=False)  # ضمن ORDER_STATUS
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AsiacellCard(Base):
    __tablename__ = "asiacell_cards"
    id = Column(String, primary_key=True)  # card_xxx
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    card_number = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="REVIEW")  # REVIEW | APPROVED | REJECTED
    amount_usd = Column(Numeric(12, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    is_for_owner = Column(Boolean, default=False)
    delivered = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class DeviceToken(Base):
    __tablename__ = "device_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    token = Column(Text, unique=True, nullable=False)
    is_owner = Column(Boolean, default=False)  # لو جهاز المالك
    created_at = Column(DateTime(timezone=True), server_default=func.now())

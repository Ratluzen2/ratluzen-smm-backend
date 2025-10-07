from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy import String, Text, Integer, Numeric, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
import uuid
from datetime import datetime, timezone

Base = declarative_base()

def now_utc():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    uid: Mapped[str] = mapped_column(String(32), primary_key=True)
    balance: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=now_utc)
    last_seen: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=now_utc)

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="user")

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uid: Mapped[str] = mapped_column(String(32), ForeignKey("users.uid", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(24))  # provider/manual/card/itunes/pubg/ludo/phone
    title: Mapped[str] = mapped_column(String(255))
    service_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    service_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)  # card number, gift_code, etc
    status: Mapped[str] = mapped_column(String(16), default="Pending")  # Pending/Processing/Done/Rejected/Refunded
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=now_utc)

    user: Mapped[User] = relationship("User", back_populates="orders")

Index("ix_orders_status_type", Order.status, Order.type)

from sqlalchemy import String, Integer, Float, Boolean, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"
    uid: Mapped[str] = mapped_column(String(32), primary_key=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)  # احتياطي
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

    orders: Mapped[list["Order"]] = relationship(back_populates="user", cascade="all, delete")
    notices: Mapped[list["Notice"]] = relationship(back_populates="user", cascade="all, delete")

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(32), ForeignKey("users.uid"))
    service_key: Mapped[str] = mapped_column(String(100))
    service_id: Mapped[int] = mapped_column(Integer)
    link: Mapped[str] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, processing, completed, failed, rejected
    provider_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="orders")

class TopupCard(Base):
    __tablename__ = "topup_cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(32), ForeignKey("users.uid"))
    provider: Mapped[str] = mapped_column(String(32))  # "asiacell"
    card_number: Mapped[str] = mapped_column(String(32))  # (يمكن لاحقاً تشفيرها)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, accepted, rejected
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()

class Notice(Base):
    __tablename__ = "notices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.uid"), nullable=True)  # None للمالك
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship(back_populates="notices")

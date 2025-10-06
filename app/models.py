# app/models.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, func, Text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# قاعدة الموديلات وفق SQLAlchemy 2.0
class Base(DeclarativeBase):
    pass


# ---- Users ----
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)  # user/admin
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---- Notifications ----
class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---- Tokens (FCM) ----
class Token(Base):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---- Service Orders (provider) ----
class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    service_key: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    service_code: Mapped[int] = mapped_column(Integer, nullable=False)
    link: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_per_k: Mapped[float] = mapped_column(Float, nullable=False)  # سعر لكل 1000
    price: Mapped[float] = mapped_column(Float, nullable=False)             # السعر النهائي
    status: Mapped[str] = mapped_column(
        String(16), index=True, default="pending", nullable=False
    )  # pending/processing/done/rejected
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---- Wallet Cards (Asiacell) ----
class WalletCard(Base):
    __tablename__ = "wallet_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    card_number: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False
    )  # pending/accepted/rejected
    amount_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---- iTunes Orders ----
class ItunesOrder(Base):
    __tablename__ = "itunes_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    gift_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---- Phone Topups ----
class PhoneTopup(Base):
    __tablename__ = "phone_topups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    operator: Mapped[str] = mapped_column(String(16), nullable=False)  # atheir/asiacell/korek
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---- PUBG Orders ----
class PubgOrder(Base):
    __tablename__ = "pubg_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    pkg: Mapped[int] = mapped_column(Integer, nullable=False)  # 60,120,325,660,1800,3850,8100
    pubg_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---- Ludo Orders ----
class LudoOrder(Base):
    __tablename__ = "ludo_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # diamonds/gold
    pack: Mapped[int] = mapped_column(Integer, nullable=False)
    ludo_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

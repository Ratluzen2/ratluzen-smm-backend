# app/models.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    """Base declarative class for SQLAlchemy 2.x"""
    pass


# -------------------------
# Users
# -------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# -------------------------
# Service orders (linked to provider)
# -------------------------
class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # صاحب الطلب داخل التطبيق
    uid: Mapped[str] = mapped_column(String(64), index=True)

    # تعريف الخدمة
    service_key: Mapped[str] = mapped_column(String(128))      # مفتاح/ID الخدمة عند المزوّد
    service_name: Mapped[str] = mapped_column(String(200))     # اسم وصفي يظهر للمالك

    link: Mapped[str] = mapped_column(Text)                     # رابط الحساب/المنشور
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# -------------------------
# Wallet cards (Asiacell)
# -------------------------
class WalletCard(Base):
    __tablename__ = "wallet_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    card_number: Mapped[str] = mapped_column(String(32))        # 14 أو 16 رقم
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    amount_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# -------------------------
# iTunes orders (manual codes)
# -------------------------
class ItunesOrder(Base):
    __tablename__ = "itunes_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    gift_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# -------------------------
# Phone topups (manual)
# -------------------------
class PhoneTopup(Base):
    __tablename__ = "phone_topups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# -------------------------
# PUBG UC orders (manual)
# -------------------------
class PubgOrder(Base):
    __tablename__ = "pubg_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    pkg: Mapped[int] = mapped_column(Integer)                   # حجم الحزمة UC
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# -------------------------
# Ludo orders (manual)
# -------------------------
class LudoOrder(Base):
    __tablename__ = "ludo_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))               # "ماس" أو "ذهب" مثلًا
    pack: Mapped[str] = mapped_column(String(64))               # وصف الحزمة
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# -------------------------
# In-app notifications
# -------------------------
class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# -------------------------
# FCM tokens
# -------------------------
class Token(Base):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(Text, unique=True)
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

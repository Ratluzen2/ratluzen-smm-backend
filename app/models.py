# app/models.py
from __future__ import annotations

from typing import Optional
from datetime import datetime

from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, BigInteger
)
from sqlalchemy.sql import func

Base = declarative_base()


# =========================
# Users
# =========================
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(16), default="user")  # user/admin
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =========================
# Notifications (in-app + owner)
# =========================
class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    # لتوجيه إشعار لمستخدم معين (إن لزم)
    uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =========================
# FCM Tokens
# =========================
class Token(Base):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    token: Mapped[str] = mapped_column(Text, unique=True)
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =========================
# Provider Service Orders (الخدمات المربوطة بالـ API)
# =========================
class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)

    # بعض التطبيقات ترسل service_id رقمي، وبعض الراوترات تستخدم service_key/ service_code النصّي
    service_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    service_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    service_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    service_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    link: Mapped[str] = mapped_column(Text)                   # رابط/معرّف الخدمة
    quantity: Mapped[int] = mapped_column(Integer)            # الكمية
    unit_price_per_k: Mapped[float] = mapped_column(Float)    # سعر لكل 1000
    price: Mapped[float] = mapped_column(Float)               # السعر النهائي

    # pending/processing/done/rejected (أو أي قيم تُستخدم في الراوتر)
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")

    # رقم الطلب عند المزوّد الخارجي (إن وجد)
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# =========================
# Wallet Cards (Asiacell) — الكارتات المرسلة من المستخدم
# =========================
class WalletCard(Base):
    __tablename__ = "wallet_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    card_number: Mapped[str] = mapped_column(String(32))          # 14/16 رقم
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/accepted/rejected
    amount_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # عند القبول
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =========================
# iTunes Orders (تنفيذ يدوي من المالك)
# =========================
class ItunesOrder(Base):
    __tablename__ = "itunes_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[int] = mapped_column(Integer)  # 2/3/4/5/10/15/20/25/30/40/50/100
    status: Mapped[str] = mapped_column(String(16), default="pending")
    gift_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =========================
# Phone Topups (كروت/أكواد الهاتف يرسلها المالك للمستخدم)
# =========================
class PhoneTopup(Base):
    __tablename__ = "phone_topups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    operator: Mapped[str] = mapped_column(String(16))  # atheir/asiacell/korek
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # رقم الكارت عند التسليم
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =========================
# PUBG UC Orders
# =========================
class PubgOrder(Base):
    __tablename__ = "pubg_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    pkg: Mapped[int] = mapped_column(Integer)  # 60,120,325,660,1800,3850,8100
    pubg_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =========================
# Ludo Orders
# =========================
class LudoOrder(Base):
    __tablename__ = "ludo_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # diamonds/gold
    pack: Mapped[int] = mapped_column(Integer)     # 810/2280/... أو 66680/...
    ludo_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =========================
# (اختياري) __all__ لتصدير الأسماء بوضوح
# =========================
__all__ = [
    "Base",
    "User",
    "Notice",
    "Token",
    "ServiceOrder",
    "WalletCard",
    "ItunesOrder",
    "PhoneTopup",
    "PubgOrder",
    "LudoOrder",
]

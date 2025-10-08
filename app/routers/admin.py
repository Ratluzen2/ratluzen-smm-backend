# app/models.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, func, Index
)
from sqlalchemy.orm import declarative_base, Mapped, mapped_column

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

    __table_args__ = (
        Index("ix_users_uid", "uid"),
    )

# =========================
# Notifications (in-app + push log)
# =========================
class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    # إذا كانت خاصة بالمالك فقط
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    # إذا كانت موجهة لمستخدم محدد
    uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_notices_uid", "uid"),
    )

# =========================
# FCM Tokens
# =========================
class Token(Base):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    token: Mapped[str] = mapped_column(Text, unique=True)
    # true = للمالك (لوحة المالك) / false = للمستخدمين
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_tokens_uid", "uid"),
        Index("ix_tokens_for_owner", "for_owner"),
    )

# =========================
# Service Orders (Connected to external SMM provider)
# =========================
class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)

    # احتفظنا بالحقلين للتوافق مع الإصدارات المختلفة من الراوتر:
    # service_key: اسم أو مفتاح الخدمة (نصي)
    service_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    # service_code: رقم الخدمة للمزوّد (رقم)
    service_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    link: Mapped[str] = mapped_column(Text)          # رابط الحساب/المنشور
    quantity: Mapped[int] = mapped_column(Integer)   # الكمية المطلوبة

    # السعر لكل 1000 (للحسبة والعرض)
    unit_price_per_k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # السعر النهائي للطلب (يجب تخزينه وقت الإنشاء)
    price: Mapped[float] = mapped_column(Float)

    # pending / processing / done / rejected
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")

    # رقم الطلب عند المزوّد بعد التنفيذ
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_service_orders_uid", "uid"),
        Index("ix_service_orders_status", "status"),
        Index("ix_service_orders_service_key", "service_key"),
        Index("ix_service_orders_service_code", "service_code"),
    )

# =========================
# Wallet Cards (Asiacell cards submitted by users)
# =========================
class WalletCard(Base):
    __tablename__ = "wallet_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    card_number: Mapped[str] = mapped_column(String(32))  # 14 أو 16 رقم
    # pending / accepted / rejected
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # يتم وضع قيمة الشحن بالدولار عند القبول
    amount_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_wallet_cards_uid", "uid"),
        Index("ix_wallet_cards_status", "status"),
    )

# =========================
# iTunes Orders (manual delivery by owner)
# =========================
class ItunesOrder(Base):
    __tablename__ = "itunes_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    # القيمة المطلوبة (2 / 3 / 4 / ... / 100)
    amount: Mapped[int] = mapped_column(Integer)
    # pending / delivered / rejected
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    gift_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_itunes_orders_uid", "uid"),
        Index("ix_itunes_orders_status", "status"),
    )

# =========================
# Phone Topups (Atheer / Asiacell / Korek)
# =========================
class PhoneTopup(Base):
    __tablename__ = "phone_topups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    operator: Mapped[str] = mapped_column(String(16))  # atheir / asiacell / korek
    amount: Mapped[int] = mapped_column(Integer)
    # pending / delivered / rejected
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # كود الكارت المرسل للمستخدم بعد التنفيذ اليدوي
    code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_phone_topups_uid", "uid"),
        Index("ix_phone_topups_status", "status"),
        Index("ix_phone_topups_operator", "operator"),
    )

# =========================
# PUBG Orders (manual delivery by owner)
# =========================
class PubgOrder(Base):
    __tablename__ = "pubg_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    # الحزمة المطلوبة 60 / 120 / 325 / 660 / 1800 / 3850 / 8100
    pkg: Mapped[int] = mapped_column(Integer)
    pubg_id: Mapped[str] = mapped_column(String(64))
    # pending / delivered / rejected
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_pubg_orders_uid", "uid"),
        Index("ix_pubg_orders_status", "status"),
    )

# =========================
# Ludo Orders (diamonds / gold) — manual delivery
# =========================
class LudoOrder(Base):
    __tablename__ = "ludo_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    # diamonds / gold
    kind: Mapped[str] = mapped_column(String(16))
    # قيمة الحزمة (810 / 2280 / 5080 / 12750) للماس أو (66680 ... إلخ) للذهب
    pack: Mapped[int] = mapped_column(Integer)
    ludo_id: Mapped[str] = mapped_column(String(64))
    # pending / delivered / rejected
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_ludo_orders_uid", "uid"),
        Index("ix_ludo_orders_status", "status"),
        Index("ix_ludo_orders_kind", "kind"),
    )

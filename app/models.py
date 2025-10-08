# app/models.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, ForeignKey, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, declarative_base

Base = declarative_base()


# ─────────────────────────────
# Users
# ─────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<User uid={self.uid} balance={self.balance} banned={self.is_banned}>"


# ─────────────────────────────
# In-App Notices
# ─────────────────────────────
class Notice(Base):
    __tablename__ = "notices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # إذا كانت للمستخدم: نحفظ uid. إذا كانت للمالك: يكون for_owner = true و uid = NULL
    for_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ─────────────────────────────
# FCM / Push Tokens
# ─────────────────────────────
class Token(Base):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    for_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ─────────────────────────────
# Provider Service Orders (الخدمات المرتبطة بالمزوّد)
# ─────────────────────────────
class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # اسم الخدمة الظاهر داخل التطبيق
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # مفتاح واجهة المستخدم (مثل: "متابعين تيكتوك")
    service_key: Mapped[str] = mapped_column(String(200), nullable=False)

    # كود الخدمة لدى المزوّد
    service_code: Mapped[int] = mapped_column(Integer, nullable=False)

    link: Mapped[str] = mapped_column(String(1000), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_per_k: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")

    # pending / processing / done / rejected / refunded
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")

    # حقل عام لتخزين أي بيانات إضافية (اختياري)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ─────────────────────────────
# Manual Orders (مثل ايتونز / ببجي / لودو … بطلب يدوي)
# ─────────────────────────────
class ManualOrder(Base):
    __tablename__ = "manual_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # عنوان قصير (مثال: "شراء رصيد ايتونز" أو "شحن شدات ببجي")
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # تفاصيل الطلب (قد تكون JSON كنص)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ─────────────────────────────
# Asiacell Topup Cards (الكارتات المرسلة من المستخدم)
# ─────────────────────────────
class TopupCard(Base):
    __tablename__ = "topup_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    uid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # رقم الكارت (14 أو 16 رقم)
    card_number: Mapped[str] = mapped_column(String(32), nullable=False)

    # pending / accepted / rejected
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default="pending")

    # عند قبول الكارت يكتب المالك المبلغ بالدولار الذي شُحن للمستخدم
    amount_added: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")

    processed_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, aut

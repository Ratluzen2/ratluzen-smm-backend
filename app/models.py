# app/models.py
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, func

Base = declarative_base()

# ---- Users ----
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(16), default="user")  # user/admin
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

# ---- Notifications ----
class Notice(Base):
    __tablename__ = "notices"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

# ---- Tokens (FCM) ----
class Token(Base):
    __tablename__ = "tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token: Mapped[str] = mapped_column(Text, unique=True)
    for_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

# ---- Service Orders (provider/manual) ----
class ServiceOrder(Base):
    __tablename__ = "service_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    service_key: Mapped[str] = mapped_column(String(120), index=True)    # اسم الخدمة (UI)
    service_code: Mapped[int | None] = mapped_column(Integer, nullable=True)  # رقم الخدمة للمزوّد (قد يكون None للطلبات اليدوية)
    link: Mapped[str | None] = mapped_column(Text, nullable=True)        # رابط/بايلود
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True) # الكمية (قد تكون None للطلبات اليدوية)
    unit_price_per_k: Mapped[float | None] = mapped_column(Float, nullable=True)  # سعر لكل 1000 (اختياري)
    price: Mapped[float] = mapped_column(Float, default=0.0)             # السعر النهائي
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")  # pending/processing/done/rejected/refunded
    provider_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# ---- Wallet Cards (Asiacell) ----
class WalletCard(Base):
    __tablename__ = "wallet_cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    card_number: Mapped[str] = mapped_column(String(32))  # 14 أو 16 رقم
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/accepted/rejected
    amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

# ---- iTunes Orders ----
class ItunesOrder(Base):
    __tablename__ = "itunes_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[int] = mapped_column(Integer)  # قيمة البطاقة
    status: Mapped[str] = mapped_column(String(16), default="pending")
    gift_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

# ---- Phone Topups ----
class PhoneTopup(Base):
    __tablename__ = "phone_topups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    operator: Mapped[str] = mapped_column(String(16))  # atheir/asiacell/korek
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)  # كود التعبئة إن وُجد
    delivered_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

# ---- PUBG Orders ----
class PubgOrder(Base):
    __tablename__ = "pubg_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    pkg: Mapped[int] = mapped_column(Integer)  # 60,120,325,660,1800,3850,8100
    pubg_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

# ---- Ludo Orders ----
class LudoOrder(Base):
    __tablename__ = "ludo_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # diamonds/gold
    pack: Mapped[int] = mapped_column(Integer)
    ludo_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped = mapped_column(DateTime(timezone=True), server_default=func.now())

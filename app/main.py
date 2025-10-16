import os
import json
import time
import logging
import asyncio
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Literal

import requests
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# =========================
# Settings
# =========================
# متغيرات البيئة الأساسية
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL_NEON")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is required")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "2000") # كلمة مرور المشرف الافتراضية
FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY", "").strip() # مفتاح خادم Firebase
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
FCM_PROJECT_ID = os.getenv("FCM_PROJECT_ID", "").strip()  # اختياري لتجاوز الإعدادات

# إعدادات مزود SMM الخارجي
PROVIDER_API_URL = os.getenv("PROVIDER_API_URL", "https://kd1s.com/api/v2")
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "25a9ceb07be0d8b2ba88e70dcbe92e06") # مفتاح API المزود

# إعدادات مجمع اتصال قاعدة البيانات
POOL_MIN, POOL_MAX = 1, int(os.getenv("DB_POOL_MAX", "5"))
dbpool: pool.SimpleConnectionPool = pool.SimpleConnectionPool(POOL_MIN, POOL_MAX, dsn=DATABASE_URL)

# إعداد المسجل
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("app")

# =========================
# Database Helpers
# =========================

def get_conn():
    """يحصل على اتصال من المجمع."""
    try:
        return dbpool.getconn()
    except Exception as e:
        logger.error(f"Failed to get connection from pool: {e}")
        raise HTTPException(status_code=500, detail="Database connection error")

def release_conn(conn):
    """يعيد الاتصال إلى المجمع."""
    if conn:
        try:
            dbpool.putconn(conn)
        except Exception as e:
            logger.error(f"Failed to release connection to pool: {e}")

def db_execute(sql: str, params: Optional[Tuple] = None, fetch_one: bool = False, fetch_all: bool = False, commit: bool = False):
    """
    دالة مساعدة لتنفيذ استعلامات قاعدة البيانات.
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            
            if commit:
                conn.commit()

            if fetch_one:
                return cur.fetchone()
            elif fetch_all:
                return cur.fetchall()
            else:
                return None
    except Exception as e:
        logger.error(f"Database operation failed: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Database operation error")
    finally:
        release_conn(conn)

# =========================
# API Models (Pydantic)
# =========================

class ServiceItem(BaseModel):
    service: int
    name: str
    category: Optional[str] = None
    rate: Optional[Decimal] = None
    min: Optional[int] = None
    max: Optional[int] = None
    override_rate: Optional[Decimal] = Field(None, description="سعر الخدمة الخاص بنا")
    override_min: Optional[int] = Field(None, description="الحد الأدنى الخاص بنا")
    override_max: Optional[int] = Field(None, description="الحد الأقصى الخاص بنا")

class AddOrderBody(BaseModel):
    device_id: str
    service: int
    link: str
    quantity: int

class AddOrderResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    order_id: Optional[int] = None # رقم الطلب في قاعدتنا
    provider_order_id: Optional[int] = None # رقم الطلب لدى المزود

class StatusResponse(BaseModel):
    status: str
    remains: Optional[int] = None
    charge: Optional[Decimal] = None
    start_count: Optional[int] = None

class BalanceDto(BaseModel):
    balance: Decimal
    currency: str = "USD"

class OrderItem(BaseModel):
    id: int
    category: Optional[str] = None
    service: Optional[str] = None
    price: Optional[Decimal] = None
    status: str
    api_order_number: Optional[int] = None
    ordered_at: Optional[str] = None

class LeaderboardEntry(BaseModel):
    user_id: str
    full_name: Optional[str] = None
    total_spent: Decimal

class DepositBody(BaseModel):
    device_id: str
    amount: Decimal
    method: str = "card"

class WalletTransaction(BaseModel):
    id: Optional[int] = None
    device_id: str
    amount: Decimal
    type: Literal["deposit", "withdrawal", "order_fee"] = "deposit"
    method: str = "card"
    status: Literal["pending", "completed", "failed"] = "completed"

class RegisterBody(BaseModel):
    device_id: str
    full_name: Optional[str] = None
    username: Optional[str] = None

class UserDto(BaseModel):
    device_id: str
    full_name: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None
    balance: Decimal = 0.00
    currency: str = "USD"

class FCMTokenIn(BaseModel):
    uid: str
    fcm: str

# نماذج الإدارة
class SvcOverrideIn(BaseModel):
    service_id: int
    rate: Optional[Decimal] = None
    min: Optional[int] = None
    max: Optional[int] = None

class PricingIn(BaseModel):
    type: Literal["flat", "percentage"]
    value: Decimal
    min_order_amount: Optional[Decimal] = None
    is_active: bool = True
    priority: int = 0
    note: Optional[str] = None

# =========================
# App Init & Middleware
# =========================

app = FastAPI(title="SMM Backend API")

# إعدادات CORS
origins = ["*"] # في بيئة الإنتاج، يجب تقييد هذا
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Provider API Helpers (SMM Panel)
# =========================

def provider_request(action: str, data: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    يرسل طلب إلى مزود SMM الخارجي.
    """
    payload = {
        "key": PROVIDER_API_KEY,
        "action": action,
        **data
    }
    try:
        response = requests.post(PROVIDER_API_URL, data=payload, timeout=20)
        response.raise_for_status()
        result = response.json()
        
        # تحقق من وجود "error" في الاستجابة
        if isinstance(result, dict) and "error" in result:
            logger.error(f"Provider API Error for action {action}: {result.get('error')}")
            raise HTTPException(status_code=500, detail=f"Provider API Error: {result.get('error', 'Unknown error')}")
        
        return result
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error for action {action}: {e}")
        raise HTTPException(status_code=503, detail="Provider API Down or Bad Request")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request Error for action {action}: {e}")
        raise HTTPException(status_code=504, detail="Provider API Timeout or Network Error")
    except Exception as e:
        logger.error(f"Unexpected Error for action {action}: {e}")
        raise HTTPException(status_code=500, detail="Internal Provider Error")

def provider_get_balance() -> Decimal:
    """الحصول على رصيد المزود."""
    res = provider_request("balance")
    # نفترض أن الرصيد يأتي في حقل 'balance' بنوع str أو float
    balance_str = res.get('balance', '0.00')
    try:
        return Decimal(str(balance_str))
    except Exception:
        return Decimal('0.00')

def provider_get_services() -> List[Dict[str, Any]]:
    """الحصول على قائمة الخدمات من المزود."""
    return provider_request("services")

def provider_add_order(service_id: int, link: str, quantity: int) -> Dict[str, Any]:
    """وضع طلب لدى المزود."""
    return provider_request("add", {
        "service": service_id,
        "link": link,
        "quantity": quantity
    })

def provider_get_status(order_id: int) -> Dict[str, Any]:
    """الحصول على حالة طلب من المزود."""
    return provider_request("status", {"order": order_id})

# =========================
# User Management
# =========================

@app.post("/api/register", response_model=UserDto)
def register(body: RegisterBody):
    """
    يسجل مستخدماً جديداً أو يعيد معلومات المستخدم الحالي.
    """
    user = db_execute(
        "SELECT * FROM users WHERE device_id = %s",
        (body.device_id,),
        fetch_one=True
    )

    if user:
        # تحديث الاسم أو اسم المستخدم إذا تم توفيره
        update_fields = []
        params = []
        if body.full_name is not None and user.get('full_name') != body.full_name:
            update_fields.append("full_name = %s")
            params.append(body.full_name)
        if body.username is not None and user.get('username') != body.username:
            update_fields.append("username = %s")
            params.append(body.username)

        if update_fields:
            params.append(body.device_id)
            db_execute(
                f"UPDATE users SET {', '.join(update_fields)} WHERE device_id = %s",
                tuple(params),
                commit=True
            )
            # استرجاع المستخدم المحدث
            user = db_execute(
                "SELECT * FROM users WHERE device_id = %s",
                (body.device_id,),
                fetch_one=True
            )
        
        return UserDto(**user)

    # مستخدم جديد - إنشاء
    db_execute(
        "INSERT INTO users (device_id, full_name, username, balance, role) VALUES (%s, %s, %s, %s, %s)",
        (body.device_id, body.full_name, body.username, Decimal('0.00'), 'user'),
        commit=True
    )
    
    new_user = db_execute(
        "SELECT * FROM users WHERE device_id = %s",
        (body.device_id,),
        fetch_one=True
    )
    return UserDto(**new_user)

@app.get("/api/user/{device_id}/balance", response_model=BalanceDto)
def get_user_balance(device_id: str):
    """الحصول على رصيد المستخدم."""
    user = db_execute(
        "SELECT balance FROM users WHERE device_id = %s",
        (device_id,),
        fetch_one=True
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Please register first.")
    return BalanceDto(**user)

# =========================
# Services and Pricing
# =========================

@app.get("/api/services", response_model=List[ServiceItem])
def list_services():
    """يسرد الخدمات مع أسعارنا المطبقة."""
    services_list = db_execute(
        """
        SELECT 
            s.service_id AS service, 
            s.name, 
            s.category, 
            s.rate, 
            s.min, 
            s.max,
            co.rate AS override_rate,
            co.min AS override_min,
            co.max AS override_max
        FROM services s
        LEFT JOIN service_overrides co ON s.service_id = co.service_id
        ORDER BY s.category, s.name
        """,
        fetch_all=True
    )
    if not services_list:
        return []

    return [ServiceItem(**dict(s)) for s in services_list]

# =========================
# Order Handling
# =========================

@app.post("/api/order/add", response_model=AddOrderResponse)
def add_order(body: AddOrderBody):
    """
    يضيف طلباً جديداً: يتحقق من الرصيد والسعر ويضعه لدى المزود.
    """
    user = db_execute(
        "SELECT * FROM users WHERE device_id = %s",
        (body.device_id,),
        fetch_one=True
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    service = db_execute(
        """
        SELECT 
            s.rate, 
            s.min, 
            s.max,
            co.rate AS override_rate,
            co.min AS override_min,
            co.max AS override_max
        FROM services s
        LEFT JOIN service_overrides co ON s.service_id = co.service_id
        WHERE s.service_id = %s
        """,
        (body.service,),
        fetch_one=True
    )
    if not service:
        raise HTTPException(status_code=404, detail="Service not found.")

    # 1. تحديد السعر والحدود النهائية
    provider_rate = service['rate'] or Decimal('0.001') # سعر المزود الأساسي
    final_rate = service['override_rate'] or provider_rate # سعر البيع النهائي (إذا تم تعيينه)
    
    # حساب سعر الطلب للمستخدم (تكلفة كل وحدة * الكمية)
    order_cost = final_rate * Decimal(body.quantity)
    
    # 2. التحقق من الرصيد
    if user['balance'] < order_cost:
        raise HTTPException(status_code=400, detail="Insufficient balance.")

    # 3. التحقق من الحدود الدنيا والقصوى
    min_qty = service['override_min'] or service['min']
    max_qty = service['override_max'] or service['max']
    
    if min_qty and body.quantity < min_qty:
        raise HTTPException(status_code=400, detail=f"Quantity must be at least {min_qty}.")
    if max_qty and body.quantity > max_qty:
        raise HTTPException(status_code=400, detail=f"Quantity must be at most {max_qty}.")

    # 4. وضع الطلب لدى المزود الخارجي
    try:
        provider_res = provider_add_order(
            service_id=body.service,
            link=body.link,
            quantity=body.quantity
        )
    except HTTPException as e:
        logger.error(f"Provider order failed for user {body.device_id}: {e.detail}")
        return AddOrderResponse(success=False, message=e.detail)
    except Exception as e:
        logger.error(f"Provider order failed for user {body.device_id}: {e}")
        return AddOrderResponse(success=False, message="Failed to place order with provider.")

    provider_order_id = provider_res.get('order')
    if not provider_order_id:
        return AddOrderResponse(success=False, message="Provider returned success but no order ID.")

    # 5. تسجيل الطلب في قاعدتنا وتحديث الرصيد
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # خصم الرصيد
            cur.execute(
                "UPDATE users SET balance = balance - %s WHERE device_id = %s",
                (order_cost, body.device_id)
            )
            # تسجيل الطلب
            cur.execute(
                """
                INSERT INTO orders 
                (device_id, service_id, link, quantity, price, status, api_order_number) 
                VALUES (%s, %s, %s, %s, %s, 'Pending', %s) 
                RETURNING id
                """,
                (body.device_id, body.service, body.link, body.quantity, order_cost, provider_order_id)
            )
            local_order_id = cur.fetchone()[0]
            
            # تسجيل المعاملة
            cur.execute(
                """
                INSERT INTO wallet_transactions 
                (device_id, amount, type, method, status) 
                VALUES (%s, %s, 'order_fee', %s, 'completed')
                """,
                (body.device_id, -order_cost, f"Order {local_order_id}", 'completed')
            )
            
            conn.commit()

        return AddOrderResponse(
            success=True,
            order_id=local_order_id,
            provider_order_id=provider_order_id
        )
    except Exception as e:
        logger.error(f"Failed to record order and update balance: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Internal order processing error.")
    finally:
        release_conn(conn)

@app.get("/api/order/{provider_order_id}/status", response_model=StatusResponse)
def get_order_status(provider_order_id: int):
    """الحصول على حالة طلب من المزود الخارجي."""
    res = provider_get_status(provider_order_id)
    
    # تحويل حالة المزود إلى حالتنا
    status_map = {
        'Pending': 'Pending',
        'In progress': 'In Progress',
        'Processing': 'In Progress',
        'Partial': 'Partial',
        'Completed': 'Done',
        'Canceled': 'Cancelled',
        'Refunded': 'Refunded'
        # قد تحتاج لإضافة المزيد حسب مزودك
    }
    
    provider_status = res.get('status', 'Error')
    our_status = status_map.get(provider_status, 'Error')

    return StatusResponse(
        status=our_status,
        remains=res.get('remains'),
        charge=res.get('charge'),
        start_count=res.get('start_count')
    )

@app.get("/api/orders/{device_id}", response_model=List[OrderItem])
def list_user_orders(device_id: str):
    """يسرد جميع طلبات المستخدم."""
    orders = db_execute(
        """
        SELECT 
            o.id, 
            o.price, 
            o.status, 
            o.api_order_number, 
            o.ordered_at, 
            s.name AS service, 
            s.category
        FROM orders o
        JOIN services s ON o.service_id = s.service_id
        WHERE o.device_id = %s
        ORDER BY o.ordered_at DESC
        """,
        (device_id,),
        fetch_all=True
    )
    if not orders:
        return []
    
    return [OrderItem(**dict(o)) for o in orders]

# =========================
# Wallet (Mocked Deposit)
# =========================

@app.post("/api/wallet/deposit", response_model=WalletTransaction)
def wallet_deposit_mock(body: DepositBody):
    """
    إضافة إيداع وهمي (لأغراض الاختبار والواجهة).
    في التطبيق الحقيقي، هذا المسار يتطلب تكامل مع بوابة دفع.
    """
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive.")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # 1. تحديث رصيد المستخدم
            cur.execute(
                "UPDATE users SET balance = balance + %s WHERE device_id = %s RETURNING device_id",
                (body.amount, body.device_id)
            )
            updated_user = cur.fetchone()
            if not updated_user:
                raise HTTPException(status_code=404, detail="User not found.")

            # 2. تسجيل المعاملة
            cur.execute(
                """
                INSERT INTO wallet_transactions 
                (device_id, amount, type, method, status) 
                VALUES (%s, %s, 'deposit', %s, 'completed') 
                RETURNING id
                """,
                (body.device_id, body.amount, body.method)
            )
            transaction_id = cur.fetchone()[0]
            
            conn.commit()

        return WalletTransaction(
            id=transaction_id,
            device_id=body.device_id,
            amount=body.amount,
            type="deposit",
            method=body.method,
            status="completed"
        )
    except HTTPException:
        conn.rollback()
        raise # إعادة إطلاق 404
    except Exception as e:
        logger.error(f"Deposit error for user {body.device_id}: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Deposit processing error.")
    finally:
        release_conn(conn)

# =========================
# Leaderboard
# =========================

@app.get("/api/leaderboard", response_model=List[LeaderboardEntry])
def get_leaderboard():
    """يسرد المتصدرين حسب إجمالي الإنفاق."""
    leaderboard = db_execute(
        """
        SELECT 
            device_id AS user_id, 
            full_name, 
            (SELECT COALESCE(SUM(price), 0.00) FROM orders WHERE orders.device_id = users.device_id AND status != 'Cancelled') AS total_spent
        FROM users
        ORDER BY total_spent DESC
        LIMIT 10
        """,
        fetch_all=True
    )
    if not leaderboard:
        return []
    
    return [LeaderboardEntry(**dict(l)) for l in leaderboard]

# =========================
# FCM Token
# =========================

# قد تحتاج لاستخدام Google Admin SDK هنا، لكن سنستخدم طريقة تحديث قاعدة البيانات مباشرةً
@app.post("/api/users/fcm_token")
def update_fcm_token(body: FCMTokenIn):
    """يحدث رمز FCM للمستخدم لتلقي الإشعارات."""
    db_execute(
        "UPDATE users SET fcm_token = %s WHERE device_id = %s",
        (body.fcm, body.uid),
        commit=True
    )
    return {"message": "FCM token updated successfully"}

# =========================
# Health Check
# =========================

@app.get("/health")
def health_check():
    """تحقق بسيط من صحة الخادم وقاعدة البيانات."""
    try:
        # اختبار اتصال قاعدة البيانات
        db_execute("SELECT 1", fetch_one=True)
        db_ok = True
    except:
        db_ok = False
    
    # اختبار اتصال المزود الخارجي
    provider_ok = False
    try:
        balance = provider_get_balance()
        provider_ok = True
    except:
        pass

    return {
        "status": "ok",
        "timestamp": int(time.time()),
        "db_status": "ok" if db_ok else "error",
        "provider_status": "ok" if provider_ok else "error"
    }

# =========================
# Admin Endpoints (Requires Password)
# =========================

def check_admin_auth(x_admin_password: Optional[str], password: Optional[str]):
    """وظيفة للتحقق من كلمة مرور المشرف."""
    provided_password = x_admin_password or password
    if not provided_password or provided_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password")

@app.post("/api/admin/services/sync")
def admin_sync_services(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    """
    يقوم بمزامنة (جلب) جميع الخدمات من المزود الخارجي.
    يحافظ على سجلات الأسعار والحدود المخصصة (Overrides).
    """
    check_admin_auth(x_admin_password, password)
    
    logger.info("Starting service sync from provider...")
    
    try:
        provider_services = provider_get_services()
    except Exception as e:
        logger.error(f"Failed to fetch services from provider: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync services from external provider")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # استخدام JSON للتخزين المؤقت لبيانات الخدمات الجديدة
            services_json = Json(provider_services)
            
            # استدعاء دالة PostgreSQL لإجراء عملية Upsert
            cur.callproc('sync_provider_services', [services_json])
            
            conn.commit()
            
            # يتم إرجاع نتيجة من الدالة المخزنة (عادةً عدد السجلات المضافة/المحدثة)
            return {"message": "Services synced successfully", "count": len(provider_services)}
            
    except psycopg2.Error as e:
        logger.error(f"Database sync failed: {e}")
        conn.rollback()
        raise HTTPException(status_code=500, detail="Database error during sync")
    finally:
        release_conn(conn)


@app.get("/api/admin/services/overrides", response_model=List[SvcOverrideIn])
def admin_list_service_ids(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    """يسرد جميع تجاوزات الخدمات (الأسعار والحدود المخصصة)."""
    check_admin_auth(x_admin_password, password)
    
    overrides = db_execute(
        "SELECT service_id, rate, min, max FROM service_overrides",
        fetch_all=True
    )
    
    if not overrides:
        return []
    
    return [SvcOverrideIn(**dict(o)) for o in overrides]

@app.post("/api/admin/services/override/set")
def admin_set_service_id(body: SvcOverrideIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    """يعيّن سعراً مخصصاً لخدمة معينة (يحدث/ينشئ سجل Overrides)."""
    check_admin_auth(x_admin_password, password)
    
    # تأكد من أن الخدمة موجودة في جدول services
    service_exists = db_execute("SELECT 1 FROM services WHERE service_id = %s", (body.service_id,), fetch_one=True)
    if not service_exists:
        raise HTTPException(status_code=404, detail=f"Service ID {body.service_id} not found in main services list.")

    db_execute(
        """
        INSERT INTO service_overrides (service_id, rate, min, max)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (service_id) DO UPDATE
        SET rate = EXCLUDED.rate, min = EXCLUDED.min, max = EXCLUDED.max
        """,
        (body.service_id, body.rate, body.min, body.max),
        commit=True
    )
    
    return {"message": f"Override set for service {body.service_id}"}

@app.post("/api/admin/services/override/clear")
def admin_clear_service_id(body: SvcOverrideIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    """يزيل التجاوز (Override) لخدمة معينة (يعيدها لسعر المزود)."""
    check_admin_auth(x_admin_password, password)
    
    db_execute(
        "DELETE FROM service_overrides WHERE service_id = %s",
        (body.service_id,),
        commit=True
    )
    
    return {"message": f"Override cleared for service {body.service_id}"}

# ---- Pricing rules ----

@app.get("/api/admin/pricing/overrides", response_model=List[PricingIn])
def admin_list_pricing(x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    """يسرد جميع قواعد التسعير الإضافية (مثل الخصومات العامة أو الزيادات)."""
    check_admin_auth(x_admin_password, password)
    
    rules = db_execute(
        "SELECT type, value, min_order_amount, is_active, priority, note FROM pricing_rules ORDER BY priority DESC, id",
        fetch_all=True
    )
    
    if not rules:
        return []
    
    return [PricingIn(**dict(r)) for r in rules]

@app.post("/api/admin/pricing/override/set")
def admin_set_pricing(body: PricingIn, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    """يعيّن قاعدة تسعير جديدة أو يحدّثها. (لا يوجد ID تلقائيًا، قد تحتاج لتعديل هذا للإنتاج)."""
    check_admin_auth(x_admin_password, password)
    
    # ملاحظة: في بيئة الإنتاج، يجب أن يكون هناك ID لتمكين التحديث بدلاً من الإدخال المتكرر.
    # سنفترض هنا أن كل إدخال فريد هو قاعدة جديدة بسيطة لغرض الاختبار.

    db_execute(
        """
        INSERT INTO pricing_rules (type, value, min_order_amount, is_active, priority, note)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (body.type, body.value, body.min_order_amount, body.is_active, body.priority, body.note),
        commit=True
    )
    
    return {"message": "Pricing rule added successfully"}

@app.post("/api/admin/pricing/override/delete")
def admin_delete_pricing(rule_id: int, x_admin_password: Optional[str] = Header(None, alias="x-admin-password"), password: Optional[str] = None):
    """يحذف قاعدة تسعير بواسطة ID (افتراضيًا ID هو الرقم التلقائي في الجدول)."""
    check_admin_auth(x_admin_password, password)
    
    deleted_rows = db_execute(
        "DELETE FROM pricing_rules WHERE id = %s RETURNING id",
        (rule_id,),
        fetch_one=True,
        commit=True
    )
    
    if not deleted_rows:
        raise HTTPException(status_code=404, detail=f"Pricing rule with ID {rule_id} not found.")

    return {"message": f"Pricing rule with ID {rule_id} deleted successfully"}


# =========================
# Database Schema (مخطط قاعدة البيانات - لتسهيل الإعداد)
# هذا الجزء هو مجرد تذكير/إرشادات - لا يتم تنفيذه تلقائيًا عند تشغيل FastAPI
# =========================
"""
CREATE TABLE IF NOT EXISTS users (
    device_id VARCHAR(255) PRIMARY KEY,
    full_name VARCHAR(255) NULL,
    username VARCHAR(255) NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'user',
    balance NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    fcm_token TEXT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS services (
    service_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category VARCHAR(255) NULL,
    rate NUMERIC(10, 5) NULL,
    min INTEGER NULL,
    max INTEGER NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_synced TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS service_overrides (
    service_id INTEGER PRIMARY KEY REFERENCES services(service_id) ON DELETE CASCADE,
    rate NUMERIC(10, 5) NULL,
    min INTEGER NULL,
    max INTEGER NULL
);

CREATE TABLE IF NOT EXISTS pricing_rules (
    id SERIAL PRIMARY KEY,
    type VARCHAR(50) NOT NULL, -- 'flat' or 'percentage'
    value NUMERIC(10, 5) NOT NULL,
    min_order_amount NUMERIC(10, 2) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 0,
    note TEXT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) REFERENCES users(device_id),
    service_id INTEGER REFERENCES services(service_id),
    link TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'Pending',
    api_order_number INTEGER NULL,
    ordered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orders_device_id ON orders(device_id);

CREATE TABLE IF NOT EXISTS wallet_transactions (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) REFERENCES users(device_id),
    amount NUMERIC(10, 2) NOT NULL,
    type VARCHAR(50) NOT NULL, -- 'deposit', 'withdrawal', 'order_fee'
    method VARCHAR(100) NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_wallet_device_id ON wallet_transactions(device_id);

-- دالة PostgreSQL لإجراء Upsert للخدمات عند المزامنة
-- يجب تنفيذ هذه الدالة في قاعدة البيانات:
/*
CREATE OR REPLACE FUNCTION sync_provider_services(services_data JSON)
RETURNS VOID AS $$
DECLARE
    service_record JSON;
BEGIN
    FOR service_record IN SELECT * FROM json_array_elements(services_data)
    LOOP
        INSERT INTO services (service_id, name, category, rate, min, max, last_synced)
        VALUES (
            (service_record->>'service')::INT,
            service_record->>'name',
            service_record->>'category',
            (service_record->>'rate')::NUMERIC,
            (service_record->>'min')::INT,
            (service_record->>'max')::INT,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (service_id) DO UPDATE
        SET 
            name = EXCLUDED.name,
            category = EXCLUDED.category,
            rate = EXCLUDED.rate,
            min = EXCLUDED.min,
            max = EXCLUDED.max,
            last_synced = EXCLUDED.last_synced;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
*/
"""

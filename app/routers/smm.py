# راوتر إضافي إن رغبت بفصل مزيد من مسارات SMM لاحقاً
from fastapi import APIRouter
router = APIRouter(prefix="/api/smm", tags=["smm"])

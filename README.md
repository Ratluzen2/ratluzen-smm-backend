# Ratlwzan API (FastAPI + Neon Postgres via Heroku)

باك-إند لخدمات "خدمات راتلوزن" مبني بـ FastAPI و SQLAlchemy.
ينشر على Heroku ويتصل بقاعدة Postgres على Neon.

## المتطلبات
- حساب Heroku
- حساب Neon (قاعدة Postgres)
- Python 3.11 (Heroku يقرأها من `runtime.txt`)

## الإعداد على Neon
1. أنشئ مشروع + قاعدة جديدة.
2. انسخ **Connection string** بصيغة:

SERVICE_CATALOG = {
    16256: {"name": "متابعين تيكتوك",    "min": 100, "max": 1_000_000, "pricePerK": 3.5, "category": "المتابعين"},
    16267: {"name": "متابعين انستغرام",  "min": 100, "max": 1_000_000, "pricePerK": 3.0, "category": "المتابعين"},
    12320: {"name": "لايكات تيكتوك",     "min": 100, "max": 1_000_000, "pricePerK": 1.0, "category": "الايكات"},
    1066500:{"name": "لايكات انستغرام",   "min": 100, "max": 1_000_000, "pricePerK": 1.0, "category": "الايكات"},
    9448:  {"name": "مشاهدات تيكتوك",    "min": 100, "max": 1_000_000, "pricePerK": 0.1, "category": "المشاهدات"},
    64686464:{"name": "مشاهدات انستغرام", "min": 100, "max": 1_000_000, "pricePerK": 0.1, "category": "المشاهدات"},
    14442: {"name": "مشاهدات بث تيكتوك", "min": 100, "max": 1_000_000, "pricePerK": 2.0, "category": "مشاهدات البث المباشر"},
    646464:{"name": "مشاهدات بث انستغرام","min":100, "max":1_000_000,  "pricePerK": 2.0, "category": "مشاهدات البث المباشر"},
    14662: {"name": "رفع سكور البث",     "min": 100, "max": 1_000_000, "pricePerK": 2.0, "category": "رفع سكور تيكتوك"},
    955656:{"name": "اعضاء قنوات تلي",   "min": 100, "max": 1_000_000, "pricePerK": 3.0, "category": "خدمات التليجرام"},
    644656:{"name": "اعضاء كروبات تلي",  "min": 100, "max": 1_000_000, "pricePerK": 3.0, "category": "خدمات التليجرام"},
}

SERVICE_CATEGORIES = [
    "قسم المتابعين",
    "قسم الايكات",
    "قسم المشاهدات",
    "قسم مشاهدات البث المباشر",
    "قسم رفع سكور تيكتوك",
    "قسم خدمات التليجرام",
    "قسم شراء رصيد ايتونز",
    "قسم شراء رصيد هاتف",
    "قسم شحن شدات ببجي",
    "قسم خدمات الودو"
]

def calc_price(service_id: int, qty: int) -> float:
    svc = SERVICE_CATALOG.get(int(service_id))
    if not svc:
        raise ValueError("SERVICE_NOT_FOUND")
    if qty < svc["min"] or qty > svc["max"]:
        raise ValueError("INVALID_QTY")
    raw = (qty / 1000.0) * float(svc["pricePerK"])
    return round((int(raw * 100 + 0.9999)) / 100.0, 2)  # تقريب سنتات لأعلى

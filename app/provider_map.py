from .config import settings

def get_provider():
    return {
        "name": "default",
        "api_url": settings.SMM_API_URL.rstrip("/"),
        "api_key": settings.SMM_API_KEY,
    }

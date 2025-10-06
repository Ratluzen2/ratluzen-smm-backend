import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str = os.environ["DATABASE_URL"]
    SMM_API_URL: str = os.getenv("SMM_API_URL", "https://kd1s.com/api/v2")
    SMM_API_KEY: str = os.getenv("SMM_API_KEY", "")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "2000")

def get_settings() -> Settings:
    return Settings()

from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

# بارگذاری متغیرهای محیطی از env.dat
load_dotenv("env.dat")

class Settings(BaseSettings):
    BOT_TOKEN: str = os.getenv("BOT_TOKEN")
    API_ID: int = int(os.getenv("API_ID", "0"))  # مقدار پیش‌فرض 0 برای جلوگیری از خطا
    API_HASH: str = os.getenv("API_HASH", "")

    GOOSHKON_BOT_USERNAME: str = os.getenv("GOOSHKON_BOT_USERNAME")
    GOOSHKON_BOT_PASSWORD: str = os.getenv("GOOSHKON_BOT_PASSWORD")
    BASE_URL: str = "https://gooshkon.ir"
    WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST")
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))

    class Config:
        env_file = "env.dat"  # تعیین فایل env برای بارگذاری

# مقداردهی متغیر settings
settings = Settings()

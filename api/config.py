import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL", "postgresql://bi_admin:bi_secret@db:5432/bi_dwh")
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    api_secret_key: str = os.getenv("API_SECRET_KEY", "change-me")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480


settings = Settings()

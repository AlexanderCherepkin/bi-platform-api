import os
from pydantic_settings import BaseSettings


class EtlSettings(BaseSettings):
    database_url: str = os.getenv("DATABASE_URL", "postgresql://bi_admin:bi_secret@db:5432/bi_dwh")
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

    onec_enabled: bool = os.getenv("ETL_1C_ENABLED", "false").lower() == "true"
    onec_base_url: str = os.getenv("ETL_1C_BASE_URL", "http://1c.local/api")
    onec_username: str = os.getenv("ETL_1C_USERNAME", "")
    onec_password: str = os.getenv("ETL_1C_PASSWORD", "")
    onec_demo_mode: bool = os.getenv("ETL_1C_DEMO", "true").lower() == "true"

    amocrm_enabled: bool = os.getenv("ETL_AMOCRM_ENABLED", "false").lower() == "true"
    amocrm_base_url: str = os.getenv("ETL_AMOCRM_BASE_URL", "https://example.amocrm.ru")
    amocrm_access_token: str = os.getenv("ETL_AMOCRM_ACCESS_TOKEN", "")
    amocrm_demo_mode: bool = os.getenv("ETL_AMOCRM_DEMO", "true").lower() == "true"

    gsheets_enabled: bool = os.getenv("ETL_GSHEETS_ENABLED", "false").lower() == "true"
    gsheets_sheet_id: str = os.getenv("ETL_GSHEETS_SHEET_ID", "")
    gsheets_gid: int = int(os.getenv("ETL_GSHEETS_GID", "0"))
    gsheets_demo_mode: bool = os.getenv("ETL_GSHEETS_DEMO", "true").lower() == "true"

    etl_run_interval_minutes: int = int(os.getenv("ETL_RUN_INTERVAL_MINUTES", "60"))
    metrics_cache_ttl_seconds: int = int(os.getenv("METRICS_CACHE_TTL_SECONDS", "300"))


settings = EtlSettings()

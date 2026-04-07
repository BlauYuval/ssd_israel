from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/tase_screener"
    DATABASE_SYNC_URL: str = "postgresql://postgres:password@localhost:5432/tase_screener"

    EODHD_API_KEY: str = ""

    MAYA_BASE_URL: str = "https://maya.tase.co.il"
    TASE_API_BASE_URL: str = "https://api.tase.co.il/api"

    SCRAPER_DELAY_SECONDS: float = 1.5
    SCRAPER_MAX_RETRIES: int = 3


settings = Settings()

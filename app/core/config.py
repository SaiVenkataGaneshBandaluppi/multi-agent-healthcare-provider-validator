"""
MIT License
Core application configuration loaded from environment variables.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    GROQ_API_KEY: str = ""
    NPPES_BASE_URL: str = "https://npiregistry.cms.hhs.gov/api"
    RATE_LIMIT_PER_MINUTE: int = 60
    VALIDATION_RATE_LIMIT: int = 10
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

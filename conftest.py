"""
Root conftest: set required environment variables before any app module is imported.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/healthcare_validator")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-not-production")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "testpassword123")

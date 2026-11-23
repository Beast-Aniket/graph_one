from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    api_prefix: str = "/api/v1"
    api_key: str = ""
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    database_url: str = "postgresql+asyncpg://graphone:graphone@localhost:5432/graphone"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "graphone"
    s3_secret_key: str = "change-this-minio-secret"
    s3_bucket: str = "graphone-raw"
    s3_region: str = "us-east-1"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "change-this-neo4j-password"

    crawler_user_agent: str = "GraphOneFrontierAtlas/1.0 (+contact@example.com)"
    crawler_timeout_seconds: float = 30.0
    crawler_max_retries: int = 4
    crawler_concurrency: int = 5
    llm_max_chunk_chars: int = 12000

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    google_sheets_webhook_url: str = ""
    github_token: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


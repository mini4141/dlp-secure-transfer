from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "postgresql+asyncpg://dlp_app:dlp_app@localhost:5432/dlp"
    db_null_pool: bool = False

    jwt_secret: str = "dev-only-jwt-secret-change-me-0123456789"
    scan_hmac_secret: str = "dev-only-hmac-secret-change-me"
    cookie_secure: bool = False
    session_hours: int = 8

    aws_region: str = "ap-southeast-2"
    aws_endpoint_url: str | None = None  # moto locally; empty in AWS
    s3_public_endpoint_url: str | None = None  # endpoint browsers use for presigned URLs
    s3_bucket: str = "dlp-transfers"
    sqs_queue_name: str = "dlp-scan"
    bootstrap_aws: bool = False  # create bucket/queues (local stand-ins only)
    sqs_visibility_timeout: int = 15

    seed_on_start: bool = False
    max_file_bytes: int = 25 * 1024 * 1024
    upload_url_ttl: int = 900
    download_url_ttl: int = 60

    otel_exporter_otlp_endpoint: str | None = None
    service_name: str = "dlp-api"


@lru_cache
def get_settings() -> Settings:
    return Settings()

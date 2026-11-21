"""Application configuration — read from environment, nothing hardcoded."""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database
    database_url: str
    database_url_pooled: str | None = None

    # Auth
    jwt_secret: str
    jwt_access_ttl_min: int = 30
    jwt_refresh_ttl_days: int = 7

    # AWS
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    aws_region: str = "us-east-1"
    s3_bucket_name: str | None = None
    s3_kms_key_id: str | None = None

    # Bedrock
    # Inference-profile ID (on-demand model IDs for newer models need a profile).
    bedrock_model_id: str = "us.amazon.nova-lite-v1:0"
    bedrock_embed_model_id: str = "amazon.titan-embed-text-v2:0"
    # Tried in order when the primary model is throttled. Bedrock's daily
    # token allowance is account-wide, so this rarely rescues a daily
    # throttle — but it does rescue a per-model limit, and it costs nothing.
    bedrock_fallback_model_ids: str = (
        "us.amazon.nova-micro-v1:0,meta.llama3-1-8b-instruct-v1:0,"
        "mistral.mistral-7b-instruct-v0:2"
    )

    # Provider selection (AWS active by default; local fallbacks when creds absent)
    storage_impl: str = "local"  # "s3" once a bucket is provisioned
    extractor_impl: str = "pdfplumber"  # "textract" if the account allows it
    embedder_impl: str = "bge-m3"  # "titan-v2" once Bedrock embedding quota is available
    llm_impl: str = "bedrock-converse"

    # RAG / retrieval tuning
    min_score: float = 0.30
    top_k: int = 6
    max_upload_mb: int = 50
    allowed_mime_types: str = (
        "application/pdf,"
        "image/png,image/jpeg,image/tiff,image/bmp,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "text/csv,text/comma-separated-values,"
        "text/plain,text/markdown,"
        "application/rtf,"
        "text/html"
    )

    # CORS
    cors_origins: str = "http://localhost:3000"

    @property
    def async_database_url(self) -> str:
        """asyncpg-compatible URL derived from the libpq-style DATABASE_URL.

        Neon hands out `postgresql://…?sslmode=require&channel_binding=require`.
        asyncpg needs the `+asyncpg` driver and rejects those query args, so we
        swap the scheme and express TLS as `ssl=require`.
        """
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        parts = urlsplit(self.database_url)
        scheme = "postgresql+asyncpg"
        query = dict(parse_qsl(parts.query))
        wants_tls = query.pop("sslmode", None) in {"require", "verify-ca", "verify-full"}
        query.pop("channel_binding", None)
        if wants_tls or "ssl" in query:
            query["ssl"] = query.get("ssl", "require")
        return urlunsplit((scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_mime_types_list(self) -> List[str]:
        return [m.strip() for m in self.allowed_mime_types.split(",") if m.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
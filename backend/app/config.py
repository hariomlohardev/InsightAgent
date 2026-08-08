import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

# Project root is two levels above this file's parent (backend/app -> backend -> root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_name: str = "InsightAgent"
    version: str = "0.1.0"
    host: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    port: int = int(os.getenv("BACKEND_PORT", "8000"))
    # Default to PROJECT_ROOT/storage, not cwd-dependent
    storage_path: Path = Path(os.getenv("STORAGE_PATH", str(PROJECT_ROOT / "storage")))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "100"))
    # LLM providers
    llm_provider: str = os.getenv(
        "LLM_PROVIDER", "auto"
    )  # auto, openai, groq, gemini, claude, ollama
    llm_model: str | None = os.getenv("LLM_MODEL")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    google_api_key: str | None = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    execution_timeout_sec: int = 5
    # L7 Enterprise
    auth_required: bool = os.getenv("AUTH_REQUIRED", "false").lower() in ("true", "1", "yes")
    enterprise: bool = os.getenv("ENTERPRISE", "false").lower() in ("true", "1", "yes")
    jwt_secret: str | None = os.getenv("JWT_SECRET")
    # L8 Cloud
    cloud: bool = os.getenv("CLOUD", "false").lower() in ("true", "1", "yes")
    stripe_secret_key: str | None = os.getenv("STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = os.getenv("STRIPE_WEBHOOK_SECRET")
    stripe_price_pro: str | None = os.getenv("STRIPE_PRICE_PRO")
    stripe_price_team: str | None = os.getenv("STRIPE_PRICE_TEAM")
    stripe_price_enterprise: str | None = os.getenv("STRIPE_PRICE_ENTERPRISE")
    # L09 Data Foundation
    database_url: str | None = os.getenv("DATABASE_URL")
    storage_backend: str = os.getenv("STORAGE_BACKEND", "fs")  # fs | s3
    s3_bucket: str | None = os.getenv("S3_BUCKET")
    s3_endpoint: str | None = os.getenv("S3_ENDPOINT") or os.getenv("AWS_ENDPOINT_URL_S3")
    otel_endpoint: str | None = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    sentry_dsn: str | None = os.getenv("SENTRY_DSN")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# Ensure storage_path is resolved correctly
# If STORAGE_PATH was relative, resolve relative to PROJECT_ROOT, not cwd
if not settings.storage_path.is_absolute():
    settings.storage_path = (PROJECT_ROOT / settings.storage_path).resolve()
else:
    settings.storage_path = settings.storage_path.resolve()

import contextvars

_workspace_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "workspace_id", default="default"
)


def set_workspace_id(ws_id: str):
    _workspace_id_ctx.set(ws_id or "default")


def get_workspace_id() -> str:
    try:
        return _workspace_id_ctx.get()
    except LookupError:
        return "default"


def is_cloud() -> bool:
    return os.getenv("CLOUD", "false").lower() in ("true", "1", "yes")


def get_storage_path() -> Path:
    base = settings.storage_path
    if is_cloud():
        ws_id = get_workspace_id()
        # sanitize ws_id
        ws_id = "".join(c for c in ws_id if c.isalnum() or c in ("-", "_"))[:32] or "default"
        p = base / "workspaces" / ws_id
        p.mkdir(parents=True, exist_ok=True)
        # ensure default workspace also has plain storage layout for migration? Not needed
        return p
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_base_storage_path() -> Path:
    """Root storage regardless of workspace (for admin stats)."""
    p = settings.storage_path
    p.mkdir(parents=True, exist_ok=True)
    return p

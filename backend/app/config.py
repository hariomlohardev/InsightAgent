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
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    execution_timeout_sec: int = 5

    class Config:
        env_file = ".env"

settings = Settings()

# Ensure storage_path is resolved correctly
# If STORAGE_PATH was relative, resolve relative to PROJECT_ROOT, not cwd
if not settings.storage_path.is_absolute():
    settings.storage_path = (PROJECT_ROOT / settings.storage_path).resolve()
else:
    settings.storage_path = settings.storage_path.resolve()

def get_storage_path() -> Path:
    p = settings.storage_path
    p.mkdir(parents=True, exist_ok=True)
    return p

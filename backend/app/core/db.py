"""
Level 09 — DB layer with graceful filesystem fallback.
Usage:
  from app.core.db import use_db, get_engine, Base, get_session, init_db

If DATABASE_URL is empty or sqlalchemy import fails, use_db() -> False
and filesystem storage is used (contributor `docker compose up` frictionless).
Supports:
  - postgresql+asyncpg://... (prod)
  - postgresql+psycopg://... (sync fallback)
  - sqlite+aiosqlite:///./test.db (CI/tests)
"""
import os
import logging

logger = logging.getLogger(__name__)

# Lazy import sqlalchemy so missing dep doesn't crash contributor without DB
try:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase
    from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Boolean
    _SA_AVAILABLE = True
except Exception as e:
    logger.info(f"SQLAlchemy not available, filesystem fallback: {e}")
    _SA_AVAILABLE = False
    # dummy placeholders to keep import safe
    DeclarativeBase = object  # type: ignore

_engine = None
_SessionLocal = None

def use_db() -> bool:
    """True only when DATABASE_URL set and SQLAlchemy available and engine can be created."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return False
    if not _SA_AVAILABLE:
        return False
    # sqlite memory or file is ok for tests; postgres requires async driver
    # Allow sqlite fallback even if url looks like postgres but driver missing
    return True

def get_database_url() -> str | None:
    url = os.getenv("DATABASE_URL", "").strip()
    return url or None

def _normalize_url(url: str) -> str:
    # Handle plain postgresql:// -> postgresql+asyncpg:// for async
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url

def get_engine():
    global _engine
    if _engine is not None:
        return _engine
    if not use_db():
        return None
    url = _normalize_url(get_database_url())  # type: ignore
    try:
        # For sqlite aiosqlite, no pool args
        if "sqlite" in url:
            _engine = create_async_engine(url, echo=False, future=True)
        else:
            _engine = create_async_engine(url, echo=False, future=True, pool_pre_ping=True)
        return _engine
    except Exception as e:
        logger.warning(f"Failed to create engine for {url}: {e}")
        return None

def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is not None:
        return _SessionLocal
    eng = get_engine()
    if eng is None:
        return None
    try:
        _SessionLocal = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        return _SessionLocal
    except Exception as e:
        logger.warning(f"Failed to create sessionmaker: {e}")
        return None

# Base for models
if _SA_AVAILABLE:
    class Base(DeclarativeBase):
        pass
else:
    class Base:  # type: ignore
        pass

# --- Models matching current JSON shape (id TEXT PK, workspace_id, meta JSONB) ---
if _SA_AVAILABLE:
    from sqlalchemy import JSON as SA_JSON
    # Use generic JSON for sqlite compat; postgres will map to JSONB via dialect
    class DatasetRow(Base):
        __tablename__ = "datasets"
        id = Column(String, primary_key=True)
        workspace_id = Column(String, index=True, default="default")
        original_filename = Column(String)
        rows = Column(Integer)
        columns = Column(Integer)
        column_names = Column(SA_JSON)
        meta_json = Column(SA_JSON)  # full meta
        created_at = Column(DateTime)
        owner = Column(String, nullable=True)

    class DashboardRow(Base):
        __tablename__ = "dashboards"
        id = Column(String, primary_key=True)
        workspace_id = Column(String, index=True, default="default")
        dataset_id = Column(String, index=True)
        name = Column(String)
        description = Column(Text, nullable=True)
        widgets = Column(SA_JSON, default=list)
        created_at = Column(DateTime)

    class UserRow(Base):
        __tablename__ = "users"
        id = Column(String, primary_key=True)
        email = Column(String, unique=True, index=True)
        role = Column(String, default="viewer")
        password_hash = Column(String)
        workspace_id = Column(String, index=True, default="default")
        created_at = Column(DateTime)

    class WorkspaceRow(Base):
        __tablename__ = "workspaces"
        id = Column(String, primary_key=True)
        name = Column(String)
        owner_id = Column(String, nullable=True)
        tier = Column(String, default="free")
        created_at = Column(DateTime)

    class BillingRow(Base):
        __tablename__ = "billing"
        id = Column(String, primary_key=True)
        workspace_id = Column(String, index=True)
        datasets_used = Column(Integer, default=0)
        created_at = Column(DateTime)
        updated_at = Column(DateTime)

    class AuditRow(Base):
        __tablename__ = "audit_log"
        id = Column(String, primary_key=True)
        workspace_id = Column(String, index=True, default="default")
        user_id = Column(String, nullable=True)
        action = Column(String)
        dataset_id = Column(String, nullable=True)
        ip = Column(String, nullable=True)
        extra = Column(Text, nullable=True)
        at = Column(DateTime)
else:
    # placeholders when SA not available
    DatasetRow = DashboardRow = UserRow = WorkspaceRow = BillingRow = AuditRow = None  # type: ignore

async def get_session():
    """FastAPI dependency: yields AsyncSession or None when use_db()==False."""
    sm = get_sessionmaker()
    if sm is None:
        yield None
        return
    async with sm() as session:
        yield session

async def init_db():
    """Create tables if DATABASE_URL set. No-op otherwise. Safe to call on startup."""
    if not use_db():
        return
    eng = get_engine()
    if eng is None:
        return
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # type: ignore
        logger.info("DB tables ensured")
    except Exception as e:
        logger.warning(f"init_db failed: {e}")

def db_latency_ms() -> float | None:
    """Sync helper for /health: returns None when no DB, else ping latency ms (sync fallback)."""
    if not use_db():
        return None
    url = get_database_url() or ""
    if "sqlite" in url:
        return 0.5
    try:
        import psycopg  # type: ignore
        import time
        sync_url = url.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
        start = time.time()
        with psycopg.connect(sync_url, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return round((time.time() - start) * 1000, 2)
    except Exception:
        return None

# --- Sync engine for storage.py (sync functions) ---
_sync_engine = None
_SyncSessionLocal = None

def _sync_normalize_url(url: str) -> str:
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql://", 1)
    return url

def get_sync_engine():
    global _sync_engine
    if _sync_engine is not None:
        return _sync_engine
    if not use_db():
        return None
    url = _sync_normalize_url(get_database_url() or "")  # type: ignore
    try:
        from sqlalchemy import create_engine
        if "sqlite" in url:
            _sync_engine = create_engine(url, echo=False, future=True, connect_args={"check_same_thread": False})
        else:
            _sync_engine = create_engine(url, echo=False, future=True, pool_pre_ping=True)
        return _sync_engine
    except Exception as e:
        logger.warning(f"Failed to create sync engine for {url}: {e}")
        return None

def get_sync_sessionmaker():
    global _SyncSessionLocal
    if _SyncSessionLocal is not None:
        return _SyncSessionLocal
    eng = get_sync_engine()
    if eng is None:
        return None
    try:
        from sqlalchemy.orm import sessionmaker
        _SyncSessionLocal = sessionmaker(eng, expire_on_commit=False)
        return _SyncSessionLocal
    except Exception as e:
        logger.warning(f"Failed to create sync sessionmaker: {e}")
        return None

def init_db_sync():
    """Sync version for storage fallback — creates tables if DATABASE_URL set."""
    if not use_db():
        return
    eng = get_sync_engine()
    if eng is None:
        return
    try:
        Base.metadata.create_all(eng)  # type: ignore
        logger.info("DB tables ensured (sync)")
    except Exception as e:
        logger.warning(f"init_db_sync failed: {e}")

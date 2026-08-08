from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from app.api import datasets, chat
from app.config import settings
from app.core.llm import get_llm_info

# L09 OTEL + Sentry — graceful no-op when env empty
try:
    _otel_ep = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if _otel_ep:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        _provider = TracerProvider()
        _processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=_otel_ep))
        _provider.add_span_processor(_processor)
        trace.set_tracer_provider(_provider)
except Exception as _e:
    pass  # OTEL optional

try:
    _sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
    if _sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.1)
except Exception:
    pass

app = FastAPI(
    title="InsightAgent - AI Data Analyst",
    description="Chat with your CSV/Excel in plain English. Get charts & insights. Supports OpenAI, Groq, Gemini, Claude, Ollama.",
    version=settings.version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# BF-06 concurrency guard + X-Concurrency header (p95 <150ms at 100 users)
import asyncio

_chat_sem = asyncio.Semaphore(20)


@app.middleware("http")
async def _bf06_concurrency(request, call_next):
    # only gate POST /api/chat
    if request.url.path.startswith("/api/chat") and request.method == "POST":
        async with _chat_sem:
            resp = await call_next(request)
            try:
                # available slots = 20 - in_use
                resp.headers["X-Concurrency"] = (
                    str(20 - _chat_sem._value) if hasattr(_chat_sem, "_value") else "20"
                )
                resp.headers["X-Queue"] = "HIT" if resp.headers.get("X-Cache") == "HIT" else "MISS"
            except Exception:
                pass
            return resp
    return await call_next(request)


app.include_router(datasets.router)
app.include_router(chat.router)
try:
    from app.api import dashboards as dashboards_api

    app.include_router(dashboards_api.router)
except Exception as _e:
    import traceback

    print(f"Dashboards router not loaded: {_e}")
    traceback.print_exc()

try:
    from app.api import connectors as connectors_api

    app.include_router(connectors_api.router)
except Exception as _e:
    import traceback

    print(f"Connectors router not loaded: {_e}")
    traceback.print_exc()

try:
    from app.api import schedules as schedules_api

    app.include_router(schedules_api.router)
except Exception as _e:
    import traceback

    print(f"Schedules router not loaded: {_e}")
    traceback.print_exc()
try:
    from app.api import reports as reports_api

    app.include_router(reports_api.router)
except Exception as _e:
    import traceback

    print(f"Reports router not loaded: {_e}")
    traceback.print_exc()
try:
    from app.api import slack as slack_api

    app.include_router(slack_api.router)
except Exception as _e:
    import traceback

    print(f"Slack router not loaded: {_e}")
    traceback.print_exc()

# Optional: try to include llm info route inline
from fastapi import APIRouter

llm_router = APIRouter(prefix="/api/llm", tags=["llm"])


@llm_router.get("/info")
async def llm_info():
    return get_llm_info()


@llm_router.get("/providers")
async def llm_providers():
    info = get_llm_info()
    return {
        "active": info,
        "supported": ["openai", "groq", "gemini", "claude", "ollama", "heuristic"],
        "how_to": {
            "openai": "Set OPENAI_API_KEY and OPENAI_MODEL=gpt-4o-mini",
            "groq": "Set GROQ_API_KEY and GROQ_MODEL=llama-3.1-8b-instant (fast, free tier)",
            "gemini": "Set GOOGLE_API_KEY and GEMINI_MODEL=gemini-1.5-flash",
            "claude": "Set ANTHROPIC_API_KEY and ANTHROPIC_MODEL=claude-3-5-sonnet-20240620",
            "ollama": "Set OLLAMA_URL=http://localhost:11434 and OLLAMA_MODEL=llama3.1:8b, run `ollama serve`",
            "auto": "Set LLM_PROVIDER=auto and provide any key above; first available wins",
        },
    }


app.include_router(llm_router)
try:
    from app.api.auth import router as auth_router

    app.include_router(auth_router)
except Exception as _e:
    import traceback

    print(f"Auth router not loaded: {_e}")
    traceback.print_exc()
try:
    from app.api.audit import router as audit_router

    app.include_router(audit_router)
except Exception as _e:
    import traceback

    print(f"Audit router not loaded: {_e}")
    traceback.print_exc()
try:
    from app.api.jobs import router as jobs_router

    app.include_router(jobs_router)
except Exception as _e:
    import traceback

    print(f"Jobs router not loaded: {_e}")
    traceback.print_exc()
# Cloud routers (always load, they handle CLOUD flag internally)
try:
    from app.api.cloud.auth_cloud import router as cloud_auth_router

    app.include_router(cloud_auth_router)
except Exception as _e:
    print(f"Cloud auth not loaded: {_e}")
try:
    from app.api.cloud.billing import router as cloud_billing_router

    app.include_router(cloud_billing_router)
except Exception as _e:
    print(f"Cloud billing not loaded: {_e}")
try:
    from app.api.cloud.workspaces import router as cloud_ws_router

    app.include_router(cloud_ws_router)
except Exception as _e:
    print(f"Cloud ws not loaded: {_e}")
try:
    from app.api.cloud.llm import router as cloud_llm_router

    app.include_router(cloud_llm_router)
except Exception as _e:
    print(f"Cloud llm not loaded: {_e}")
try:
    from app.api.marketplace import router as marketplace_router

    app.include_router(marketplace_router)
except Exception as _e:
    print(f"Marketplace not loaded: {_e}")
try:
    from app.api.cloud.admin import router as cloud_admin_router

    app.include_router(cloud_admin_router)
except Exception as _e:
    print(f"Cloud admin not loaded: {_e}")


@app.on_event("startup")
async def startup_load_schedules():
    try:
        from app.services.scheduler import load_all_jobs

        load_all_jobs()
        from app.core.auth import seed_admin

        seed_admin()
        # L09 DB init (creates tables if DATABASE_URL set, no-op otherwise)
        try:
            from app.core.db import init_db
            import asyncio

            # init_db is async; schedule without blocking startup
            try:
                asyncio.create_task(init_db())
            except RuntimeError:
                # if no loop, run directly
                import asyncio as _aio

                _aio.run(init_db())
        except Exception:
            pass
        # L09 OTEL FastAPI instrumentation after app created
        try:
            _otel_ep2 = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
            if _otel_ep2:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

                FastAPIInstrumentor.instrument_app(app)
        except Exception:
            pass
    except Exception as e:
        import traceback

        print(f"Scheduler/auth load failed: {e}")
        traceback.print_exc()


@app.get("/")
async def root():
    llm = get_llm_info()
    return {
        "name": settings.app_name,
        "version": settings.version,
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "storage": str(settings.storage_path),
        "openai_configured": bool(settings.openai_api_key),
        "llm": llm,
    }


@app.get("/health")
async def health():
    # L09 add db latency when DATABASE_URL set
    db_ms = None
    db_status = "filesystem"
    try:
        from app.core.db import use_db, db_latency_ms

        if use_db():
            db_status = "db"
            db_ms = db_latency_ms()
            if db_ms is None:
                # fallback simple ping via sync engine
                try:
                    from app.core.db import get_sync_engine
                    import time

                    eng = get_sync_engine()
                    if eng is not None:
                        start = time.time()
                        from sqlalchemy import text

                        with eng.connect() as conn:
                            conn.execute(text("SELECT 1"))
                        db_ms = round((time.time() - start) * 1000, 2)
                except Exception:
                    db_ms = None
    except Exception:
        pass
    payload = {"status": "ok", "version": settings.version, "llm": get_llm_info()}
    if db_status == "db":
        payload["db"] = {"status": "connected", "latency_ms": db_ms}
    else:
        payload["db"] = {"status": "filesystem", "latency_ms": None}
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)

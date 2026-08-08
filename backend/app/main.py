from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import datasets, chat
from app.config import settings

app = FastAPI(
    title="InsightAgent - AI Data Analyst",
    description="Chat with your CSV/Excel in plain English. Get charts & insights.",
    version=settings.version,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(datasets.router)
app.include_router(chat.router)

@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": settings.version,
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "storage": str(settings.storage_path),
        "openai_configured": bool(settings.openai_api_key),
    }

@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.version}

# For running directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)

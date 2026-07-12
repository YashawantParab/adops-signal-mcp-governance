from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.responses import Response

from app.api import agent, auth, campaigns, insights, mcp, recommendations, system
from app.config import get_settings
from app.database import SessionLocal, create_all
from app.observability import configure_logging, request_observability_middleware, security_headers_middleware
from app.services.rag_service import index_knowledge_base

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(security_headers_middleware)
app.middleware("http")(request_observability_middleware)


@app.on_event("startup")
def on_startup() -> None:
    create_all()
    with SessionLocal() as db:
        index_knowledge_base(db)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/ready")
def readiness() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {
        "status": "ready",
        "database": "connected",
        "ai_mode": "llm_rag" if settings.llm_available else "grounded_fallback",
    }


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(auth.router)
app.include_router(campaigns.router)
app.include_router(agent.router)
app.include_router(mcp.router)
app.include_router(recommendations.router)
app.include_router(insights.router)
app.include_router(system.router)

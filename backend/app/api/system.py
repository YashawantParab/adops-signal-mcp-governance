from fastapi import APIRouter

from app.config import get_settings
from app.schemas import SystemStatus

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status", response_model=SystemStatus)
def system_status() -> SystemStatus:
    settings = get_settings()
    return SystemStatus(
        status="operational",
        environment=settings.environment,
        version=settings.app_version,
        ai_mode="llm_rag" if settings.llm_available else "grounded_fallback",
        model=settings.openai_model if settings.llm_available else "deterministic-fallback",
        rag_provider=settings.rag_embedding_provider,
        auth_enabled=settings.auth_enabled,
    )

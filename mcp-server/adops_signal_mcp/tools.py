from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from adops_signal_mcp.bootstrap import configure_backend_runtime

configure_backend_runtime()

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.services.campaign_service import (  # noqa: E402
    campaign_to_read,
    get_campaign_health as compute_campaign_health,
    get_campaign_or_none,
)

logger = logging.getLogger(__name__)

MAX_CAMPAIGN_ID = 2_147_483_647


def _success(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, **data}


def _error(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        payload["error"]["details"] = details
    return payload


def _validate_campaign_id(campaign_id: Any) -> int | dict[str, Any]:
    if isinstance(campaign_id, bool) or not isinstance(campaign_id, int):
        return _error(
            "INVALID_CAMPAIGN_ID",
            "campaign_id must be an integer.",
            {"received_type": type(campaign_id).__name__},
        )
    if campaign_id <= 0:
        return _error(
            "INVALID_CAMPAIGN_ID",
            "campaign_id must be a positive integer.",
            {"received_value": campaign_id},
        )
    if campaign_id > MAX_CAMPAIGN_ID:
        return _error(
            "INVALID_CAMPAIGN_ID",
            "campaign_id is outside the supported integer range.",
            {"max_value": MAX_CAMPAIGN_ID},
        )
    return campaign_id


def ping_adops_signal() -> dict[str, Any]:
    """Return MCP server and database readiness for SignalOps AI."""
    settings = get_settings()
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return _success(
            {
                "service": "SignalOps AI",
                "mcp_server": "signalops-ai-governance",
                "database": {"connected": True},
                "environment": settings.environment,
            }
        )
    except Exception as exc:  # pragma: no cover - depends on local database availability
        logger.exception("MCP ping failed")
        return _error(
            "DATABASE_UNAVAILABLE",
            "SignalOps AI database check failed.",
            {"exception": exc.__class__.__name__},
        )


def get_campaign_health(campaign_id: int) -> dict[str, Any]:
    """Return structured campaign health using the existing backend campaign service."""
    validated_campaign_id = _validate_campaign_id(campaign_id)
    if isinstance(validated_campaign_id, dict):
        return validated_campaign_id

    try:
        with SessionLocal() as db:
            campaign = get_campaign_or_none(db, validated_campaign_id)
            if campaign is None:
                return _error(
                    "CAMPAIGN_NOT_FOUND",
                    "Campaign was not found.",
                    {"campaign_id": validated_campaign_id},
                )

            campaign_read = campaign_to_read(campaign)
            health = compute_campaign_health(db, campaign)
            return _success(
                {
                    "campaign_id": validated_campaign_id,
                    "campaign": campaign_read.model_dump(mode="json"),
                    "health": health.model_dump(mode="json"),
                    "metadata": {
                        "data_source": "SignalOps AI SQLAlchemy database",
                        "service_function": "app.services.campaign_service.get_campaign_health",
                    },
                }
            )
    except Exception as exc:  # pragma: no cover - defensive MCP boundary
        logger.exception("Campaign health lookup failed for campaign_id=%s", validated_campaign_id)
        return _error(
            "CAMPAIGN_HEALTH_FAILED",
            "Campaign health lookup failed.",
            {
                "campaign_id": validated_campaign_id,
                "exception": exc.__class__.__name__,
            },
        )


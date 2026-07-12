from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text

from adops_signal_mcp.bootstrap import REPO_ROOT, configure_backend_runtime

configure_backend_runtime()

from app.config import get_settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Creative, PacingSnapshot, Recommendation, VastValidationError  # noqa: E402
from app.services.campaign_service import (  # noqa: E402
    campaign_to_read,
    get_campaign_health as compute_campaign_health,
    get_campaign_or_none,
)
from app.services.json_fields import parse_list  # noqa: E402
from app.services.recommendation_service import list_recommendations  # noqa: E402
from app.services.vast_service import suggested_fix_for_errors  # noqa: E402

logger = logging.getLogger(__name__)

MAX_CAMPAIGN_ID = 2_147_483_647
MAX_POLICY_QUERY_LENGTH = 200
POLICY_DIR = REPO_ROOT / "docs" / "policies"
POLICY_FILE_GLOB = "*.md"
POLICY_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
BRAND_SENSITIVE_CATEGORIES = {"Finance", "Business News", "News", "Gaming"}


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


def _validate_policy_query(query: Any) -> str | dict[str, Any]:
    if not isinstance(query, str):
        return _error(
            "INVALID_POLICY_QUERY",
            "query must be a string.",
            {"received_type": type(query).__name__},
        )
    cleaned = " ".join(query.strip().split())
    if not cleaned:
        return _error("INVALID_POLICY_QUERY", "query must not be empty.")
    if len(cleaned) > MAX_POLICY_QUERY_LENGTH:
        return _error(
            "INVALID_POLICY_QUERY",
            "query is too long.",
            {"max_length": MAX_POLICY_QUERY_LENGTH},
        )
    return cleaned


def _load_campaign_or_error(db, campaign_id: Any) -> tuple[Any | None, int | None, dict[str, Any] | None]:
    validated_campaign_id = _validate_campaign_id(campaign_id)
    if isinstance(validated_campaign_id, dict):
        return None, None, validated_campaign_id

    campaign = get_campaign_or_none(db, validated_campaign_id)
    if campaign is None:
        return (
            None,
            validated_campaign_id,
            _error(
                "CAMPAIGN_NOT_FOUND",
                "Campaign was not found.",
                {"campaign_id": validated_campaign_id},
            ),
        )
    return campaign, validated_campaign_id, None


def _recommendation_to_json(recommendation: Recommendation) -> dict[str, Any]:
    return {
        "id": recommendation.id,
        "campaign_id": recommendation.campaign_id,
        "title": recommendation.title,
        "description": recommendation.description,
        "expected_impact": recommendation.expected_impact,
        "risk_level": recommendation.risk_level,
        "status": recommendation.status,
        "created_at": recommendation.created_at.isoformat(),
        "decision_reason": recommendation.decision_reason,
        "decided_at": recommendation.decided_at.isoformat() if recommendation.decided_at else None,
        "decided_by_user_id": recommendation.decided_by_user_id,
        "decided_by_name": getattr(recommendation, "decided_by_name", None),
        "decided_by_role": getattr(recommendation, "decided_by_role", None),
    }


def _tokenize(text_value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text_value.lower())
        if len(token) > 2 and token not in POLICY_STOP_WORDS
    ]


def _policy_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _policy_snippet(content: str, tokens: set[str], max_length: int = 360) -> str:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", content)
        if paragraph.strip() and not paragraph.strip().startswith("#")
    ]
    for paragraph in paragraphs:
        lowered = paragraph.lower()
        if any(token in lowered for token in tokens):
            return paragraph[:max_length].strip()
    return (paragraphs[0] if paragraphs else content)[:max_length].strip()


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


def get_campaign_pacing(campaign_id: int) -> dict[str, Any]:
    """Return latest and historical pacing snapshots for one campaign."""
    try:
        with SessionLocal() as db:
            campaign, validated_campaign_id, error = _load_campaign_or_error(db, campaign_id)
            if error:
                return error

            snapshots = list(
                db.execute(
                    select(PacingSnapshot)
                    .where(PacingSnapshot.campaign_id == validated_campaign_id)
                    .order_by(PacingSnapshot.snapshot_date)
                ).scalars()
            )
            if not snapshots:
                return _error(
                    "PACING_DATA_NOT_FOUND",
                    "No pacing snapshots were found for this campaign.",
                    {"campaign_id": validated_campaign_id},
                )

            latest = snapshots[-1]
            prior = snapshots[-2] if len(snapshots) > 1 else None
            delta = round(latest.pacing_percentage - prior.pacing_percentage, 1) if prior else None
            required_remaining = max(campaign.goal_impressions - latest.actual_delivery, 0)
            flight_days_remaining = max((campaign.end_date - latest.snapshot_date).days, 0)
            required_daily_impressions = (
                round(required_remaining / flight_days_remaining) if flight_days_remaining else required_remaining
            )
            history = [
                {
                    "snapshot_date": snapshot.snapshot_date.isoformat(),
                    "expected_delivery": snapshot.expected_delivery,
                    "actual_delivery": snapshot.actual_delivery,
                    "pacing_percentage": round(snapshot.pacing_percentage, 1),
                    "risk_level": snapshot.risk_level,
                }
                for snapshot in snapshots
            ]
            return _success(
                {
                    "campaign_id": validated_campaign_id,
                    "campaign_name": campaign.campaign_name,
                    "latest": history[-1],
                    "trend": {
                        "previous_pacing_percentage": round(prior.pacing_percentage, 1) if prior else None,
                        "delta_percentage_points": delta,
                        "direction": "improving" if delta and delta > 0 else "declining" if delta and delta < 0 else "flat",
                    },
                    "remaining_delivery": {
                        "goal_impressions": campaign.goal_impressions,
                        "remaining_impressions": required_remaining,
                        "flight_days_remaining": flight_days_remaining,
                        "required_daily_impressions": required_daily_impressions,
                    },
                    "history": history,
                    "metadata": {"data_source": "pacing_snapshots"},
                }
            )
    except Exception as exc:  # pragma: no cover - defensive MCP boundary
        logger.exception("Campaign pacing lookup failed for campaign_id=%s", campaign_id)
        return _error(
            "CAMPAIGN_PACING_FAILED",
            "Campaign pacing lookup failed.",
            {"campaign_id": campaign_id, "exception": exc.__class__.__name__},
        )


def get_vast_validation_summary(campaign_id: int) -> dict[str, Any]:
    """Return creative approval and persisted VAST validation error summary."""
    try:
        with SessionLocal() as db:
            _, validated_campaign_id, error = _load_campaign_or_error(db, campaign_id)
            if error:
                return error

            creatives = list(
                db.execute(
                    select(Creative).where(Creative.campaign_id == validated_campaign_id).order_by(Creative.id)
                ).scalars()
            )
            if not creatives:
                return _error(
                    "CREATIVE_DATA_NOT_FOUND",
                    "No creatives were found for this campaign.",
                    {"campaign_id": validated_campaign_id},
                )

            errors = list(
                db.execute(
                    select(VastValidationError)
                    .join(Creative, Creative.id == VastValidationError.creative_id)
                    .where(Creative.campaign_id == validated_campaign_id)
                    .order_by(VastValidationError.detected_at.desc(), VastValidationError.id.desc())
                ).scalars()
            )
            rejected = [creative for creative in creatives if creative.approval_status == "rejected"]
            status_counts = {
                status: sum(1 for creative in creatives if creative.approval_status == status)
                for status in sorted({creative.approval_status for creative in creatives})
            }
            severity_counts = {
                severity: sum(1 for error_item in errors if error_item.severity == severity)
                for severity in sorted({error_item.severity for error_item in errors})
            }
            error_code_counts = {
                code: sum(1 for error_item in errors if error_item.error_code == code)
                for code in sorted({error_item.error_code for error_item in errors})
            }
            return _success(
                {
                    "campaign_id": validated_campaign_id,
                    "valid": not rejected and not errors,
                    "creative_count": len(creatives),
                    "approval_status_counts": status_counts,
                    "rejected_count": len(rejected),
                    "vast_error_count": len(errors),
                    "severity_counts": severity_counts,
                    "error_code_counts": error_code_counts,
                    "rejection_reasons": [
                        creative.rejection_reason for creative in rejected if creative.rejection_reason
                    ],
                    "latest_errors": [
                        {
                            "id": error_item.id,
                            "creative_id": error_item.creative_id,
                            "error_code": error_item.error_code,
                            "error_message": error_item.error_message,
                            "severity": error_item.severity,
                            "detected_at": error_item.detected_at.isoformat(),
                        }
                        for error_item in errors[:10]
                    ],
                    "suggested_fix": suggested_fix_for_errors(
                        errors, "rejected" if rejected else "approved"
                    ),
                    "metadata": {"data_source": "creatives,vast_validation_errors"},
                }
            )
    except Exception as exc:  # pragma: no cover - defensive MCP boundary
        logger.exception("VAST validation summary failed for campaign_id=%s", campaign_id)
        return _error(
            "VAST_VALIDATION_SUMMARY_FAILED",
            "VAST validation summary failed.",
            {"campaign_id": campaign_id, "exception": exc.__class__.__name__},
        )


def get_brand_safety_findings(campaign_id: int) -> dict[str, Any]:
    """Return deterministic brand-safety governance findings from existing campaign data."""
    try:
        with SessionLocal() as db:
            campaign, validated_campaign_id, error = _load_campaign_or_error(db, campaign_id)
            if error:
                return error

            findings: list[dict[str, Any]] = []
            categories = parse_list(campaign.target_content_categories)
            sensitive_categories = sorted(set(categories) & BRAND_SENSITIVE_CATEGORIES)
            if sensitive_categories:
                findings.append(
                    {
                        "type": "sensitive_content_category",
                        "severity": "medium",
                        "message": "Campaign targets content categories that require brand-suitability review.",
                        "evidence": {"target_content_categories": sensitive_categories},
                    }
                )

            if campaign.advertiser and campaign.advertiser.industry in {"Finance", "Gaming"}:
                findings.append(
                    {
                        "type": "regulated_or_sensitive_advertiser_vertical",
                        "severity": "medium",
                        "message": "Advertiser industry requires conservative placement and claims review controls.",
                        "evidence": {
                            "advertiser_name": campaign.advertiser.name,
                            "industry": campaign.advertiser.industry,
                        },
                    }
                )

            rejected_count = db.scalar(
                select(func.count(Creative.id)).where(
                    Creative.campaign_id == validated_campaign_id,
                    Creative.approval_status == "rejected",
                )
            ) or 0
            if rejected_count:
                findings.append(
                    {
                        "type": "creative_approval_block",
                        "severity": "high",
                        "message": "Rejected creative must not serve until corrected and revalidated.",
                        "evidence": {"rejected_creative_count": int(rejected_count)},
                    }
                )

            vast_error_count = db.scalar(
                select(func.count(VastValidationError.id))
                .join(Creative, Creative.id == VastValidationError.creative_id)
                .where(Creative.campaign_id == validated_campaign_id)
            ) or 0
            if vast_error_count:
                findings.append(
                    {
                        "type": "creative_quality_governance",
                        "severity": "medium",
                        "message": "Persisted VAST errors should be reviewed before scaling delivery.",
                        "evidence": {"vast_error_count": int(vast_error_count)},
                    }
                )

            recommendations = list_recommendations(db, validated_campaign_id)
            policy_relevant_recommendations = [
                recommendation
                for recommendation in recommendations
                if "brand" in recommendation.description.lower() or "suitability" in recommendation.description.lower()
            ]
            for recommendation in policy_relevant_recommendations:
                findings.append(
                    {
                        "type": "recommendation_policy_reference",
                        "severity": "low",
                        "message": "Existing recommendation explicitly references brand-safety or brand-suitability controls.",
                        "evidence": {
                            "recommendation_id": recommendation.id,
                            "title": recommendation.title,
                            "status": recommendation.status,
                        },
                    }
                )

            if not findings:
                return _error(
                    "NO_BRAND_SAFETY_FINDINGS",
                    "No brand-safety findings were identified from current campaign data.",
                    {"campaign_id": validated_campaign_id},
                )

            return _success(
                {
                    "campaign_id": validated_campaign_id,
                    "campaign_name": campaign.campaign_name,
                    "findings": findings,
                    "finding_count": len(findings),
                    "read_only": True,
                    "metadata": {
                        "data_source": "campaigns,advertisers,creatives,vast_validation_errors,recommendations",
                        "method": "deterministic rules over existing campaign data",
                    },
                }
            )
    except Exception as exc:  # pragma: no cover - defensive MCP boundary
        logger.exception("Brand safety findings failed for campaign_id=%s", campaign_id)
        return _error(
            "BRAND_SAFETY_FINDINGS_FAILED",
            "Brand safety findings lookup failed.",
            {"campaign_id": campaign_id, "exception": exc.__class__.__name__},
        )


def get_recommendation_history(campaign_id: int) -> dict[str, Any]:
    """Return recommendation history and human decision metadata for one campaign."""
    try:
        with SessionLocal() as db:
            campaign, validated_campaign_id, error = _load_campaign_or_error(db, campaign_id)
            if error:
                return error

            recommendations = list_recommendations(db, validated_campaign_id)
            if not recommendations:
                return _error(
                    "RECOMMENDATION_HISTORY_NOT_FOUND",
                    "No recommendation history was found for this campaign.",
                    {"campaign_id": validated_campaign_id},
                )

            status_counts = {
                status: sum(1 for recommendation in recommendations if recommendation.status == status)
                for status in sorted({recommendation.status for recommendation in recommendations})
            }
            return _success(
                {
                    "campaign_id": validated_campaign_id,
                    "campaign_name": campaign.campaign_name,
                    "recommendation_count": len(recommendations),
                    "status_counts": status_counts,
                    "recommendations": [_recommendation_to_json(item) for item in recommendations],
                    "read_only": True,
                    "metadata": {"data_source": "recommendations,users"},
                }
            )
    except Exception as exc:  # pragma: no cover - defensive MCP boundary
        logger.exception("Recommendation history failed for campaign_id=%s", campaign_id)
        return _error(
            "RECOMMENDATION_HISTORY_FAILED",
            "Recommendation history lookup failed.",
            {"campaign_id": campaign_id, "exception": exc.__class__.__name__},
        )


def search_policy_context(query: str) -> dict[str, Any]:
    """Search local policy markdown with simple keyword scoring."""
    validated_query = _validate_policy_query(query)
    if isinstance(validated_query, dict):
        return validated_query

    try:
        policy_files = sorted(Path(POLICY_DIR).glob(POLICY_FILE_GLOB))
        if not policy_files:
            return _error(
                "POLICY_CONTEXT_UNAVAILABLE",
                "No local policy markdown files were found.",
                {"policy_dir": str(POLICY_DIR)},
            )

        query_tokens = set(_tokenize(validated_query))
        if not query_tokens:
            return _error(
                "INVALID_POLICY_QUERY",
                "query must include at least one searchable keyword.",
            )

        matches: list[dict[str, Any]] = []
        for path in policy_files:
            content = path.read_text(encoding="utf-8")
            content_tokens = _tokenize(content)
            score = sum(1 for token in content_tokens if token in query_tokens)
            title = _policy_title(content, path.stem)
            title_score = sum(3 for token in query_tokens if token in title.lower())
            total_score = score + title_score
            if total_score <= 0:
                continue
            matches.append(
                {
                    "source": str(path.relative_to(REPO_ROOT)),
                    "title": title,
                    "score": total_score,
                    "matched_keywords": sorted(token for token in query_tokens if token in content.lower()),
                    "snippet": _policy_snippet(content, query_tokens),
                }
            )

        matches.sort(key=lambda item: (-item["score"], item["source"]))
        if not matches:
            return _error(
                "POLICY_CONTEXT_NOT_FOUND",
                "No policy context matched the query.",
                {"query": validated_query},
            )

        return _success(
            {
                "query": validated_query,
                "matches": matches[:5],
                "match_count": len(matches),
                "retrieval": {
                    "method": "keyword",
                    "policy_dir": str(POLICY_DIR.relative_to(REPO_ROOT)),
                    "vector_db_used": False,
                    "llm_used": False,
                },
            }
        )
    except Exception as exc:  # pragma: no cover - defensive MCP boundary
        logger.exception("Policy context search failed for query=%s", validated_query)
        return _error(
            "POLICY_CONTEXT_SEARCH_FAILED",
            "Policy context search failed.",
            {"exception": exc.__class__.__name__},
        )

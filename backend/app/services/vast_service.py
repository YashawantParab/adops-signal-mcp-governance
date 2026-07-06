from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Creative, VastValidationError
from app.schemas import VastValidationResponse
from app.time_utils import utc_now


def suggested_fix_for_errors(errors: list[VastValidationError], approval_status: str) -> str:
    codes = {error.error_code for error in errors}
    if approval_status == "rejected":
        return "Request a revised creative package with the missing companion asset and resubmit for approval."
    if "VAST_TIMEOUT" in codes:
        return "Ask the advertiser to shorten redirect chains and use faster media file hosting for the VAST tag."
    if "MEDIAFILE_MISSING" in codes:
        return "Confirm the VAST response includes at least one playable MP4 media file for CTV devices."
    if errors:
        return "Review the VAST response with the creative vendor and revalidate before scaling delivery."
    return "No blocking VAST issues detected. Continue monitoring validation freshness."


def validate_vast(db: Session, creative_id: Optional[int], vast_url: Optional[str]) -> VastValidationResponse:
    creative = db.get(Creative, creative_id) if creative_id else None
    errors: list[VastValidationError] = []

    if creative:
        errors = list(
            db.execute(
                select(VastValidationError)
                .where(VastValidationError.creative_id == creative.id)
                .order_by(VastValidationError.detected_at.desc())
            ).scalars()
        )
        approval_status = creative.approval_status
    else:
        approval_status = "approved"
        if vast_url and ("timeout" in vast_url.lower() or "slow" in vast_url.lower()):
            synthetic = VastValidationError(
                id=0,
                creative_id=0,
                error_code="VAST_TIMEOUT",
                error_message="Synthetic validation timed out after 3 seconds.",
                severity="high",
                detected_at=utc_now(),
            )
            errors = [synthetic]
            approval_status = "needs_review"

    return VastValidationResponse(
        valid=approval_status == "approved" and not errors,
        creative_id=creative.id if creative else None,
        approval_status=approval_status,
        errors=errors,
        suggested_fix=suggested_fix_for_errors(errors, approval_status),
    )

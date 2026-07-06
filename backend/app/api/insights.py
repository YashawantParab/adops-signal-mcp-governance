from fastapi import APIRouter, Depends

from app.models import User
from app.schemas import RoiAssumptions, RoiEstimate
from app.security import get_current_user

router = APIRouter(prefix="/api/insights", tags=["business impact"])


@router.post("/roi", response_model=RoiEstimate)
def estimate_roi(
    assumptions: RoiAssumptions,
    _: User = Depends(get_current_user),
) -> RoiEstimate:
    incidents = assumptions.campaigns_per_month * assumptions.incident_rate
    minutes_saved = max(
        assumptions.minutes_per_incident_before - assumptions.minutes_per_incident_after,
        0,
    )
    hours_saved = incidents * minutes_saved / 60
    labor_savings = hours_saved * assumptions.loaded_hourly_cost_eur
    revenue_at_risk = (
        incidents
        * assumptions.average_campaign_value_eur
        * assumptions.revenue_at_risk_rate
    )
    revenue_protected = revenue_at_risk * assumptions.recovery_rate
    total = labor_savings + revenue_protected
    return RoiEstimate(
        incidents_per_month=round(incidents, 1),
        hours_saved_per_month=round(hours_saved, 1),
        labor_savings_eur=round(labor_savings, 2),
        revenue_protected_eur=round(revenue_protected, 2),
        total_monthly_value_eur=round(total, 2),
        annualized_value_eur=round(total * 12, 2),
        assumptions=assumptions,
    )

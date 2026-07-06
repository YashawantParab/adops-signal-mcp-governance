from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AdvertiserRead(BaseModel):
    id: int
    name: str
    industry: str
    region: str

    model_config = ConfigDict(from_attributes=True)


class PublisherRead(BaseModel):
    id: int
    name: str
    country: str
    inventory_type: str
    device_types: list[str]


class CampaignRead(BaseModel):
    id: int
    advertiser_id: int
    advertiser_name: Optional[str] = None
    campaign_name: str
    campaign_type: str
    start_date: date
    end_date: date
    goal_impressions: int
    delivered_impressions: int
    budget: float
    status: str
    target_countries: list[str]
    target_devices: list[str]
    target_content_categories: list[str]
    frequency_cap: int
    bid_floor: float
    priority_level: str


class CampaignSummary(CampaignRead):
    pacing_percentage: float
    risk_level: str
    main_issue: str
    creative_status: str


class CreativeRead(BaseModel):
    id: int
    campaign_id: int
    creative_name: str
    format: str
    duration_seconds: int
    vast_url: str
    approval_status: str
    rejection_reason: Optional[str]
    last_validated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VastErrorRead(BaseModel):
    id: int
    creative_id: int
    error_code: str
    error_message: str
    severity: str
    detected_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InventorySummary(BaseModel):
    eligible_segments: int
    eligible_daily_impressions: int
    total_daily_impressions: int
    eligible_inventory_percentage: float
    constrained_dimensions: list[str]


class BidSummary(BaseModel):
    total_bids: int
    win_rate: float
    below_floor_rate: float
    avg_bid_price: float
    avg_floor_price: float


class CampaignHealth(BaseModel):
    campaign_id: int
    pacing_percentage: float
    expected_delivery: int
    actual_delivery: int
    risk_level: str
    creative_status: str
    vast_error_count: int
    inventory: InventorySummary
    bid_analysis: BidSummary
    main_suspected_issue: str


class CampaignDetail(CampaignRead):
    health: CampaignHealth
    creatives: list[CreativeRead]
    vast_errors: list[VastErrorRead]
    pacing_history: list[dict[str, Any]]


class EvidenceItem(BaseModel):
    id: Optional[str] = None
    source: str
    message: str
    metric: Optional[str] = None
    retrieved_at: Optional[datetime] = None


class RootCause(BaseModel):
    cause: str
    impact: str
    evidence: str
    evidence_ids: list[str] = []


class RecommendationRead(BaseModel):
    id: int
    campaign_id: int
    title: str
    description: str
    expected_impact: str
    risk_level: str
    status: str
    created_at: datetime
    decision_reason: Optional[str] = None
    decided_at: Optional[datetime] = None
    decided_by_user_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class RecommendationDecisionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AgentDiagnoseRequest(BaseModel):
    campaign_id: int
    query: str = Field(min_length=4, max_length=500)


class AgentDiagnoseResponse(BaseModel):
    campaign_id: int
    diagnosis: str
    root_causes: list[RootCause]
    tools_called: list[str]
    evidence: list[EvidenceItem]
    recommendations: list[RecommendationRead]
    confidence_score: float
    human_approval_required: bool
    query_intent: str = "comprehensive"
    execution_mode: str = "fallback"
    model_name: str = "deterministic-fallback"
    prompt_version: str = "adops-diagnosis-v1"
    latency_ms: int = 0
    retrieved_documents: list[str] = []


class VastValidationRequest(BaseModel):
    creative_id: Optional[int] = None
    vast_url: Optional[str] = None


class VastValidationResponse(BaseModel):
    valid: bool
    creative_id: Optional[int] = None
    approval_status: str
    errors: list[VastErrorRead]
    suggested_fix: str


class ClientSummaryRequest(BaseModel):
    campaign_id: int
    diagnosis: Optional[str] = None


class ClientSummaryResponse(BaseModel):
    campaign_id: int
    summary: str
    omitted_internal_details: list[str]


class AuditLogRead(BaseModel):
    id: int
    campaign_id: int
    user_query: str
    tools_called: list[str]
    evidence: list[EvidenceItem]
    diagnosis: str
    confidence_score: float
    query_intent: str = "comprehensive"
    execution_mode: str = "fallback"
    model_name: str = "deterministic-fallback"
    latency_ms: int = 0
    request_id: Optional[str] = None
    created_at: datetime


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    id: int
    email: str
    full_name: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class SystemStatus(BaseModel):
    status: str
    environment: str
    version: str
    ai_mode: str
    model: str
    rag_provider: str
    auth_enabled: bool


class RoiAssumptions(BaseModel):
    campaigns_per_month: int = Field(default=250, ge=1, le=100_000)
    incident_rate: float = Field(default=0.18, ge=0, le=1)
    minutes_per_incident_before: int = Field(default=75, ge=1, le=1440)
    minutes_per_incident_after: int = Field(default=18, ge=1, le=1440)
    loaded_hourly_cost_eur: float = Field(default=58, ge=1, le=1000)
    average_campaign_value_eur: float = Field(default=18_000, ge=0, le=10_000_000)
    revenue_at_risk_rate: float = Field(default=0.08, ge=0, le=1)
    recovery_rate: float = Field(default=0.25, ge=0, le=1)


class RoiEstimate(BaseModel):
    incidents_per_month: float
    hours_saved_per_month: float
    labor_savings_eur: float
    revenue_protected_eur: float
    total_monthly_value_eur: float
    annualized_value_eur: float
    assumptions: RoiAssumptions

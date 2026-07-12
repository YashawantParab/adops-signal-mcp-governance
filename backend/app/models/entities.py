from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.database import Base
from app.time_utils import utc_now


class Advertiser(Base):
    __tablename__ = "advertisers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    industry: Mapped[str] = mapped_column(String(80), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False)

    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="advertiser")


class Publisher(Base):
    __tablename__ = "publishers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    inventory_type: Mapped[str] = mapped_column(String(80), nullable=False)
    device_types: Mapped[str] = mapped_column(Text, nullable=False)

    segments: Mapped[list["InventorySegment"]] = relationship(back_populates="publisher")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    advertiser_id: Mapped[int] = mapped_column(ForeignKey("advertisers.id"), nullable=False)
    campaign_name: Mapped[str] = mapped_column(String(180), nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(80), nullable=False)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    goal_impressions: Mapped[int] = mapped_column(Integer, nullable=False)
    delivered_impressions: Mapped[int] = mapped_column(Integer, nullable=False)
    budget: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    target_countries: Mapped[str] = mapped_column(Text, nullable=False)
    target_devices: Mapped[str] = mapped_column(Text, nullable=False)
    target_content_categories: Mapped[str] = mapped_column(Text, nullable=False)
    frequency_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    bid_floor: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    priority_level: Mapped[str] = mapped_column(String(40), nullable=False)

    advertiser: Mapped[Advertiser] = relationship(back_populates="campaigns")
    creatives: Mapped[list["Creative"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class InventorySegment(Base):
    __tablename__ = "inventory_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publisher_id: Mapped[int] = mapped_column(ForeignKey("publishers.id"), nullable=False)
    segment_name: Mapped[str] = mapped_column(String(160), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    device_type: Mapped[str] = mapped_column(String(40), nullable=False)
    content_category: Mapped[str] = mapped_column(String(80), nullable=False)
    avg_daily_available_impressions: Mapped[int] = mapped_column(Integer, nullable=False)
    floor_price: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)

    publisher: Mapped[Publisher] = relationship(back_populates="segments")


class Creative(Base):
    __tablename__ = "creatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    creative_name: Mapped[str] = mapped_column(String(160), nullable=False)
    format: Mapped[str] = mapped_column(String(40), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    vast_url: Mapped[str] = mapped_column(Text, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(40), nullable=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    last_validated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    campaign: Mapped[Campaign] = relationship(back_populates="creatives")
    validation_errors: Mapped[list["VastValidationError"]] = relationship(back_populates="creative", cascade="all, delete-orphan")


class VastValidationError(Base):
    __tablename__ = "vast_validation_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creative_id: Mapped[int] = mapped_column(ForeignKey("creatives.id"), nullable=False)
    error_code: Mapped[str] = mapped_column(String(40), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    creative: Mapped[Creative] = relationship(back_populates="validation_errors")


class AdRequest(Base):
    __tablename__ = "ad_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    publisher_id: Mapped[int] = mapped_column(ForeignKey("publishers.id"), nullable=False)
    inventory_segment_id: Mapped[int] = mapped_column(ForeignKey("inventory_segments.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    device_type: Mapped[str] = mapped_column(String(40), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    content_category: Mapped[str] = mapped_column(String(80), nullable=False)
    request_status: Mapped[str] = mapped_column(String(40), nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)


class Impression(Base):
    __tablename__ = "impressions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    publisher_id: Mapped[int] = mapped_column(ForeignKey("publishers.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    device_type: Mapped[str] = mapped_column(String(40), nullable=False)
    country: Mapped[str] = mapped_column(String(8), nullable=False)
    content_category: Mapped[str] = mapped_column(String(80), nullable=False)
    revenue: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)


class BidResponse(Base):
    __tablename__ = "bid_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    ad_request_id: Mapped[int] = mapped_column(ForeignKey("ad_requests.id"), nullable=False)
    bid_price: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    floor_price: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    won: Mapped[bool] = mapped_column(Boolean, nullable=False)
    loss_reason: Mapped[Optional[str]] = mapped_column(Text)


class PacingSnapshot(Base):
    __tablename__ = "pacing_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    snapshot_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    expected_delivery: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_delivery: Mapped[int] = mapped_column(Integer, nullable=False)
    pacing_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_impact: Mapped[str] = mapped_column(String(40), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    decided_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    campaign: Mapped[Campaign] = relationship(back_populates="recommendations")


class AgentAuditLog(Base):
    __tablename__ = "agent_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    tools_called: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    query_intent: Mapped[str] = mapped_column(String(60), nullable=False, default="comprehensive")
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="deterministic-fallback")
    execution_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="fallback")
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False, default="adops-diagnosis-v1")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_id: Mapped[Optional[str]] = mapped_column(String(80))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    campaign: Mapped[Campaign] = relationship()
    tool_calls: Mapped[list["MCPToolCall"]] = relationship(back_populates="agent_run", cascade="all, delete-orphan")
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )
    policy_checks: Mapped[list["PolicyCheck"]] = relationship(back_populates="agent_run", cascade="all, delete-orphan")
    blocked_actions: Mapped[list["BlockedAction"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )


class MCPToolCall(Base):
    __tablename__ = "mcp_tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    agent_run: Mapped[AgentRun] = relationship(back_populates="tool_calls")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False)
    proposed_action: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    reviewer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    agent_run: Mapped[AgentRun] = relationship(back_populates="approval_requests")
    campaign: Mapped[Campaign] = relationship()
    reviewer: Mapped[Optional["User"]] = relationship()


class PolicyCheck(Base):
    __tablename__ = "policy_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    policy_name: Mapped[str] = mapped_column(String(160), nullable=False)
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    matched_rules: Mapped[list] = mapped_column(JSON, nullable=False)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    agent_run: Mapped[AgentRun] = relationship(back_populates="policy_checks")


class BlockedAction(Base):
    __tablename__ = "blocked_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    agent_run: Mapped[AgentRun] = relationship(back_populates="blocked_actions")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(1536).with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    embedding_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

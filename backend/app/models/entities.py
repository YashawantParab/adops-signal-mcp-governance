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

    # Governed MCP agent observability (Phase 1). execution_mode is always
    # set; the rest are populated only for execution_mode="llm_mcp_agent" and
    # stay NULL for "deterministic_fallback" runs - never fabricated.
    execution_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="deterministic_fallback")
    llm_provider: Mapped[Optional[str]] = mapped_column(String(40))
    model_name: Mapped[Optional[str]] = mapped_column(String(120))
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Float)
    steps_used: Mapped[Optional[int]] = mapped_column(Integer)
    max_steps: Mapped[Optional[int]] = mapped_column(Integer)
    fallback_reason: Mapped[Optional[str]] = mapped_column(String(80))

    # Client-safe brief (Phase 2): populated only for execution_mode="llm_mcp_agent"
    # runs, where the finish call also produces a client-facing brief that the
    # client_safe_brief gate then classifies before it is considered releasable.
    client_safe_brief: Mapped[Optional[str]] = mapped_column(Text)
    client_safe_brief_status: Mapped[Optional[str]] = mapped_column(String(40))  # safe | needs_review | block

    campaign: Mapped[Campaign] = relationship()
    tool_calls: Mapped[list["MCPToolCall"]] = relationship(back_populates="agent_run", cascade="all, delete-orphan")
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )
    policy_checks: Mapped[list["PolicyCheck"]] = relationship(back_populates="agent_run", cascade="all, delete-orphan")
    blocked_actions: Mapped[list["BlockedAction"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )
    gate_decisions: Mapped[list["GateDecision"]] = relationship(
        back_populates="agent_run", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["RunFeedback"]] = relationship(back_populates="agent_run", cascade="all, delete-orphan")


class MCPToolCall(Base):
    __tablename__ = "mcp_tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    input_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_category: Mapped[Optional[str]] = mapped_column(String(80))
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


class GateDecision(Base):
    __tablename__ = "gate_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), nullable=False, index=True)
    campaign_id: Mapped[Optional[int]] = mapped_column(ForeignKey("campaigns.id"))
    decision_point: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    gate_type: Mapped[str] = mapped_column(String(20), nullable=False)  # jev | llm | rules
    provider: Mapped[Optional[str]] = mapped_column(String(40))
    model_name: Mapped[Optional[str]] = mapped_column(String(120))
    decision: Mapped[str] = mapped_column(String(80), nullable=False)
    probability: Mapped[Optional[float]] = mapped_column(Float)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    rule_floor: Mapped[Optional[str]] = mapped_column(String(40))
    final_decision: Mapped[str] = mapped_column(String(80), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Float)
    input_reference: Mapped[Optional[str]] = mapped_column(String(120))  # short hash/tag, never a raw prompt
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False, default="gate-decision-v1")
    # The gate type the configured chain was asked for first (may differ from
    # gate_type/provider above if it was unavailable/failed and the chain fell
    # through - see app.gates.decide_with_fallback).
    requested_provider: Mapped[Optional[str]] = mapped_column(String(20))
    # Human-readable summary of why any earlier gate(s) were skipped, e.g.
    # "jev: TYPESAFE_API_KEY is not configured". NULL when the requested
    # provider answered directly with no fallback.
    fallback_reason: Mapped[Optional[str]] = mapped_column(Text)
    # e.g. "jev_executed", "jev_unavailable_fallback_llm", "jev_failed_fallback_rules".
    execution_status: Mapped[str] = mapped_column(String(80), nullable=False, default="executed")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    agent_run: Mapped[AgentRun] = relationship(back_populates="gate_decisions")
    campaign: Mapped[Optional[Campaign]] = relationship()


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


class ProposedAction(Base):
    """A proposed synthetic ad-server change (Phase 3). Lifecycle: proposed ->
    pending_approval -> approved -> executed -> verified, or blocked / failed /
    rolled_back. Approval is delegated to the existing ApprovalRequest table
    (one unified approval queue for both diagnosis and action-execution
    approvals) rather than a second parallel approval mechanism."""

    __tablename__ = "proposed_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    agent_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("agent_runs.id"))
    approval_request_id: Mapped[Optional[int]] = mapped_column(ForeignKey("approval_requests.id"))
    action_type: Mapped[str] = mapped_column(String(60), nullable=False)
    requested_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    risk_class: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="proposed")
    proposed_by: Mapped[str] = mapped_column(String(80), nullable=False)  # "agent" or a user identifier
    state_version: Mapped[Optional[str]] = mapped_column(String(64))  # hash of before_state+params at approval time
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    campaign: Mapped[Campaign] = relationship()
    approval_request: Mapped[Optional["ApprovalRequest"]] = relationship()
    executions: Mapped[list["ActionExecution"]] = relationship(back_populates="proposed_action", cascade="all, delete-orphan")


class ActionExecution(Base):
    __tablename__ = "action_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposed_action_id: Mapped[int] = mapped_column(ForeignKey("proposed_actions.id"), nullable=False, index=True)
    executed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    before_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    after_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)  # executed | failed
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    proposed_action: Mapped[ProposedAction] = relationship(back_populates="executions")
    executor: Mapped["User"] = relationship()
    verifications: Mapped[list["ActionVerification"]] = relationship(back_populates="action_execution", cascade="all, delete-orphan")
    rollbacks: Mapped[list["ActionRollback"]] = relationship(back_populates="action_execution", cascade="all, delete-orphan")


class ActionVerification(Base):
    __tablename__ = "action_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_execution_id: Mapped[int] = mapped_column(ForeignKey("action_executions.id"), nullable=False, index=True)
    expected_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    actual_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False)  # verified | mismatch
    mismatch_reason: Mapped[Optional[str]] = mapped_column(Text)
    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    action_execution: Mapped[ActionExecution] = relationship(back_populates="verifications")


class ActionRollback(Base):
    __tablename__ = "action_rollbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_execution_id: Mapped[int] = mapped_column(ForeignKey("action_executions.id"), nullable=False, index=True)
    rolled_back_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    restored_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    actual_state_after: Mapped[dict] = mapped_column(JSON, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(40), nullable=False)  # verified | mismatch
    rolled_back_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    action_execution: Mapped[ActionExecution] = relationship(back_populates="rollbacks")
    actor: Mapped["User"] = relationship()


class RunFeedback(Base):
    """Thumbs up/down + optional comment on a completed agent run (Phase 3H).
    Authenticated, non-demo users only - see app/api/mcp.py role gating."""

    __tablename__ = "run_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    rating: Mapped[str] = mapped_column(String(10), nullable=False)  # "up" | "down"
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

    agent_run: Mapped[AgentRun] = relationship(back_populates="feedback")
    user: Mapped["User"] = relationship()


class MCPAccessToken(Base):
    """A scoped bearer token for the hosted, external, read-only MCP endpoint
    (Phase 3F). Only a salted hash is ever stored - the raw token is shown
    once, at creation, and never again."""

    __tablename__ = "mcp_access_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(40), nullable=False, default="read")
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class ExternalMCPCall(Base):
    """Audit row for every request the hosted external MCP endpoint receives -
    written before the request is forwarded, exactly like the internal
    governance_wrapper's mcp_tool_calls pattern (Phase 1)."""

    __tablename__ = "external_mcp_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[Optional[int]] = mapped_column(ForeignKey("mcp_access_tokens.id"), index=True)
    method: Mapped[str] = mapped_column(String(80), nullable=False)  # JSON-RPC method, e.g. "tools/call"
    tool_name: Mapped[Optional[str]] = mapped_column(String(120))
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    client_host: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.agent import tools
from app.agent.llm_reasoner import LLMReasoner, PROMPT_VERSION
from app.models import AgentAuditLog, Campaign
from app.observability import AGENT_LATENCY, AGENT_RUNS
from app.schemas import AgentDiagnoseResponse, EvidenceItem, RecommendationRead, RootCause
from app.services.recommendation_service import create_recommendation
from app.time_utils import utc_now

logger = logging.getLogger(__name__)


@dataclass
class RankedCause:
    cause: str
    impact: str
    score: int
    evidence: str
    recommendation_title: str
    recommendation_description: str
    expected_impact: str
    risk_level: str = "Medium"
    evidence_ids: list[str] = field(default_factory=list)


class AdOpsSignalAgent:
    """Evidence-grounded LLM agent with a deterministic availability fallback."""

    @staticmethod
    def _classify_query(query: str) -> str:
        normalized = " ".join(query.lower().split())
        intent_terms = [
            ("client_communication", ("client", "customer", "external explanation", "safe summary")),
            ("goal_feasibility", ("hit its goal", "hit the goal", "on time", "by friday", "by monday", "attain", "feasible")),
            ("creative_vast", ("vast", "creative", "media file", "companion", "timeout", "tracking uri")),
            ("bid_competitiveness", ("bid", "floor", "auction", "win rate", "cpm")),
            ("frequency_cap", ("frequency", "repeat reach", "cap restricting")),
            ("launch_timing", ("start late", "started late", "launch delay", "launch late")),
            ("portfolio_pressure", ("shared inventory", "consuming inventory", "other campaigns")),
            ("targeting_inventory", ("targeting", "eligible inventory", "country", "device mismatch", "category", "inventory expansion")),
            ("next_action", ("what action", "next action", "what should", "recommend next", "do next")),
        ]
        return next((intent for intent, terms in intent_terms if any(term in normalized for term in terms)), "comprehensive")

    @staticmethod
    def _collect_tool_results(db: Session, campaign: Campaign, query: str, intent: str):
        builders = {
            "pacing": lambda: tools.check_pacing(db, campaign),
            "setup": lambda: tools.check_frequency_and_dates(db, campaign),
            "targeting": lambda: tools.analyze_targeting(db, campaign),
            "inventory": lambda: tools.check_inventory(db, campaign),
            "portfolio": lambda: tools.check_portfolio_pressure(db, campaign),
            "creative": lambda: tools.validate_creatives(db, campaign),
            "bids": lambda: tools.analyze_bids(db, campaign),
            "goal": lambda: tools.forecast_goal_attainment(db, campaign, query),
            "docs": lambda: tools.retrieve_docs(db, query),
        }
        plans = {
            "comprehensive": ["pacing", "setup", "targeting", "inventory", "portfolio", "creative", "bids", "goal", "docs"],
            "targeting_inventory": ["pacing", "targeting", "inventory", "portfolio", "goal", "docs"],
            "creative_vast": ["pacing", "creative", "goal", "docs"],
            "bid_competitiveness": ["pacing", "inventory", "bids", "goal", "docs"],
            "frequency_cap": ["pacing", "setup", "inventory", "goal", "docs"],
            "launch_timing": ["pacing", "setup", "goal", "docs"],
            "portfolio_pressure": ["pacing", "inventory", "portfolio", "bids", "goal", "docs"],
            "goal_feasibility": ["pacing", "setup", "targeting", "inventory", "creative", "bids", "goal", "docs"],
            "client_communication": ["pacing", "targeting", "creative", "goal", "docs"],
            "next_action": ["pacing", "setup", "targeting", "inventory", "portfolio", "creative", "bids", "goal", "docs"],
        }
        return [builders[name]() for name in plans[intent]]

    def diagnose(
        self,
        db: Session,
        campaign: Campaign,
        query: str,
        *,
        user_id: int | None = None,
        request_id: str | None = None,
    ) -> AgentDiagnoseResponse:
        started = time.perf_counter()
        query_intent = self._classify_query(query)
        tool_results = self._collect_tool_results(db, campaign, query, query_intent)
        raw_evidence = [item for result in tool_results for item in result.evidence]
        evidence = [
            item.model_copy(update={"id": f"E{index}"})
            for index, item in enumerate(raw_evidence, start=1)
        ]
        payload = {result.name: result.payload for result in tool_results}
        reasoner = LLMReasoner()
        execution_mode = "fallback"
        model_name = "deterministic-fallback"
        input_tokens = 0
        output_tokens = 0
        human_approval_required = False
        try:
            model_run = reasoner.diagnose(
                campaign_context={
                    "id": campaign.id,
                    "name": campaign.campaign_name,
                    "start_date": campaign.start_date,
                    "end_date": campaign.end_date,
                    "goal_impressions": campaign.goal_impressions,
                    "delivered_impressions": campaign.delivered_impressions,
                    "target_countries": campaign.target_countries,
                    "target_devices": campaign.target_devices,
                    "target_content_categories": campaign.target_content_categories,
                    "frequency_cap": campaign.frequency_cap,
                    "priority_level": campaign.priority_level,
                },
                query=query,
                evidence=[item.model_dump(mode="json") for item in evidence],
                retrieved_documents=payload["rag_documentation_lookup"]["docs"],
            )
            evidence_map = {item.id: item for item in evidence if item.id}
            causes = []
            for cause in model_run.output.root_causes:
                valid_ids = [evidence_id for evidence_id in cause.evidence_ids if evidence_id in evidence_map]
                if not valid_ids:
                    continue
                evidence_text = " ".join(evidence_map[evidence_id].message for evidence_id in valid_ids)
                causes.append(
                    RankedCause(
                        cause=cause.cause,
                        impact=cause.impact,
                        score={"High": 90, "Medium": 60, "Low": 30}[cause.impact],
                        evidence=evidence_text,
                        recommendation_title=cause.recommendation_title,
                        recommendation_description=cause.recommendation_description,
                        expected_impact=cause.expected_impact,
                        risk_level=cause.risk_level,
                        evidence_ids=valid_ids,
                    )
                )
            if not causes:
                raise RuntimeError("Model returned no evidence-grounded root causes")
            diagnosis = model_run.output.diagnosis
            confidence = round(min(model_run.output.confidence_score, 0.95), 2)
            human_approval_required = model_run.output.human_approval_required
            execution_mode = "llm_rag"
            model_name = model_run.model
            input_tokens = model_run.input_tokens
            output_tokens = model_run.output_tokens
        except Exception as exc:
            logger.warning("LLM diagnosis unavailable; using grounded fallback: %s", exc)
            causes = self._rank_root_causes(campaign, payload, query_intent)
            diagnosis = self._compose_diagnosis(campaign, causes, payload, query_intent)
            confidence = self._confidence(causes, payload)
            human_approval_required = any(cause.recommendation_title != "Continue monitoring" for cause in causes)

        recommendations = self._upsert_recommendations(db, campaign.id, causes)
        latency_ms = round((time.perf_counter() - started) * 1000)
        response = AgentDiagnoseResponse(
            campaign_id=campaign.id,
            diagnosis=diagnosis,
            root_causes=[
                RootCause(
                    cause=cause.cause,
                    impact=cause.impact,
                    evidence=cause.evidence,
                    evidence_ids=cause.evidence_ids or self._evidence_ids_for_cause(cause.cause, evidence),
                )
                for cause in causes[:5]
            ],
            tools_called=[result.name for result in tool_results],
            evidence=evidence,
            recommendations=[RecommendationRead.model_validate(item) for item in recommendations],
            confidence_score=confidence,
            human_approval_required=human_approval_required,
            query_intent=query_intent,
            execution_mode=execution_mode,
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            latency_ms=latency_ms,
            retrieved_documents=sorted(
                {doc["source"] for doc in payload["rag_documentation_lookup"]["docs"]}
            ),
        )
        self._write_audit(
            db,
            campaign.id,
            query,
            response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            user_id=user_id,
            request_id=request_id,
        )
        AGENT_RUNS.labels(execution_mode, "success").inc()
        AGENT_LATENCY.labels(execution_mode).observe(latency_ms / 1000)
        return response

    def client_safe_summary(
        self,
        db: Session,
        campaign: Campaign,
        diagnosis: Optional[str] = None,
        *,
        user_id: int | None = None,
        request_id: str | None = None,
    ) -> str:
        response = (
            self.diagnose(
                db,
                campaign,
                "Generate a client-safe explanation",
                user_id=user_id,
                request_id=request_id,
            )
            if diagnosis is None
            else None
        )
        source_diagnosis = diagnosis or (response.diagnosis if response else "")
        evidence = response.evidence if response else [
            item
            for result in [
                tools.check_pacing(db, campaign),
                tools.analyze_targeting(db, campaign),
                tools.validate_creatives(db, campaign),
            ]
            for item in result.evidence
        ]
        reasoner = LLMReasoner()
        if reasoner.available:
            try:
                summary = reasoner.client_safe_summary(
                    campaign_name=campaign.campaign_name,
                    diagnosis=source_diagnosis,
                    evidence=[item.model_dump(mode="json") for item in evidence],
                )
                if summary:
                    return summary
            except Exception as exc:
                logger.warning("LLM client summary unavailable; using fallback: %s", exc)
        return (
            f"{campaign.campaign_name} is currently pacing below plan due to delivery constraints that have reduced "
            f"the amount of eligible, usable supply. {source_diagnosis} Our recommendation is to adjust campaign "
            "settings and refresh any impacted creative assets so delivery can recover while preserving brand safety."
        )

    @staticmethod
    def _evidence_ids_for_cause(cause: str, evidence: list[EvidenceItem]) -> list[str]:
        lowered = cause.lower()
        source_terms = {
            "pacing": ["pacing_snapshots"],
            "targeting": ["inventory_segments", "ad_requests"],
            "inventory": ["ad_requests", "inventory_segments"],
            "creative": ["creatives"],
            "vast": ["vast_validation_errors"],
            "bid": ["bid_responses"],
            "floor": ["bid_responses"],
            "frequency": ["campaigns,impressions", "ad_requests"],
            "started late": ["campaigns,impressions"],
            "launch": ["campaigns,impressions"],
            "goal": ["campaigns,pacing_snapshots"],
            "attainment": ["campaigns,pacing_snapshots"],
            "shared": ["ad_requests,campaigns"],
            "priority": ["ad_requests,campaigns"],
        }
        expected_sources = next(
            (sources for term, sources in source_terms.items() if term in lowered),
            [],
        )
        matched = [
            item.id
            for source in expected_sources
            for item in evidence
            if item.id and (item.source == source or source in item.source.split(","))
        ]
        return list(dict.fromkeys(matched))[:2] or [item.id for item in evidence[:1] if item.id]

    def _rank_root_causes(self, campaign: Campaign, payload: dict, intent: str) -> list[RankedCause]:
        causes: list[RankedCause] = []
        pacing = payload.get("campaign_pacing_tool")
        targeting = payload.get("targeting_analyzer_tool")
        inventory = payload.get("inventory_checker_tool")
        portfolio = payload.get("portfolio_inventory_pressure_tool")
        creatives = payload.get("vast_validation_tool")
        bids = payload.get("sql_analysis_tool")
        setup = payload.get("campaign_setup_tool")
        feasibility = payload.get("goal_feasibility_tool")

        if intent == "goal_feasibility" and feasibility:
            causes.append(
                RankedCause(
                    cause="Goal attainment risk",
                    impact="Low" if feasibility["feasible"] else "High",
                    score=100,
                    evidence=(
                        f"{feasibility['required_daily']:,} impressions/day are required by {feasibility['target_date']} "
                        f"versus a recent {feasibility['recent_daily']:,}/day run rate; projected gap is "
                        f"{feasibility['projected_gap']:,}."
                    ),
                    recommendation_title="Reforecast recovery plan",
                    recommendation_description=(
                        "Align remaining daily delivery with eligible supply and agree a flight extension or scope change "
                        "if the required run rate remains unattainable."
                    ),
                    expected_impact="High",
                    risk_level="Medium",
                )
            )

        if pacing and pacing["pacing_percentage"] < 80:
            causes.append(
                RankedCause(
                    cause="Campaign behind pacing",
                    impact="High" if pacing["pacing_percentage"] < 60 else "Medium",
                    score=58 if pacing["pacing_percentage"] < 60 else 46,
                    evidence=f"Pacing is {pacing['pacing_percentage']}% against expected delivery.",
                    recommendation_title="Reforecast campaign delivery",
                    recommendation_description="Recalculate required daily delivery and align AdOps, sales, and publisher operations on a recovery plan.",
                    expected_impact="Medium",
                )
            )

        if targeting and targeting["eligible_inventory_percentage"] < 25:
            causes.append(
                RankedCause(
                    cause="Narrow targeting",
                    impact="High",
                    score=95,
                    evidence=(
                        f"Only {targeting['eligible_inventory_percentage']}% of modeled supply matches country, "
                        "device, and category targeting."
                    ),
                    recommendation_title="Expand eligible CTV inventory",
                    recommendation_description="Add adjacent countries, devices, or content categories with comparable brand suitability controls.",
                    expected_impact="High",
                    risk_level="Medium",
                )
            )

        if inventory and inventory["failure_rate"] > 35:
            causes.append(
                RankedCause(
                    cause=inventory["top_failure_reason"].replace("_", " ").title(),
                    impact="High" if inventory["failure_rate"] > 55 else "Medium",
                    score=72,
                    evidence=f"{inventory['failure_rate']}% of ad requests failed for this campaign.",
                    recommendation_title="Resolve inventory request filtering",
                    recommendation_description="Review blocked inventory rules with publisher operations and relax constraints where commercially acceptable.",
                    expected_impact="High",
                )
            )

        if portfolio and (
            portfolio["affected_request_count"] > 0
            or (portfolio["campaign_is_high_priority"] and portfolio["portfolio_affected_request_count"] > 0)
        ):
            affected = (
                portfolio["portfolio_affected_request_count"]
                if portfolio["campaign_is_high_priority"]
                else portfolio["affected_request_count"]
            )
            causes.append(
                RankedCause(
                    cause="Shared inventory pressure",
                    impact="High" if affected >= 20 else "Medium",
                    score=88 if intent == "portfolio_pressure" else 68,
                    evidence=(
                        f"{affected} request failures show shared inventory pressure involving active high-priority "
                        f"campaigns {portfolio['high_priority_campaign_ids']}."
                    ),
                    recommendation_title="Protect shared inventory allocation",
                    recommendation_description=(
                        "Review priority allocation across overlapping campaigns and reserve supply according to contracted "
                        "delivery commitments."
                    ),
                    expected_impact="High",
                    risk_level="Medium",
                )
            )

        if creatives and creatives["rejected_count"] > 0:
            causes.append(
                RankedCause(
                    cause="Creative rejected",
                    impact="High",
                    score=93,
                    evidence="At least one assigned creative is rejected and cannot serve.",
                    recommendation_title="Replace rejected creative",
                    recommendation_description="Request a corrected creative package and pause the rejected asset until approval is complete.",
                    expected_impact="High",
                    risk_level="Low",
                )
            )

        if creatives and creatives["error_count"] > 0:
            error_text = ", ".join(creatives["error_codes"]) or "validation errors"
            causes.append(
                RankedCause(
                    cause="VAST validation issue",
                    impact="Medium",
                    score=80,
                    evidence=f"{creatives['error_count']} validation errors detected: {error_text}.",
                    recommendation_title="Fix or replace VAST tag",
                    recommendation_description="Ask the advertiser or ad server team to correct the VAST response and revalidate before scaling delivery.",
                    expected_impact="Medium",
                    risk_level="Low",
                )
            )

        if bids and bids["below_floor_rate"] > 45:
            causes.append(
                RankedCause(
                    cause="Bid price below floor",
                    impact="High" if bids["below_floor_rate"] > 65 else "Medium",
                    score=86,
                    evidence=f"{bids['below_floor_rate']}% of bids are below floor; win rate is {bids['win_rate']}%.",
                    recommendation_title="Increase bid competitiveness",
                    recommendation_description="Raise bid settings or negotiate lower publisher floors for the constrained inventory segments.",
                    expected_impact="High",
                    risk_level="Medium",
                )
            )

        if setup and setup["frequency_cap"] <= 1:
            causes.append(
                RankedCause(
                    cause="Frequency cap too strict",
                    impact="Medium",
                    score=70,
                    evidence=f"Frequency cap is set to {setup['frequency_cap']}, limiting repeat reach on scarce CTV supply.",
                    recommendation_title="Relax frequency cap",
                    recommendation_description="Increase the frequency cap to 2 or 3 for the recovery window and monitor user experience.",
                    expected_impact="Medium",
                    risk_level="Medium",
                )
            )

        if setup and setup["launch_lag_days"] and setup["launch_lag_days"] > 1:
            causes.append(
                RankedCause(
                    cause="Campaign started late",
                    impact="Medium",
                    score=66,
                    evidence=f"First impression was recorded {setup['launch_lag_days']} days after the planned start date.",
                    recommendation_title="Apply launch-delay makegood plan",
                    recommendation_description="Extend the campaign flight or increase daily allocation to recover missed delivery days.",
                    expected_impact="Medium",
                    risk_level="Low",
                )
            )

        if not causes:
            causes.append(
                RankedCause(
                    cause="No critical blocker detected",
                    impact="Low",
                    score=35,
                    evidence="Pacing, inventory, creative, and bid diagnostics do not show a dominant delivery blocker.",
                    recommendation_title="Continue monitoring",
                    recommendation_description="Keep daily pacing checks active and investigate external demand changes if delivery softens.",
                    expected_impact="Low",
                    risk_level="Low",
                )
            )

        ranked = sorted(causes, key=lambda cause: cause.score, reverse=True)
        focus_terms = {
            "targeting_inventory": ("targeting", "inventory", "device", "category", "shared"),
            "creative_vast": ("creative", "vast"),
            "bid_competitiveness": ("bid", "floor", "auction"),
            "frequency_cap": ("frequency",),
            "launch_timing": ("started late", "launch"),
            "portfolio_pressure": ("shared inventory", "priority"),
        }
        if intent in focus_terms:
            focused = [cause for cause in ranked if any(term in cause.cause.lower() for term in focus_terms[intent])]
            return focused or ranked[:1]
        if intent == "goal_feasibility":
            goal_causes = [cause for cause in ranked if cause.cause == "Goal attainment risk"]
            blockers = [
                cause
                for cause in ranked
                if cause.cause not in {"Goal attainment risk", "Campaign behind pacing"}
            ][:2]
            return goal_causes + blockers
        return ranked

    def _compose_diagnosis(
        self,
        campaign: Campaign,
        causes: list[RankedCause],
        payload: dict,
        intent: str,
    ) -> str:
        top = causes[0]
        secondary = causes[1] if len(causes) > 1 else None
        feasibility = payload.get("goal_feasibility_tool") or tools.can_hit_goal_by_end(campaign)
        goal_text = (
            f"The campaign needs {feasibility['required_daily']:,} impressions per day over "
            f"{feasibility['remaining_days']} remaining day(s), versus a recent run rate of "
            f"{feasibility['recent_daily']:,}."
        )
        if intent == "goal_feasibility":
            answer = "Yes" if feasibility["feasible"] else "No"
            return (
                f"{answer}. Campaign {campaign.id} is {'on a feasible path' if feasibility['feasible'] else 'unlikely'} "
                f"to reach its goal by {feasibility['target_date']} at the current run rate. {goal_text} "
                f"The projected shortfall is {feasibility['projected_gap']:,} impressions. "
                f"The leading recovery constraint is {secondary.cause.lower() if secondary else top.cause.lower()}."
            )
        if intent == "targeting_inventory":
            targeting = payload.get("targeting_analyzer_tool", {})
            inventory = payload.get("inventory_checker_tool", {})
            return (
                f"Targeting is materially restricting Campaign {campaign.id}: only "
                f"{targeting.get('eligible_inventory_percentage', 0)}% of modeled supply is eligible across "
                f"{targeting.get('eligible_segments', 0)} segment(s). The constrained dimensions are "
                f"{', '.join(targeting.get('constrained_dimensions', [])) or 'not isolated'}, while "
                f"{inventory.get('failure_rate', 0)}% of requests fail, led by "
                f"{str(inventory.get('top_failure_reason', 'no dominant rule')).replace('_', ' ')}."
            )
        if intent == "creative_vast":
            creative = payload.get("vast_validation_tool", {})
            return (
                f"Creative delivery is {'blocked' if creative.get('rejected_count', 0) else 'degraded'} for Campaign "
                f"{campaign.id}: {creative.get('rejected_count', 0)} creative(s) are rejected and "
                f"{creative.get('error_count', 0)} VAST errors were detected "
                f"({', '.join(creative.get('error_codes', [])) or 'no runtime error codes'})."
            )
        if intent == "bid_competitiveness":
            bids = payload.get("sql_analysis_tool", {})
            return (
                f"Campaign {campaign.id} is not sufficiently competitive in the auction: "
                f"{bids.get('below_floor_rate', 0)}% of bids are below publisher floors and the win rate is "
                f"{bids.get('win_rate', 0)}%. Average bid is EUR {bids.get('avg_bid_price', 0)} against an average "
                f"floor of EUR {bids.get('avg_floor_price', 0)}."
            )
        if intent == "frequency_cap":
            setup = payload.get("campaign_setup_tool", {})
            inventory = payload.get("inventory_checker_tool", {})
            frequency_failures = inventory.get("failure_reasons", {}).get("frequency_cap_exceeded", 0)
            return (
                f"Frequency controls are restricting Campaign {campaign.id}: the cap is "
                f"{setup.get('frequency_cap', campaign.frequency_cap)} per household/day and "
                f"{frequency_failures} requests were rejected because the frequency cap was exceeded."
            )
        if intent == "launch_timing":
            setup = payload.get("campaign_setup_tool", {})
            lag = setup.get("launch_lag_days")
            return (
                f"Campaign {campaign.id} {'started late' if lag and lag > 1 else 'did not show a material launch delay'}"
                f"{f' by {lag} days' if lag and lag > 1 else ''}. {goal_text}"
            )
        if intent == "portfolio_pressure":
            portfolio = payload.get("portfolio_inventory_pressure_tool", {})
            if portfolio.get("campaign_is_high_priority"):
                return (
                    f"Yes. Campaign {campaign.id} is high priority and is associated with "
                    f"{portfolio.get('portfolio_affected_request_count', 0)} shared-inventory request failures on "
                    "other campaigns. Review allocation before changing bids or targeting."
                )
            return (
                f"Campaign {campaign.id} lost {portfolio.get('affected_request_count', 0)} requests to shared "
                f"high-priority inventory pressure from campaigns {portfolio.get('high_priority_campaign_ids', [])}."
            )
        if intent == "next_action":
            return (
                f"The next action for Campaign {campaign.id} is to {top.recommendation_title.lower()}. "
                f"{top.evidence} This action remains subject to human approval."
            )
        if secondary:
            return (
                f"Campaign {campaign.id} is underdelivering primarily because of {top.cause.lower()}. "
                f"A secondary issue is {secondary.cause.lower()}. {goal_text}"
            )
        return f"Campaign {campaign.id} is currently driven by {top.cause.lower()}. {goal_text}"

    def _confidence(self, causes: list[RankedCause], payload: dict) -> float:
        base = 0.58
        if payload.get("campaign_pacing_tool", {}).get("pacing_percentage", 0) > 0:
            base += 0.08
        if payload.get("targeting_analyzer_tool", {}).get("eligible_segments", -1) >= 0:
            base += 0.08
        if payload.get("sql_analysis_tool", {}).get("total_bids", 0) >= 20:
            base += 0.08
        if payload.get("vast_validation_tool", {}).get("creative_count", 0) > 0:
            base += 0.06
        if payload.get("goal_feasibility_tool"):
            base += 0.04
        if causes and causes[0].score > 80:
            base += 0.08
        return round(min(base, 0.94), 2)

    def _upsert_recommendations(self, db: Session, campaign_id: int, causes: list[RankedCause]):
        recommendations = [
            create_recommendation(
                db,
                campaign_id=campaign_id,
                title=cause.recommendation_title,
                description=cause.recommendation_description,
                expected_impact=cause.expected_impact,
                risk_level=cause.risk_level,
            )
            for cause in causes[:3]
        ]
        db.commit()
        for recommendation in recommendations:
            db.refresh(recommendation)
        return recommendations

    def _write_audit(
        self,
        db: Session,
        campaign_id: int,
        query: str,
        response: AgentDiagnoseResponse,
        *,
        input_tokens: int,
        output_tokens: int,
        user_id: int | None,
        request_id: str | None,
    ) -> None:
        log = AgentAuditLog(
            campaign_id=campaign_id,
            user_query=query,
            tools_called=json.dumps(response.tools_called),
            evidence=response.model_dump_json(include={"evidence"}),
            diagnosis=response.diagnosis,
            confidence_score=response.confidence_score,
            query_intent=response.query_intent,
            model_name=response.model_name,
            execution_mode=response.execution_mode,
            prompt_version=response.prompt_version,
            latency_ms=response.latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_id=request_id,
            user_id=user_id,
            created_at=utc_now(),
        )
        db.add(log)
        db.commit()

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import get_settings

PROMPT_VERSION = "adops-diagnosis-v4"


class GroundedCause(BaseModel):
    cause: str = Field(min_length=3, max_length=120)
    impact: str = Field(pattern="^(High|Medium|Low)$")
    evidence_ids: list[str] = Field(min_length=1, max_length=4)
    recommendation_title: str = Field(min_length=3, max_length=160)
    recommendation_description: str = Field(min_length=8, max_length=500)
    expected_impact: str = Field(pattern="^(High|Medium|Low)$")
    risk_level: str = Field(pattern="^(High|Medium|Low)$")


class GroundedDiagnosis(BaseModel):
    diagnosis: str = Field(min_length=20, max_length=1200)
    root_causes: list[GroundedCause] = Field(min_length=1, max_length=4)
    confidence_score: float = Field(ge=0, le=1)
    human_approval_required: bool


@dataclass(frozen=True)
class ModelRun:
    output: GroundedDiagnosis
    model: str
    input_tokens: int
    output_tokens: int


SYSTEM_PROMPT = """
You are SignalOps AI, a senior CTV and addressable TV campaign troubleshooting agent.

Your job is to reason over tool evidence and retrieved operational guidance. Identify the
smallest set of root causes that explains campaign underdelivery and recommend reversible,
operationally realistic actions.

Non-negotiable guardrails:
1. Use only facts contained in the supplied EVIDENCE items. Never invent a metric or event.
2. Every root cause must cite one or more evidence IDs exactly as provided.
3. Rank causes by likely delivery impact, not by how dramatic they sound.
4. Do not claim that a recommendation has been executed.
5. Mark human_approval_required true for any change to targeting, bids, frequency, inventory,
   flight dates, or creatives.
6. Treat retrieved documentation as guidance, not campaign-specific proof.
7. Use direct operational language. Avoid generic AI phrases.
8. Answer the operator's exact question. For a narrow question about targeting, creative/VAST,
   bids, frequency, launch timing, shared inventory, or goal feasibility, omit unrelated causes
   even if they appear elsewhere in the evidence.
9. Do not attribute fault to a specific publisher, advertiser, or partner unless the supplied
   evidence directly supports it. Prefer describing the mechanism (e.g. "shared inventory
   pressure") over blaming a named party.
""".strip()


def _response_schema() -> dict[str, Any]:
    return GroundedDiagnosis.model_json_schema()


class LLMReasoner:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def available(self) -> bool:
        return self.settings.llm_available

    def diagnose(
        self,
        *,
        campaign_context: dict[str, Any],
        query: str,
        evidence: list[dict[str, Any]],
        retrieved_documents: list[dict[str, Any]],
    ) -> ModelRun:
        if not self.available:
            raise RuntimeError("LLM is not configured")
        client = OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.openai_timeout_seconds,
            max_retries=2,
        )
        payload = {
            "user_query": query,
            "campaign": campaign_context,
            "evidence": evidence,
            "retrieved_operational_guidance": retrieved_documents,
        }
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, default=str)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "grounded_adops_diagnosis",
                    "strict": True,
                    "schema": _response_schema(),
                },
            },
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Model returned an empty diagnosis")
        output = GroundedDiagnosis.model_validate_json(content)
        usage = response.usage
        return ModelRun(
            output=output,
            model=response.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    def client_safe_summary(
        self,
        *,
        campaign_name: str,
        diagnosis: str,
        evidence: list[dict[str, Any]],
    ) -> str:
        if not self.available:
            raise RuntimeError("LLM is not configured")
        client = OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.openai_timeout_seconds,
            max_retries=2,
        )
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Write a concise client-safe campaign update. Use only supplied evidence. "
                        "Do not expose publisher names, floor prices, loss reasons, internal tool names, "
                        "or raw validation traces. State the issue, its delivery effect, and the next step. "
                        "Do not claim that a fix has already been applied. Do not state or imply certainty "
                        "beyond what the evidence supports. Do not attribute fault to a specific publisher, "
                        "advertiser, or partner unless the evidence directly supports it."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"campaign_name": campaign_name, "diagnosis": diagnosis, "evidence": evidence},
                        default=str,
                    ),
                },
            ],
        )
        return (response.choices[0].message.content or "").strip()

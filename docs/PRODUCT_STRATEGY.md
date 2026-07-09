# Product Strategy

## Strategic Position

SignalOps AI is an operational intelligence layer for CTV and addressable TV platforms. It does not replace the ad server, SSP, or reporting stack. It converts fragmented platform signals into an evidence-backed decision workflow.

## Why This Wedge

Campaign underdelivery is:

- Frequent enough to create recurring operating cost.
- Commercially important because it threatens booked media and client trust.
- Data-rich enough for grounded AI.
- Difficult enough to require cross-system reasoning.
- Safe to introduce through recommendation-only workflows.

That makes it a stronger first agent than autonomous optimization, where incorrect actions can immediately affect spend, contractual obligations, and inventory allocation.

## Target Customer

Initial buyer: Head of Ad Operations or Platform Operations at a CTV/video platform.

Initial users:

- AdOps Managers.
- Campaign Managers.
- Publisher Operations.
- Customer Success.

Expansion users:

- Agencies and broadcaster sales operations.
- Product teams analyzing recurring platform defects.

## Value Proposition

“Move from a pacing alert to an evidence-backed recovery decision in minutes, with the controls required for high-value TV campaigns.”

## Differentiation

- CTV-specific operational model rather than a generic support chatbot.
- Cross-domain evidence across delivery, supply, creative, and auction layers.
- Transparent model provenance and evidence IDs.
- Human approval and client-safe communication as first-class workflows.
- Availability fallback when the AI provider is unavailable.

## Monetization Hypotheses

1. Premium Signal module priced by managed campaign volume.
2. Enterprise operations tier with connectors, governance, and custom playbooks.
3. Managed-service efficiency package sharing documented operational savings.
4. Product intelligence add-on for recurring failure patterns and supply quality.

Pricing should follow a pilot that quantifies resolved incidents, hours saved, and protected media value. See [ROI_MODEL.md](./ROI_MODEL.md).

## Build, Buy, Partner

- **Build:** AdTech tools, evidence model, workflow, guardrails, evaluations, and approvals.
- **Buy:** Foundation-model inference and managed embedding APIs where economics allow.
- **Partner/connect:** Ad server, SSP, VAST validation, identity, incident management, and customer communication systems.

The proprietary advantage is not the base model. It is the domain tool layer, incident dataset, workflow integration, and evaluation feedback loop.

## Roadmap

### Now: Evidence-Backed Diagnosis

- Campaign health.
- LLM/RAG reasoning.
- VAST triage.
- Approval and audit.

### Next: Connected Pilot

- Read-only Metro Exchange/ad-server connectors.
- Data freshness indicators.
- Historical incident labels.
- Expert feedback capture.
- Slack or incident-system handoff.

### Later: Assisted Optimization

- Change simulation.
- Delivery recovery forecasts.
- Staged writes with rollback.
- Portfolio-level inventory allocation recommendations.

## Portfolio Relevance

The concept demonstrates the complete AI product-management loop: discovering a CTV operations problem, forming a product thesis, translating it into technical architecture, building the prototype, defining safeguards, and specifying how to validate customer and commercial value.

## Strategic Risks

- Data availability may be less unified than the prototype assumes.
- Root causes can be commercial or contractual, not only technical.
- Operators may distrust model synthesis unless evidence is faster to inspect.
- A generic assistant may become a feature rather than a monetizable product.
- Model costs and latency may exceed value for low-severity incidents.

The rollout therefore begins in shadow mode and measures decision quality before automation.

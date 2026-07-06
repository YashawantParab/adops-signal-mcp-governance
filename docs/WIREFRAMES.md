# Product Wireframes

These low-fidelity wireframes show the information architecture and decision flow before visual styling.

## Campaign Health

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ AdOps Signal                    AI mode: LLM + RAG       Alex / AdOps   │
├───────────────┬──────────────────────────────────────────────────────────┤
│ Operations    │ Delivery Operations                                      │
│ Investigations│ [5 monitored] [3 high risk] [2.1m gap] [EUR 201k risk] │
│ VAST Validator├──────────────────────────────────────────────────────────┤
│ Decision Queue│ Campaign     Pacing  Risk  Main issue        Action      │
│ Audit Logs    │ RheinAuto     58%     High  Narrow targeting  Diagnose   │
│ Business Value│ NordicStream  41%     High  Creative rejected Diagnose   │
│               │ GameHub       39%     High  Device mismatch   Diagnose   │
└───────────────┴──────────────────────────────────────────────────────────┘
```

## Diagnosis Workspace

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Campaign [1045 RheinAuto ▼]  Question [Why underdelivering?] [Diagnose] │
├──────────────────────────────────────────────────────────────────────────┤
│ DIAGNOSIS                                              87% confidence    │
│ Eligible CTV supply is constrained; VAST timeout is secondary.           │
│ Human approval required                                                │
├───────────────────────────────────┬──────────────────────────────────────┤
│ Ranked root causes                │ Evidence                             │
│ 1 Narrow targeting        HIGH    │ E1 Pacing: 58%                       │
│   E3 eligible supply: 14%          │ E3 Inventory: 1 eligible segment     │
│ 2 VAST timeout            MEDIUM  │ E7 Creative 501: timeout errors      │
├───────────────────────────────────┴──────────────────────────────────────┤
│ Recommendations                                                         │
│ [Expand inventory: pending] [Replace VAST: pending]                     │
├──────────────────────────────────────────────────────────────────────────┤
│ Trace: gpt-5.4-mini · 1.8s · 7 tools · pacing_playbook.md               │
└──────────────────────────────────────────────────────────────────────────┘
```

## Approval Queue

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Recommendation                  Expected impact   Risk    Status          │
│ Expand eligible CTV inventory   High              Medium  Pending         │
│ Decision rationale [Evidence checked and controlled test approved...]    │
│                                                      [Reject] [Approve]  │
├──────────────────────────────────────────────────────────────────────────┤
│ Governance: User 1 · approved · rationale · timestamp                    │
└──────────────────────────────────────────────────────────────────────────┘
```

## Business Impact

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Business Impact Model                                                   │
│ [45 incidents] [42.8 hours saved] [EUR 18.7k/month] [EUR 224k/year]     │
├──────────────────────────────────┬───────────────────────────────────────┤
│ Editable assumptions             │ Value decomposition                   │
│ campaigns/month        [250]     │ Operations capacity      EUR 2,480    │
│ incident rate          [18%]     │ Media value protected    EUR 16,200   │
│ before / after         [75/18]   │                                       │
│ campaign value         [18,000]  │ Directional; calibrate in pilot       │
└──────────────────────────────────┴───────────────────────────────────────┘
```

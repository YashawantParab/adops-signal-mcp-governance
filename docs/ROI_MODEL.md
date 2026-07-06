# ROI Model

## Decision

The first business case is operational capacity plus media value protected through earlier intervention. The model is implemented at `/impact` and calculated by `POST /api/insights/roi`.

## Formula

```text
monthly incidents
  = campaigns per month × incident rate

hours saved
  = monthly incidents × (minutes before - minutes after) / 60

labor savings
  = hours saved × loaded hourly cost

revenue protected
  = monthly incidents × average campaign value
    × media value at risk × recoverable share

total monthly value
  = labor savings + revenue protected
```

## Base Case

| Assumption | Value |
|---|---:|
| Campaigns per month | 250 |
| Campaigns requiring investigation | 18% |
| Investigation time today | 75 minutes |
| Investigation time with Signal | 18 minutes |
| Loaded operations cost | EUR 58/hour |
| Average campaign media value | EUR 18,000 |
| Media value at risk | 8% |
| Recoverable share | 25% |

Base-case output:

- 45 incidents per month.
- 42.8 operations hours recovered per month.
- Approximately EUR 2,480 monthly labor capacity.
- Approximately EUR 16,200 monthly media value protected.
- Approximately EUR 224,000 directional annual value.

These values are hypotheses, not realized savings. A pilot must replace every assumption with observed data.

## Pilot Measurement

- Randomize eligible incidents between current workflow and Signal-assisted workflow.
- Measure time from alert to agreed root cause.
- Measure number of tools and handoffs used.
- Track whether a recommended intervention was approved.
- Compare recovered delivery against matched historical incidents.
- Report false interventions and client-communication corrections as counter-metrics.

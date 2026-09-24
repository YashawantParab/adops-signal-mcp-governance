# Jev / TypeSafe System One — Integration Research (Phase 2A)

Researched 2026-09-24 via typesafe.ai's public blog, docs.typesafe.ai, the official
`typesafe-ai/typesafe-sdk-python` GitHub repo, and web search. `TYPESAFE_API_KEY` is
**not available in this environment** — nothing below has been exercised against the
live API. Everything is sourced from public docs, not guessed.

## What Jev is

Jev is TypeSafe AI's first "System One Model": a non-chat model that takes free-form
`state` plus a set of typed `questions` and returns typed, calibrated probabilistic
answers instead of free text. Trained with "Reinforcement Learning for Calibrated
Decisions" (RLCD) rather than RLHF, positioned as fast (vendor claims 70–500ms
end-to-end, 40–200x faster than an equivalent LLM call) and cheap (vendor claims
$0.042 / 1M input tokens, output tokens free). Early access, waitlist-gated.

Source: https://typesafe.ai/blog/introducing-system-one-models-and-jev

## Package / install

- PyPI package: `typesafe-sdk`. Import as `typesafe_sdk`.
- `pip install typesafe-sdk` (or `uv add typesafe-sdk`).
- Official repo: https://github.com/typesafe-ai/typesafe-sdk-python

**Not added to `backend/requirements.txt` in this pass** — flagged for explicit
approval, see the Phase 2 checkpoint report. It costs nothing to have installed (no
key = no calls), but the brief for this phase explicitly asked to confirm before
adding a new dependency tied to a paid API.

## Auth

- Env var: `TYPESAFE_API_KEY` (matches this project's chosen name).
- Optional `TYPESAFE_BASE_URL` to override the API host.
- Can also be passed explicitly as `TypeSafeClient(api_key=...)`.

## Client / call shape

```python
from typesafe_sdk import TypeSafeClient, AsyncTypeSafeClient, Choice, Noul, Score

with TypeSafeClient() as client:
    response = client.system_one(
        state={"document": "..."},
        questions={
            "billing": Noul(instructions="Is this ticket about billing?"),
            "tone": Choice(
                instructions="What is the customer's tone?",
                criteria={"calm": None, "frustrated": None, "angry": None},
            ),
            "urgency": Score(
                instructions="How urgent is this ticket?",
                criteria=["can wait", "this week", "today"],
            ),
        },
    )
```

Constructor (`TypeSafeClient` / `AsyncTypeSafeClient`, both context managers):

```python
TypeSafeClient(
    *, api_key: str | None = None, model: str | None = None,
    retry: RetryPolicy | None = None, timeout: float | httpx.Timeout | None = None,
    headers=None, transport=None, http_client=None, base_url: str | None = None,
)
```

`system_one()`:

```python
system_one(
    state: JSONContent, questions: Mapping[str, Question], *,
    model: str | None = None, retry: RetryPolicy | None = None,
    timeout: float | httpx.Timeout | None = None,
    extra_headers=None, extra_body=None, response_model: type[ResponseT] | None = None,
) -> SystemOneResponse | ResponseT
```

Default retry: `max_retries=2`, backoff 0.5s doubling to 5s (0.25 jitter), retries
408/429/5xx + connection/timeout errors, honors `Retry-After`. Default total timeout
budget: 30s.

Source: https://docs.typesafe.ai/sdk/python (constructor/method pages), confirmed via
direct fetch of the rendered docs.

## Question primitives and answer fields

| Type | Input | Answer field(s) |
|---|---|---|
| `Noul(instructions=str)` | yes/no question | `.noul`: float in **[0, 1]** — itself both the decision (>0.5 ≈ yes) and the calibrated confidence (closer to 0 or 1 = more confident); no separate confidence field |
| `Choice(instructions=str, criteria=dict[str, None])` | pick one of N labels | `.choice`: selected label. Per the announcement post, also `.probabilities` (per-label distribution) and `.confidence` (float) |
| `Score(instructions=str, criteria=list[str])` | ordered severity/level | `.score`: selected level. Per the announcement post, also `.probabilities` and `.confidence` |

Response access: `response.nouls["billing"].noul`, `response.choices["tone"].choice`,
`response.scores["urgency"].score`; also `response.request_id`. A typed shorthand
(`response.billing.noul`) and a custom `response_model=` for direct typed parsing also
exist per the docs.

**Confidence note:** I directly fetched code examples showing `.noul`/`.choice`/`.score`
access. The `.probabilities`/`.confidence` attribute names for `Choice`/`Score` are
sourced from the announcement blog's prose ("Choice: Returns `choice`, `probabilities`,
and `confidence`") rather than a verbatim SDK code sample I could fetch directly — the
docs page hosting the full `ChoiceAnswer`/`ScoreAnswer` type definitions 404'd when
fetched directly. **The adapter below reads these defensively (`getattr(..., None)`)**
so an imprecise field name degrades to "confidence unknown" instead of crashing.

Usage/token/cost fields: the docs mention the response carries "model and token usage
details" but I could not get a verbatim field name for them from a live fetch. The
adapter stores `estimated_cost_usd=None` unless a real field is found at integration
time — never computed from the vendor's published per-token rate, which would count as
fabricating a cost the SDK itself didn't report.

## Errors

Typed exception hierarchy (base `TypeSafeError`), per the official repo (confirmed via
a GitHub issue on `typesafe-ai/typesafe-sdk-python` plus the docs' usage/exceptions
pages — the exceptions page itself 404'd on direct fetch, so treat this list as
high-confidence but not verbatim-quoted):

`TypeSafeError` → `TypeSafeAPIError` → `TypeSafeBadRequestError` (400),
`TypeSafeAuthenticationError` (401), `TypeSafePermissionDeniedError` (403),
`TypeSafeNotFoundError` (404), `TypeSafeUnprocessableEntityError` (422),
`TypeSafeRateLimitError` (429, carries `retry_after_ms`), `TypeSafeInternalServerError`
(5xx), `TypeSafeAPIConnectionError`, `TypeSafeAPITimeoutError`,
`TypeSafeAPIResponseValidationError` (200 but the body didn't parse).

The adapter catches the base `TypeSafeError` as its primary boundary (correct
regardless of exact subclass spelling), and additionally checks for
`TypeSafeAuthenticationError` / `TypeSafeAPITimeoutError` by class name where available,
falling back to the base class if those names turn out to differ once exercised for
real.

## Early-access limitations

- Waitlist/access-gated; no public self-serve signup confirmed.
- No `TYPESAFE_API_KEY` available in this environment → **JevGate live execution is
  NOT RUN in this phase.** The adapter boundary is implemented and unit-testable with
  a stub client; DecisionGate comparison evals mark Jev rows `NOT RUN`, never fabricated.

## Sources

- https://typesafe.ai/blog/introducing-system-one-models-and-jev
- https://docs.typesafe.ai/ (llms.txt index)
- https://docs.typesafe.ai/sdk/python (quickstart, client constructor, usage)
- https://github.com/typesafe-ai/typesafe-sdk-python
- https://github.com/typesafe-ai/typesafe-sdk-python/issues/9 (exception hierarchy, API key echo bug)

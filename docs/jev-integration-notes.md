# Jev / TypeSafe System One — Integration Research

Researched 2026-09-24/25. `TYPESAFE_API_KEY` is **not available in this environment**
(TypeSafe's early-access waitlist is currently full) — nothing here has been exercised
against the live API. This revision supersedes the 2026-09-24 notes: everything below
was re-verified by installing the real published package (`pip install typesafe-sdk`
in a scratch venv) and reading its actual source (`_core/client/aio/client.py`,
`_core/errors.py`, `_core/question_types.py`, `_core/response_types.py`,
`_schemas/models.py`, `constants.py`) rather than relying on docs-page prose alone.
Findings are separated into three buckets so the adapter never treats a guess as a fact.

---

## CONFIRMED FROM OFFICIAL SOURCES

Verified either by direct `pip install typesafe-sdk==0.7.1` + source inspection in a
scratch venv, or by a verbatim fetch of `docs.typesafe.ai` / the package's own metadata.

**Package**
- PyPI: `typesafe-sdk`, latest published version `0.7.1` (released 2026-09-21).
- Import name: `typesafe_sdk`. Requires Python `>=3.10`.
- Runtime dependencies (from `pyproject.toml`): `httpx2>=2.0.0`, `pydantic>=2.12.0`,
  `pydantic-core>=2.41.1`, `tenacity>=9.0.0`, `typing-extensions>=4.13.0`.
  - `httpx2` is TypeSafe's own internal HTTP client package, not standard `httpx`.
  - The `pydantic>=2.12.0` floor is higher than this repo's existing pin
    (`pydantic==2.11.7`, set for the Phase 1 `mcp` SDK). A full combined resolution
    test (`typesafe-sdk` + every existing backend dependency, in a clean venv) installs
    cleanly with `pydantic==2.13.5` and `pip check` reports no conflicts — see Step 3.

**Full export surface** (`typesafe_sdk.__all__`, 37 names, confirmed via
`python -c "import typesafe_sdk; print(sorted(typesafe_sdk.__all__))"` against the real
installed package):
`Answer, AsyncModels, AsyncTypeSafeClient, Choice, ChoiceAnswer, ChoiceModel,
JSONContent, JSONValue, ListModelsResponse, ModelMetadata, Models, Noul, NoulAnswer,
NoulCriteria, NoulModel, Question, QuestionModel, Questions, RetryPolicy, Score,
ScoreAnswer, ScoreModel, SystemOneResponse, TypeSafeAPIConnectionError,
TypeSafeAPIError, TypeSafeAPIResponseValidationError, TypeSafeAPITimeoutError,
TypeSafeAuthenticationError, TypeSafeBadRequestError, TypeSafeClient, TypeSafeError,
TypeSafeInternalServerError, TypeSafeNotFoundError, TypeSafePermissionDeniedError,
TypeSafeRateLimitError, TypeSafeUnprocessableEntityError, Usage, constants`

**Client construction and call shape** (`_core/client/aio/client.py`, read verbatim):
```python
AsyncTypeSafeClient(
    *, api_key: str | None = None, model: str | None = None,
    retry: RetryPolicy | None = None, timeout: float | None = None,
    headers=None, transport=None, http_client=None, base_url: str | None = None,
)

async def system_one(
    self, state, questions, *,
    model: str | None = None, retry: RetryPolicy | None = None,
    timeout: float | None = None, extra_headers=None, extra_body=None,
    response_model: type[ResponseT] | None = None,
) -> SystemOneResponse | ResponseT
```
A synchronous `TypeSafeClient` with the same shape also exists. Both are context
managers (`async with` / `with`).

**Question input types** (`_core/question_types.py`, read verbatim):
```python
Noul(type="noul", instructions: JSONContent | None = None, criteria: NoulCriteria | None = None)
Choice(type="choice", criteria: Mapping[str, JSONContent | None], instructions: JSONContent | None = None)
Score(type="score", criteria: Sequence[JSONContent], instructions: JSONContent | None = None)
```
This confirms `Choice(instructions=..., criteria={option: None for option in ...})` —
already used by the existing adapter — is the exact, current, correct call shape.

**Answer / response types** (`_schemas/models.py`, read verbatim):
```python
class ChoiceAnswer: type: Literal["choice"]; choice: str; confidence: float; probabilities: dict[str, float]
class ScoreAnswer:  type: Literal["score"];  score: str;  confidence: float; legend: ...; probabilities: dict[str, float]
class NoulAnswer:   type: Literal["noul"];   noul: float
class Answer(RootModel[NoulAnswer | ScoreAnswer | ChoiceAnswer])
class SystemOneResponse: model: str; answers: dict[str, Answer]; usage: Usage
class Usage: input_tokens: int; output_tokens: int
```
`ChoiceAnswer`/`ScoreAnswer` **do** carry `.confidence` and `.probabilities` as real
typed fields (this was only inferred from blog prose in the prior revision of this
document — now confirmed from the actual Pydantic model). `NoulAnswer` carries only
`.noul` (a float in `[0, 1]`, doubling as both decision and calibrated confidence) — no
separate confidence field. `SystemOneResponse.usage` is `{input_tokens, output_tokens}`
only — **there is no cost or dollar-amount field anywhere in the response schema.**

**Response accessors** (`_core/response_types.py`, read verbatim): `SystemOneResponse`
exposes `@cached_property` accessors `.nouls`, `.choices`, `.scores`, each a
`dict[str, <TypedAnswer>]` filtered from `.answers` by `isinstance`. So
`response.choices["decision"].choice` (already used by the existing adapter) is the
exact, current, correct access pattern — not an inference.

**Exception hierarchy** (`_core/errors.py`, read verbatim):
```
TypeSafeError (base)
└─ TypeSafeAPIError (fields: status, body, headers, endpoint; property: request_id)
   ├─ TypeSafeBadRequestError            (400)
   ├─ TypeSafeAuthenticationError        (401)
   ├─ TypeSafePermissionDeniedError      (403)
   ├─ TypeSafeNotFoundError              (404)
   ├─ TypeSafeUnprocessableEntityError   (422)
   ├─ TypeSafeRateLimitError             (429, field: retry_after_ms)
   ├─ TypeSafeInternalServerError        (5xx)
   └─ TypeSafeAPIResponseValidationError (200 but body failed validation; field: field_path)
└─ TypeSafeAPIConnectionError (also subclasses ConnectionError)
   └─ TypeSafeAPITimeoutError (also subclasses TimeoutError; field: timeout)
```
This is a strictly more precise hierarchy than the previous revision guessed (all
subclass names, HTTP codes, and fields are exact, not approximate).

**Env vars and defaults** (`constants.py`, read verbatim):
- `TYPESAFE_API_KEY` — the API key (matches this project's existing env var name).
- `TYPESAFE_BASE_URL` — override the API host. Default: `https://api.typesafe.ai`.
- `TYPESAFE_DEFAULT_MODEL` — override the default model. Default: `"jev-latest"`.
- `TYPESAFE_LOG_LEVEL` — SDK-internal log verbosity.
- Default request timeout: `10.0` seconds (independent of this repo's own
  `JEV_TIMEOUT_SECONDS`, which is passed explicitly and takes precedence).

**Retry policy** (`RetryPolicy` dataclass, read verbatim): default
`max_retries=2, backoff_initial=0.5, backoff_max=5.0, backoff_jitter=0.25,
respect_retry_after=True, timeout=30.0`, retries on configurable `http_statuses` plus
connection/timeout errors. Configurable via `retry=RetryPolicy(...)` on the client or
per-call.

**Model listing API**: `client.models` / `AsyncTypeSafeClient(...).models` (types
`Models`/`AsyncModels`) exposes a `list()`-style call returning
`ListModelsResponse{models: tuple[ModelMetadata, ...]}` where
`ModelMetadata{name: str, description: str, release_date: str}`. This lets a caller
enumerate models actually available to the account. Not required for the adapter's core
`system_one()` call, but is the mechanism a future readiness check could use to validate
`JEV_MODEL` against real account access once a key exists.

**What Jev is** (from `https://typesafe.ai/blog/introducing-system-one-models-and-jev`,
a public source, treated as vendor marketing prose rather than an API contract): Jev is
TypeSafe AI's first "System One Model" — a non-chat model that takes free-form `state`
plus a set of typed `questions` (`Noul`/`Choice`/`Score`) and returns typed, calibrated
probabilistic answers instead of free text. Positioned as fast and cheap relative to an
equivalent LLM call. Early access, waitlist-gated; **the waitlist is currently full and
no self-serve signup is available**, which is why this integration has no live key.

---

## INFERRED / NOT VERIFIED

Reasonable to assume from the confirmed contract above, but not something we have
directly observed against a live response (since no live call has been made).

- The *typical* magnitude of `.confidence`/`.probabilities` values in practice for
  realistic ad-ops-style prompts (the field types are confirmed; their real-world
  distribution is not).
- Whether `TYPESAFE_BASE_URL` / `TYPESAFE_DEFAULT_MODEL` env vars are actually read by
  `AsyncTypeSafeClient()` when no explicit `base_url=`/`model=` kwarg is passed (the
  constants exist in `constants.py` and are named as the obvious env-var wiring point,
  but we have not traced the constructor's env-var-reading code path line by line).
- Exact behavior of the model-listing endpoint (`client.models.list()`-equivalent)
  under an invalid/expired key — presumed to raise `TypeSafeAuthenticationError` like
  every other endpoint, consistent with the shared exception hierarchy, but not observed.

---

## NOT PUBLICLY DOCUMENTED

Actively searched for (via `docs.typesafe.ai`, its `llms.txt` full page index, and
`typesafe.ai`) and confirmed absent, not merely unread:

- **Rate limits**: no requests/min, tokens/min, or concurrency limits are published
  anywhere in the docs index or marketing site.
- **Pricing / billing**: no per-token, per-call, or subscription pricing page exists
  publicly. The only cost-adjacent text found anywhere is a cookbook aside claiming
  batching multiple questions into one call is "12.2x cheaper and 10.0x faster" than
  separate calls — a relative claim, not a rate. No dollar figures are documented.
  (The prior revision of this document cited a specific vendor blog price of
  "$0.042 / 1M input tokens" — that figure could not be re-confirmed against the
  current docs index and is being dropped rather than repeated unverified.)
- **Cost/usage reporting mechanism**: `SystemOneResponse.usage` reports
  `input_tokens`/`output_tokens` only (confirmed above); there is no documented way to
  convert that into a dollar cost without an undocumented, unverified rate. The adapter
  must therefore persist `cost_usd=None` always — computing a cost from a guessed rate
  would be fabrication, not measurement.

---

## Early-access status

No `TYPESAFE_API_KEY` is available in this environment — **JevGate live execution is
NOT RUN.** The adapter boundary is fully implemented and unit-tested against realistic
deterministic fixtures that mock only the SDK/network boundary (see
`backend/tests/test_jev_gate.py`); DecisionGate comparison evals mark Jev rows
`NOT RUN`, never fabricated. See `docs/JEV_ACTIVATION_RUNBOOK.md` for the exact steps to
go live once access is granted.

## Sources

- https://typesafe.ai/blog/introducing-system-one-models-and-jev (vendor positioning/marketing — not an API contract)
- https://docs.typesafe.ai/ and https://docs.typesafe.ai/llms.txt (full docs index)
- `typesafe-sdk==0.7.1` on PyPI — installed and inspected directly in a scratch venv
- Package source read verbatim: `_core/client/aio/client.py`, `_core/errors.py`,
  `_core/question_types.py`, `_core/response_types.py`, `_schemas/models.py`,
  `constants.py`, `__init__.py`

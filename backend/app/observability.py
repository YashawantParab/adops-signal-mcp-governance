from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request
from prometheus_client import Counter, Histogram

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)

HTTP_REQUESTS = Counter(
    "adops_signal_http_requests_total",
    "HTTP requests by method, route, and status",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "adops_signal_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
)
AGENT_RUNS = Counter(
    "adops_signal_agent_runs_total",
    "Agent diagnoses by execution mode and outcome",
    ["execution_mode", "outcome"],
)
AGENT_LATENCY = Histogram(
    "adops_signal_agent_duration_seconds",
    "Agent diagnosis latency",
    ["execution_mode"],
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_context.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


async def request_observability_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    token = request_id_context.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        HTTP_REQUESTS.labels(request.method, request.url.path, "500").inc()
        raise
    finally:
        elapsed = time.perf_counter() - started
        HTTP_LATENCY.labels(request.method, request.url.path).observe(elapsed)
        request_id_context.reset(token)
    response.headers["X-Request-ID"] = request_id
    HTTP_REQUESTS.labels(request.method, request.url.path, str(response.status_code)).inc()
    return response


async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

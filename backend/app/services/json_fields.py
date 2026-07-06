from __future__ import annotations

import json
from typing import Any, Optional, Union


def parse_list(value: Union[str, list[str], None]) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [part.strip() for part in value.split(",") if part.strip()]
    return parsed if isinstance(parsed, list) else []


def dump_list(values: list[str]) -> str:
    return json.dumps(values)


def parse_json(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback

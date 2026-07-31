from __future__ import annotations

import json
from typing import Any, IO


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def json_loads_strict(value: str | bytes | bytearray, **kwargs: Any) -> Any:
    kwargs["parse_constant"] = _reject_constant
    parsed = json.loads(value, **kwargs)
    return ensure_json_finite(parsed)


def json_load_strict(stream: IO[str], **kwargs: Any) -> Any:
    kwargs["parse_constant"] = _reject_constant
    parsed = json.load(stream, **kwargs)
    return ensure_json_finite(parsed)


def ensure_json_finite(value: Any) -> Any:
    json.dumps(value, allow_nan=False)
    return value

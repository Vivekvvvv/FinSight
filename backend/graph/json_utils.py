# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
from datetime import date, datetime, time as dt_time
from typing import Any


def _json_default(value: object) -> str:
    if isinstance(value, (datetime, date, dt_time)):
        return value.isoformat()
    return str(value)


def _sanitize_non_finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _sanitize_non_finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_non_finite(item) for item in value]
    return value


def json_dumps_safe(obj: Any, **kwargs: Any) -> str:
    """
    JSON dump helper that tolerates datetime/date/time and other non-JSON-native types.
    """
    return json.dumps(
        _sanitize_non_finite(obj),
        default=_json_default,
        allow_nan=False,
        **kwargs,
    )

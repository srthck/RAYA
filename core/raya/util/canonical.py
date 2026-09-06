"""Deterministic JSON serialization.

The evidence hash is only meaningful if two independent parties can rebuild
the exact same bytes from the same logical record. Plain `json.dumps` does not
guarantee that: key order, whitespace and float formatting all vary.

We follow the shape of RFC 8785 (JSON Canonicalization Scheme):

  * object keys sorted by Unicode code point
  * no insignificant whitespace
  * UTF-8 output, with non-ASCII characters emitted literally, not escaped
  * floats rounded to a fixed precision, then emitted with Python's
    shortest-round-trip repr (deterministic for IEEE-754 doubles)
  * NaN / Infinity rejected outright -- they have no JSON representation

`FLOAT_PRECISION` is part of the evidence schema contract. Changing it changes
every hash, so it moves only with `schema_version`.
"""

from __future__ import annotations

import json
import math
from typing import Any

FLOAT_PRECISION = 6


def _normalize(value: Any) -> Any:
    """Recursively coerce a value into canonically serializable form."""
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("NaN and Infinity cannot be canonicalized")
        rounded = round(value, FLOAT_PRECISION)
        # Collapse -0.0 to 0.0 so sign of zero cannot fork the hash.
        if rounded == 0:
            return 0.0
        # An integral float stays a float; JSON has one number type and
        # round() already fixed the precision.
        return rounded
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    raise TypeError(f"cannot canonicalize type {type(value).__name__}")


def canonical_json(obj: Any) -> str:
    """Return the canonical JSON text for `obj`."""
    return json.dumps(
        _normalize(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(obj: Any) -> bytes:
    """Return the canonical UTF-8 bytes that get hashed and stored."""
    return canonical_json(obj).encode("utf-8")

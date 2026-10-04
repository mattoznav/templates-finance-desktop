"""Input checks for data coming from the interface or from CSV files."""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Iterable

from .errors import Invalid


def text(data: dict, key: str, *, required: bool = True, max_length: int = 200, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        value = default
    if not isinstance(value, str):
        raise Invalid(f"{label(key)} must be text")
    value = value.strip()
    if required and not value:
        raise Invalid(f"{label(key)} is required")
    if len(value) > max_length:
        raise Invalid(f"{label(key)} is too long (max {max_length} characters)")
    return value


def iso_date(value: Any, key: str = "date") -> str:
    if not isinstance(value, str):
        raise Invalid(f"{label(key)} is required")
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as exc:
        raise Invalid(f"{label(key)} must be a date (YYYY-MM-DD)") from exc


def month(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 7:
        raise Invalid("Month must look like YYYY-MM")
    iso_date(value + "-01", "month")
    return value


def cents(value: Any, key: str, *, minimum: int | None = None) -> int:
    """Amounts travel as integer cents, never as floats."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise Invalid(f"{label(key)} must be a whole number of cents")
    if abs(value) > 10**13:
        raise Invalid(f"{label(key)} is too large")
    if minimum is not None and value < minimum:
        raise Invalid(f"{label(key)} cannot be negative")
    return value


def positive_number(value: Any, key: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Invalid(f"{label(key)} must be a number")
    if value < 0 or (value == 0 and not allow_zero):
        raise Invalid(f"{label(key)} must be greater than zero")
    if value > 1e12:
        raise Invalid(f"{label(key)} is too large")
    return float(value)


def ident(value: Any, key: str = "id") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise Invalid(f"{label(key)} is missing")
    return value


def optional_ident(value: Any, key: str) -> int | None:
    return None if value in (None, "", 0) else ident(value, key)


def choice(value: Any, key: str, options: Iterable[str]) -> str:
    options = tuple(options)
    if value not in options:
        raise Invalid(f"{label(key)} must be one of: {', '.join(options)}")
    return value


def label(key: str) -> str:
    return key.replace("_", " ").capitalize()


def to_cents(amount: float) -> int:
    """Rounds half away from zero, like SQLite's ROUND, so Python and SQL agree."""
    return int(math.copysign(math.floor(abs(amount) * 100 + 0.5), amount))

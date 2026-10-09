"""Display, parsing and goal-checking for scorecard values.

Values are stored as plain floats (dollars are whole dollars); the measurable's
unit only affects how they're shown and typed.
"""

import math

from app.models.enums import GoalDirection, MeasurableUnit

GOAL_SYMBOLS = {
    GoalDirection.AT_LEAST.value: "≥",
    GoalDirection.AT_MOST.value: "≤",
    GoalDirection.EXACTLY.value: "=",
}
_SUFFIXES = {"k": 1e3, "m": 1e6, "b": 1e9}


def _trim(x: float, places: int = 2) -> str:
    text = f"{x:,.{places}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_value(value: float, unit: str) -> str:
    if unit == MeasurableUnit.PERCENT.value:
        return f"{_trim(value)}%"
    if unit == MeasurableUnit.CURRENCY.value:
        sign = "-" if value < 0 else ""
        a = abs(value)
        if a >= 1e6:
            return f"{sign}${_trim(a / 1e6)}M"
        if a >= 1e3:
            return f"{sign}${_trim(a / 1e3)}K"
        return f"{sign}${_trim(a)}"
    return _trim(value)


def format_goal(value: float, unit: str, direction: str) -> str:
    return f"{GOAL_SYMBOLS.get(direction, '')} {format_value(value, unit)}".strip()


def parse_value(text: str) -> float:
    """Accepts 47, 1,200, $175K, 1.5M, 80%. Raises ValueError if unreadable."""
    cleaned = text.strip().lower().replace(",", "").replace("$", "").replace("%", "")
    cleaned = cleaned.replace(" ", "")
    multiplier = 1.0
    if cleaned and cleaned[-1] in _SUFFIXES:
        multiplier = _SUFFIXES[cleaned[-1]]
        cleaned = cleaned[:-1]
    value = float(cleaned) * multiplier
    if not math.isfinite(value):
        raise ValueError(text)
    return value


def goal_met(value: float, goal: float, direction: str) -> bool:
    if direction == GoalDirection.AT_MOST.value:
        return value <= goal or math.isclose(value, goal)
    if direction == GoalDirection.EXACTLY.value:
        return math.isclose(value, goal)
    return value >= goal or math.isclose(value, goal)


def raw_value(value: float) -> str:
    """Plain, exact text for pre-filling a form field (no K/M, no commas)."""
    return f"{value:.12g}"

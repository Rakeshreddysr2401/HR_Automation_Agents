"""Date reading, and knowing when not to.

03/04/2021 has two readings and no amount of cleverness applied to that string
alone will tell you which is right. But a column is written by one system in one
convention, so a single value in the same column with a day above 12 settles the
whole column. That is the entire idea here: read the column, not the value.

When a column offers no such anchor, the agent has nothing to reason from and
must ask. This is the case the brief calls "a value it can't confidently clean",
and it is worth being strict about, because guessing produces a date that looks
perfectly valid and quietly misstates someone's tenure for years.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

NUMERIC = re.compile(r"^(\d{1,4})([-/.])(\d{1,2})\2(\d{1,4})$")
TEXT_DMY = re.compile(r"^(\d{1,2})[\s-]+([A-Za-z]{3,9})[\s-]+(\d{2,4})$")
TEXT_MDY = re.compile(r"^([A-Za-z]{3,9})[\s-]+(\d{1,2}),?[\s-]+(\d{2,4})$")

DMY = "DMY"
MDY = "MDY"
ISO = "ISO"


def _year(value: int) -> int:
    if value >= 100:
        return value
    # Two-digit years in HR data are birth dates and joining dates, never
    # futures: 95 means 1995, 05 means 2005.
    return 2000 + value if value <= 30 else 1900 + value


def _safe(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


@dataclass
class Reading:
    """One attempt at reading a single value."""

    value: str
    parsed: date | None = None
    ambiguous: bool = False
    implies: str | None = None      # DMY or MDY, when the value settles it
    error: str | None = None


def read_value(raw: str) -> Reading:
    """Read one value, reporting what it implies rather than guessing."""
    text = (raw or "").strip()
    if not text:
        return Reading(value=raw, error="empty")

    match = TEXT_DMY.match(text)
    if match:
        day, name, year = match.groups()
        month = MONTHS.get(name[:3].lower())
        if month:
            return Reading(value=raw, parsed=_safe(_year(int(year)), month, int(day)))

    match = TEXT_MDY.match(text)
    if match:
        name, day, year = match.groups()
        month = MONTHS.get(name[:3].lower())
        if month:
            return Reading(value=raw, parsed=_safe(_year(int(year)), month, int(day)))

    match = NUMERIC.match(text)
    if not match:
        return Reading(value=raw, error="unrecognised format")

    first, _sep, middle, last = match.groups()
    a, b, c = int(first), int(middle), int(last)

    # Four-digit leading group is unambiguously ISO.
    if len(first) == 4:
        return Reading(value=raw, parsed=_safe(a, b, c), implies=ISO)

    year = _year(c)
    if a > 12 and b <= 12:
        return Reading(value=raw, parsed=_safe(year, b, a), implies=DMY)
    if b > 12 and a <= 12:
        return Reading(value=raw, parsed=_safe(year, a, b), implies=MDY)
    if a > 12 and b > 12:
        return Reading(value=raw, error="neither component can be a month")
    # Both <= 12: genuinely unreadable on its own.
    return Reading(value=raw, ambiguous=True)


@dataclass
class ColumnPlan:
    """What the agent concluded about a whole date column."""

    convention: str | None = None
    anchors: int = 0                 # values that settle the convention themselves
    agreement: float = 0.0           # how consistently those anchors agree
    ambiguous_values: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    total: int = 0

    @property
    def inferred(self) -> bool:
        """True when the convention came from anchors rather than from ISO values."""
        return self.convention in (DMY, MDY) and self.anchors > 0


def analyse_column(values: list[str]) -> ColumnPlan:
    plan = ColumnPlan()
    votes = {DMY: 0, MDY: 0}
    iso = 0

    for raw in values:
        text = (raw or "").strip()
        if not text:
            continue
        plan.total += 1
        reading = read_value(text)
        if reading.implies in votes:
            votes[reading.implies] += 1
        elif reading.implies == ISO:
            iso += 1
        elif reading.ambiguous:
            plan.ambiguous_values.append(text)
        elif reading.error:
            plan.unreadable.append(text)

    anchors = votes[DMY] + votes[MDY]
    plan.anchors = anchors
    if anchors:
        winner = DMY if votes[DMY] >= votes[MDY] else MDY
        plan.convention = winner
        plan.agreement = max(votes.values()) / anchors
    elif iso and not plan.ambiguous_values:
        plan.convention = ISO
        plan.agreement = 1.0
    return plan


def apply_convention(raw: str, convention: str | None) -> tuple[date | None, str | None]:
    """Read a value under a known convention. Returns (date, error)."""
    reading = read_value(raw)
    if reading.parsed:
        return reading.parsed, None
    if reading.error:
        return None, reading.error
    if not reading.ambiguous:
        return None, "unreadable"
    if convention not in (DMY, MDY):
        return None, "ambiguous and no convention established for the column"

    match = NUMERIC.match((raw or "").strip())
    if not match:
        return None, "unreadable"
    first, _sep, middle, last = match.groups()
    a, b, year = int(first), int(middle), _year(int(last))
    parsed = _safe(year, b, a) if convention == DMY else _safe(year, a, b)
    return (parsed, None) if parsed else (None, "not a real calendar date")


def describe(convention: str | None) -> str:
    return {
        DMY: "day/month/year",
        MDY: "month/day/year",
        ISO: "year-month-day",
    }.get(convention or "", "unknown")

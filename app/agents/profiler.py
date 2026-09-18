"""Profiler: read the files, describe the columns, find the PII.

Entirely deterministic. It makes no decisions and never escalates - it produces
the evidence every other agent reasons over. Keeping this separate is what lets
the mapper reason about a *column* instead of a pile of rows, and what keeps raw
values from ever reaching a model.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app.models import ColumnProfile
from app.pii import detect_pii_kind, redact_samples

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[\d\s\-()]{9,20}$")
NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")
DATE_RE = re.compile(
    r"^(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}|"
    r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4})$"
)
ID_RE = re.compile(r"^[A-Z]{1,4}[-_]?\d{2,}$", re.IGNORECASE)


def load_sources(paths: list[str | Path]) -> dict[str, pd.DataFrame]:
    """Read every source file into a frame, keyed by file name.

    Everything is read as string: a migration must not let pandas silently
    coerce an employee code like "00123" into the number 123, or a date column
    into whatever it guesses the format to be. Type decisions belong to the
    agents, where they can be explained and escalated.
    """
    frames: dict[str, pd.DataFrame] = {}
    for raw in paths:
        path = Path(raw)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        elif suffix in (".xlsx", ".xls"):
            frame = pd.read_excel(path, dtype=str, engine="openpyxl").fillna("")
        else:
            raise ValueError(f"Unsupported file type: {path.name}")
        frame.columns = [str(c).strip() for c in frame.columns]
        frames[path.name] = frame.astype(str)
    return frames


def _infer_type(values: list[str]) -> str:
    if not values:
        return "string"
    total = len(values)

    def share(pattern: re.Pattern[str]) -> float:
        return sum(1 for v in values if pattern.match(v)) / total

    if share(EMAIL_RE) >= 0.7:
        return "email"
    if share(DATE_RE) >= 0.7:
        return "date"
    if share(PHONE_RE) >= 0.7 and any(len(re.sub(r"\D", "", v)) >= 10 for v in values):
        return "phone"
    if share(ID_RE) >= 0.7:
        return "id"
    if share(NUMERIC_RE) >= 0.9:
        return "number"
    return "string"


def profile_frame(source_file: str, frame: pd.DataFrame) -> list[ColumnProfile]:
    profiles: list[ColumnProfile] = []
    for column in frame.columns:
        series = frame[column].astype(str)
        values = [v.strip() for v in series.tolist()]
        non_empty = [v for v in values if v and v.lower() not in ("nan", "none", "null")]

        # Samples favour distinct values: five copies of "Engineering" tell the
        # mapper far less than five different departments do.
        seen: list[str] = []
        for value in non_empty:
            if value not in seen:
                seen.append(value)
            if len(seen) >= 8:
                break

        pii_kind = detect_pii_kind(column, seen)
        profiles.append(
            ColumnProfile(
                source_file=source_file,
                column=column,
                row_count=len(values),
                non_null=len(non_empty),
                cardinality=len(set(non_empty)),
                inferred_type=_infer_type(non_empty),
                samples=redact_samples(seen[:5], pii_kind),
                raw_samples=seen[:8],
                is_pii=pii_kind is not None,
                pii_kind=pii_kind,
            )
        )
    return profiles


def profile_all(frames: dict[str, pd.DataFrame]) -> list[ColumnProfile]:
    profiles: list[ColumnProfile] = []
    for name, frame in frames.items():
        profiles.extend(profile_frame(name, frame))
    return profiles

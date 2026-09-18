"""PII detection and masking.

Indian HR exports routinely carry PAN, Aadhaar, provident fund and salary
account numbers. Three rules follow from that, and they are enforced here rather
than left to discipline at each call site:

1. PII never reaches a model. The mapper sees redacted samples.
2. PII never lands in the audit trail in the clear.
3. The UI shows enough to recognise a value, never enough to use it.

The detector is deliberately conservative: it matches on value shape as well as
column name, so a PAN sitting in a column called "tax_ref" is still caught.
"""

from __future__ import annotations

import re

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "pan": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
    "aadhaar": re.compile(r"^\d{4}\s?\d{4}\s?\d{4}$"),
    "uan": re.compile(r"^\d{12}$"),
    "bank_account": re.compile(r"^\d{9,18}$"),
}

PII_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "pan": ("pan", "permanent account"),
    "aadhaar": ("aadhaar", "aadhar", "uid"),
    "uan": ("uan", "provident", "pf number", "pf no"),
    "bank_account": ("bank", "account no", "account number", "salary account", "ac no"),
}


def detect_pii_kind(column_name: str, samples: list[str]) -> str | None:
    """Identify the kind of PII in a column, by name hint or by value shape."""
    lowered = column_name.lower().replace("_", " ")
    for kind, hints in PII_NAME_HINTS.items():
        if any(h in lowered for h in hints):
            return kind

    clean = [s.strip() for s in samples if s and s.strip()]
    if not clean:
        return None
    for kind, pattern in PII_PATTERNS.items():
        hits = sum(1 for s in clean if pattern.match(s.upper()))
        if hits / len(clean) >= 0.8:
            return kind
    return None


def mask(value: str | None, kind: str | None = None) -> str:
    """Mask a value for display and logging.

    Keeps the last four characters so a human can still match a record against
    a source document, which is the only legitimate reason to look.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if len(text) <= 4:
        return "*" * len(text)
    return f"{'*' * (len(text) - 4)}{text[-4:]}"


def redact_samples(samples: list[str], kind: str | None) -> list[str]:
    if not kind:
        return samples
    return [mask(s, kind) for s in samples]


def redact_value(field_name: str, value, pii_fields: set[str]):
    """Redact a single field value if the schema marks that field as PII."""
    if field_name in pii_fields and value not in (None, ""):
        return mask(str(value))
    return value


def redact_record(fields: dict, pii_fields: set[str]) -> dict:
    return {k: redact_value(k, v, pii_fields) for k, v in fields.items()}

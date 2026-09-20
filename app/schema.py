"""Target schema loading and the format vocabulary the Validator enforces."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.settings import get_settings

# Statutory and contact formats. These are deterministic: a PAN either has the
# shape the income tax department issues or it does not, and no model is needed
# to tell the difference.
FORMATS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"),
    "phone": re.compile(r"^\+?\d[\d\s\-()]{7,17}\d$"),
    "pan": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
    "uan": re.compile(r"^\d{12}$"),
    "ifsc": re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$"),
    "bank_account": re.compile(r"^\d{9,18}$"),
}

FORMAT_HELP: dict[str, str] = {
    "email": "an address like name@company.com",
    "phone": "8 to 18 digits, optionally with a country code",
    "pan": "five letters, four digits, one letter (ABCDE1234F)",
    "uan": "exactly twelve digits",
    "ifsc": "four letters, a zero, then six characters (HDFC0001234)",
    "bank_account": "9 to 18 digits",
}


@dataclass
class TargetField:
    name: str
    type: str
    description: str
    required: bool = False
    unique: bool = False
    identity: str | None = None
    format: str | None = None
    enum: list[str] = field(default_factory=list)
    default: Any = None
    max_length: int | None = None
    pii: bool = False
    references: str | None = None

    @property
    def embed_text(self) -> str:
        """The text embedded when scoring a source column against this field.

        Name plus description, because a column header alone ("division") often
        has no lexical overlap with the target name ("department") while the
        description carries the concept.
        """
        return f"{self.name.replace('_', ' ')}. {self.description}"


@dataclass
class TargetSchema:
    entity: str
    version: int
    fields: list[TargetField]
    business_rules: list[dict[str, str]]

    @property
    def by_name(self) -> dict[str, TargetField]:
        return {f.name: f for f in self.fields}

    @property
    def required_fields(self) -> list[TargetField]:
        return [f for f in self.fields if f.required]

    @property
    def identity_fields(self) -> list[TargetField]:
        return [f for f in self.fields if f.identity == "strong"]

    @property
    def pii_fields(self) -> set[str]:
        return {f.name for f in self.fields if f.pii}

    def field(self, name: str) -> TargetField | None:
        return self.by_name.get(name)


def load_schema(path: str | Path | None = None) -> TargetSchema:
    path = Path(path or get_settings().schema_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    fields = [
        TargetField(
            name=f["name"],
            type=f["type"],
            description=" ".join(str(f.get("description", "")).split()),
            required=bool(f.get("required", False)),
            unique=bool(f.get("unique", False)),
            identity=f.get("identity"),
            format=f.get("format"),
            enum=list(f.get("enum", []) or []),
            default=f.get("default"),
            max_length=f.get("max_length"),
            pii=bool(f.get("pii", False)),
            references=f.get("references"),
        )
        for f in raw["fields"]
    ]
    return TargetSchema(
        entity=raw["entity"],
        version=int(raw.get("version", 1)),
        fields=fields,
        business_rules=list(raw.get("business_rules", []) or []),
    )


@lru_cache
def get_schema() -> TargetSchema:
    return load_schema()


def check_format(fmt: str | None, value: str) -> bool:
    if not fmt or fmt not in FORMATS:
        return True
    return bool(FORMATS[fmt].match(value.strip()))

"""Shared vocabulary for the pipeline.

These types are the contract between the agents, the store, and the UI. Keeping
them in one place is what lets every decision carry the same shape of evidence,
which is what makes the escalation queue readable at a glance.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class Disposition(str, Enum):
    """What the agent did with a decision.

    The three tiers are the whole argument of this project: most systems only
    have AUTO and ESCALATE, which forces you to choose between a silent agent
    and an exhausting one. FLAGGED is the middle: applied without blocking, but
    surfaced so the consultant can audit it in seconds.
    """

    AUTO = "auto"              # applied silently; deterministic or unambiguous
    FLAGGED = "flagged"        # applied, but surfaced because it was inferred
    ESCALATED = "escalated"    # blocked pending a human decision
    IGNORED = "ignored"        # deliberately dropped (confident "no match")


class EscalationType(str, Enum):
    COLUMN_MAPPING = "column_mapping"
    DATE_CONVENTION = "date_convention"
    ENUM_VALUE = "enum_value"
    DUPLICATE_SUSPECTED = "duplicate_suspected"
    REHIRE_SUSPECTED = "rehire_suspected"
    VALIDATION_FAILED = "validation_failed"
    HIERARCHY_ORPHAN = "hierarchy_orphan"
    HIERARCHY_CYCLE = "hierarchy_cycle"
    PUSH_REJECTED = "push_rejected"
    BATCH_ANOMALY = "batch_anomaly"


class EscalationStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class Actor(str, Enum):
    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"


@dataclass
class ColumnProfile:
    """What the agent knows about one source column before it decides anything.

    This - not the raw rows - is what reaches the LLM. Samples are redacted, so
    PII never leaves the process.
    """

    source_file: str
    column: str
    row_count: int
    non_null: int
    cardinality: int
    inferred_type: str                       # string | number | date | email | phone | id
    samples: list[str] = field(default_factory=list)          # redacted
    raw_samples: list[str] = field(default_factory=list)      # never leaves the process
    is_pii: bool = False
    pii_kind: str | None = None

    @property
    def null_rate(self) -> float:
        return 0.0 if not self.row_count else 1 - (self.non_null / self.row_count)

    def for_llm(self) -> dict[str, Any]:
        return {
            "column_name": self.column,
            "inferred_type": self.inferred_type,
            "null_rate": round(self.null_rate, 2),
            "distinct_values": self.cardinality,
            "sample_values": self.samples[:5],
        }


@dataclass
class MappingCandidate:
    target_field: str
    score: float
    embedding_score: float
    fuzzy_score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_field": self.target_field,
            "score": round(self.score, 3),
            "embedding_score": round(self.embedding_score, 3),
            "fuzzy_score": round(self.fuzzy_score, 3),
        }


@dataclass
class ColumnMapping:
    source_file: str
    column: str
    target_field: str | None
    disposition: Disposition
    confidence: float
    margin: float
    rationale: str
    candidates: list[MappingCandidate] = field(default_factory=list)
    transform: str | None = None             # e.g. "split_full_name"
    provenance: str = "scored"               # scored | memory | human

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "column": self.column,
            "target_field": self.target_field,
            "disposition": self.disposition.value,
            "confidence": round(self.confidence, 3),
            "margin": round(self.margin, 3),
            "rationale": self.rationale,
            "transform": self.transform,
            "provenance": self.provenance,
            "candidates": [c.as_dict() for c in self.candidates[:4]],
        }


@dataclass
class Escalation:
    """One thing the agent refuses to guess about.

    `evidence` is deliberately free-form per type, but every type fills in
    enough for the UI to render a decision in one glance: what it saw, what the
    options are, and how many records ride on the answer.
    """

    run_id: str
    type: EscalationType
    title: str
    question: str
    # A stable, semantic identifier for *what is being asked*, independent of
    # this run. Escalation ids are regenerated whenever the pipeline re-runs;
    # subjects are not, which is what lets a human answer survive a re-run and
    # be carried into the next client's migration as remembered knowledge.
    # Shapes: "contest:<file>:<field>", "map:<file>:<column>",
    # "date:<file>:<column>", "enum:<field>:<value>", "identity:<a>|<b>",
    # "record:<key>", "manager:<email>", "cycle:<a>|<b>", "batch:<run>".
    subject: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    options: list[dict[str, Any]] = field(default_factory=list)
    affected_records: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: _uid("esc"))
    status: EscalationStatus = EscalationStatus.OPEN
    resolution: dict[str, Any] | None = None
    created_at: str = field(default_factory=_now)
    resolved_at: str | None = None

    @property
    def affected_count(self) -> int:
        return len(self.affected_records)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "type": self.type.value,
            "subject": self.subject,
            "title": self.title,
            "question": self.question,
            "evidence": self.evidence,
            "options": self.options,
            "affected_records": self.affected_records,
            "affected_count": self.affected_count,
            "status": self.status.value,
            "resolution": self.resolution,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


@dataclass
class AuditEntry:
    run_id: str
    actor: Actor
    action: str
    entity: str                 # record key, or "column:<file>:<name>"
    rationale: str
    before: Any = None
    after: Any = None
    disposition: Disposition | None = None
    id: str = field(default_factory=lambda: _uid("aud"))
    at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "at": self.at,
            "actor": self.actor.value,
            "action": self.action,
            "entity": self.entity,
            "before": self.before,
            "after": self.after,
            "rationale": self.rationale,
            "disposition": self.disposition.value if self.disposition else None,
        }


@dataclass
class TargetRecord:
    """One employee, assembled from one or more source rows."""

    key: str                                   # stable identity key
    fields: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)      # "file.csv#12"
    errors: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)   # escalation ids
    push_status: str = "pending"               # pending|success|failed|rejected|rolled_back|skipped
    push_detail: str = ""
    attempts: int = 0

    @property
    def ready(self) -> bool:
        return not self.errors and not self.blocked_by

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "fields": self.fields,
            "sources": self.sources,
            "errors": self.errors,
            "blocked_by": self.blocked_by,
            "push_status": self.push_status,
            "push_detail": self.push_detail,
            "attempts": self.attempts,
            "ready": self.ready,
        }

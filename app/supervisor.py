"""Supervisor: the judgment no single-record agent can make.

Three jobs, all of which are about the queue as a whole rather than any one
decision in it.

**Linking questions to records.** An enum question about `Engg` already covers the
two records whose department it blanked. Without that link the validator would ask
again about the same two records - "department is required but empty" - and the
consultant would answer one question twice. A record waiting on a question already
in the queue is not separately broken.

**Knowing which fields are pending.** A required field left empty because its column
mapping is still contested is not a validation failure.

**Calling a halt.** Per-record judgment cannot detect a wrong premise. If a third of
the file is escalating, or almost nothing maps to the schema, the likely truth is
that this is the wrong export - and the useful response is one question rather than
two hundred.
"""

from __future__ import annotations

from collections import defaultdict

from app import policy
from app.models import (
    ColumnMapping,
    Disposition,
    Escalation,
    EscalationType,
    TargetRecord,
)

# Questions about a column stand for every row beneath it; questions about a
# record stand only for that record. Only the latter say anything about how much
# of the dataset is actually in trouble.
COLUMN_LEVEL = {
    EscalationType.COLUMN_MAPPING,
    EscalationType.DATE_CONVENTION,
    EscalationType.ENUM_VALUE,
}
RECORD_LEVEL = {
    EscalationType.VALIDATION_FAILED,
    EscalationType.DUPLICATE_SUSPECTED,
    EscalationType.REHIRE_SUSPECTED,
    EscalationType.HIERARCHY_ORPHAN,
    EscalationType.HIERARCHY_CYCLE,
    EscalationType.PUSH_REJECTED,
}


def pending_fields(
    mappings: list[ColumnMapping], blocked_by_file: dict[str, set[str]] | None = None
) -> set[str]:
    """Target fields whose source is still awaiting a decision."""
    pending: set[str] = set()
    for mapping in mappings:
        if mapping.disposition is not Disposition.ESCALATED:
            continue
        # The contested field, plus the runner-up it is contested against.
        pending.update(c.target_field for c in mapping.candidates[:2])
    for fields in (blocked_by_file or {}).values():
        pending.update(fields)
    return pending


def link_to_records(
    escalations: list[Escalation], records: list[TargetRecord]
) -> dict[str, set[str]]:
    """Map each record key to the fields already under question for it.

    Escalations raised before records exist refer to source rows
    ("payroll.xlsx#14"); records refer to themselves by key. This resolves one
    into the other so the validator does not re-ask what is already queued.
    """
    by_source: dict[str, list[TargetRecord]] = defaultdict(list)
    for record in records:
        for source in record.sources:
            by_source[source].append(record)
    by_key = {record.key: record for record in records}

    pending: dict[str, set[str]] = defaultdict(set)
    for escalation in escalations:
        field = str(escalation.evidence.get("target_field") or "")
        if not field:
            continue
        for reference in escalation.affected_records:
            targets = by_source.get(reference) or (
                [by_key[reference]] if reference in by_key else []
            )
            for record in targets:
                pending[record.key].add(field)
    return dict(pending)


def attach_blocks(escalations: list[Escalation], records: list[TargetRecord]) -> None:
    """Record which open questions block which records, for the UI and the loader."""
    by_source: dict[str, list[TargetRecord]] = defaultdict(list)
    for record in records:
        record.blocked_by = []
        for source in record.sources:
            by_source[source].append(record)
    by_key = {record.key: record for record in records}

    for escalation in escalations:
        for reference in escalation.affected_records:
            targets = by_source.get(reference) or (
                [by_key[reference]] if reference in by_key else []
            )
            for record in targets:
                if escalation.id not in record.blocked_by:
                    record.blocked_by.append(escalation.id)


def evaluate_batch(
    escalations: list[Escalation],
    records: list[TargetRecord],
    mappings: list[ColumnMapping],
    run_id: str,
) -> Escalation | None:
    """Is this run worth continuing, or is the premise wrong?"""
    mapped = sum(
        1
        for m in mappings
        if m.target_field and m.disposition in (Disposition.AUTO, Disposition.FLAGGED)
    )
    coverage = mapped / len(mappings) if mappings else 0.0

    if mappings and coverage < policy.MIN_MAPPING_COVERAGE:
        return Escalation(
            run_id=run_id,
            type=EscalationType.BATCH_ANOMALY,
            subject="batch:coverage",
            title="These files do not look like employee data",
            question=(
                f"Only {mapped} of {len(mappings)} columns ({coverage:.0%}) resemble anything "
                f"in the employee schema. Rather than raise a question per column, it is "
                f"worth checking whether this is the right export - the shape suggests a "
                f"different entity altogether."
            ),
            evidence={
                "mapped_columns": mapped,
                "total_columns": len(mappings),
                "coverage": round(coverage, 3),
                "threshold": policy.MIN_MAPPING_COVERAGE,
                "unmapped": [m.column for m in mappings if not m.target_field][:20],
            },
            options=[
                {"value": "abort", "label": "Stop - wrong file", "detail": "discard this run"},
                {
                    "value": "continue",
                    "label": "Continue anyway",
                    "detail": "map what little matches",
                },
            ],
        )

    blocked = {
        key
        for escalation in escalations
        if escalation.type in RECORD_LEVEL
        for key in escalation.affected_records
    }
    tripped, reason = policy.should_trip_breaker(
        escalated_records=len(blocked),
        total_records=len(records),
        total_escalations=len(escalations),
    )
    if not tripped:
        return None

    return Escalation(
        run_id=run_id,
        type=EscalationType.BATCH_ANOMALY,
        subject="batch:rate",
        title="Too much of this run needs a human",
        question=(
            f"{reason} Rather than work through the queue one card at a time, it is worth "
            f"confirming the inputs first."
        ),
        evidence={
            "blocked_records": len(blocked),
            "total_records": len(records),
            "total_escalations": len(escalations),
            "rate_threshold": policy.CIRCUIT_BREAKER_RATE,
            "by_type": {
                escalation_type.value: sum(
                    1 for e in escalations if e.type is escalation_type
                )
                for escalation_type in EscalationType
                if any(e.type is escalation_type for e in escalations)
            },
        },
        options=[
            {"value": "abort", "label": "Stop and check the files", "detail": "discard this run"},
            {
                "value": "continue",
                "label": "Continue - the data really is this messy",
                "detail": "work through the queue",
            },
        ],
    )

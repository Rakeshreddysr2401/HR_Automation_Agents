"""Validator: decide whether a record is loadable, and repair it once if not.

Two ideas carry this agent.

**One repair attempt, then ask.** The second failure is the signal. The first tells
you a value was messy, which is ordinary and mechanical. The second tells you the
mess is not mechanical, and at that point more attempts are just a slower way of
reaching the same human.

**Pending is not invalid.** A required field left empty because the column feeding it
is still awaiting a mapping decision is not a broken record - it is a record waiting
on a question already in the queue. Reporting those as validation failures would
bury the real ones and trip the circuit breaker on a file that is completely fine.

The hierarchy checks are here because they are the failures that column-level
validation cannot see. Every `manager_email` is a perfectly valid email address; the
problem is that one of them points at nobody, and another two point at each other.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Callable

from app import policy
from app.models import (
    Actor,
    AuditEntry,
    Disposition,
    Escalation,
    EscalationType,
    TargetRecord,
)
from app.pii import redact_value
from app.schema import FORMAT_HELP, TargetSchema, check_format

Emit = Callable[[str], None]

MIN_AGE_AT_JOINING = 15
MAX_AGE_AT_JOINING = 75


def _as_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _years_between(start: date, end: date) -> float:
    return (end - start).days / 365.25


def check(
    record: TargetRecord,
    schema: TargetSchema,
    pending: set[str],
    record_pending: set[str] | None = None,
) -> list[str]:
    """Every reason this record cannot be loaded, in human words.

    `pending` are fields whose column mapping is still contested dataset-wide;
    `record_pending` are fields already under question for this specific record,
    such as a department blanked by an enum value awaiting a decision. Neither
    counts as a validation failure - the question is already in the queue, and
    asking it twice in two different shapes is how a review queue becomes noise.
    """
    issues: list[str] = []
    fields = record.fields
    waiting = pending | (record_pending or set())

    for target in schema.fields:
        value = str(fields.get(target.name, "") or "").strip()

        if not value:
            if target.required and target.name not in waiting:
                issues.append(f"{target.name} is required but empty")
            continue

        if target.format and not check_format(target.format, value):
            issues.append(
                f"{target.name} is not {FORMAT_HELP.get(target.format, 'in the expected format')}"
            )
        if target.enum and value not in target.enum:
            issues.append(f"{target.name} '{value}' is not one of {', '.join(target.enum)}")
        if target.max_length and len(value) > target.max_length:
            issues.append(
                f"{target.name} is {len(value)} characters, longer than the {target.max_length} allowed"
            )

    if "status" in waiting or "date_of_exit" in waiting:
        return issues

    dob = _as_date(fields.get("date_of_birth"))
    doj = _as_date(fields.get("date_of_joining"))
    exit_date = _as_date(fields.get("date_of_exit"))

    if dob and doj:
        if doj <= dob:
            issues.append("date_of_joining is on or before date_of_birth")
        else:
            age = _years_between(dob, doj)
            if not MIN_AGE_AT_JOINING <= age <= MAX_AGE_AT_JOINING:
                issues.append(
                    f"age at joining works out to {age:.0f} years, outside the plausible "
                    f"{MIN_AGE_AT_JOINING}-{MAX_AGE_AT_JOINING}"
                )
    if exit_date and doj and exit_date < doj:
        issues.append("date_of_exit is before date_of_joining")
    if str(fields.get("status", "")).strip() == "Inactive" and not exit_date:
        issues.append("status is Inactive but no date_of_exit is set")

    return issues


def repair(record: TargetRecord, schema: TargetSchema) -> list[tuple[str, str, str, str]]:
    """One deterministic pass. Returns (field, before, after, why) for each change.

    Only mechanical corrections belong here. Anything that would invent
    information - guessing a missing designation, inferring a country code onto a
    bare phone number - is a decision, and decisions go to the human.
    """
    changes: list[tuple[str, str, str, str]] = []
    fields = record.fields

    for name in ("pan", "ifsc"):
        value = str(fields.get(name, "") or "")
        fixed = value.upper().replace(" ", "").replace("-", "")
        if fixed != value and fixed:
            fields[name] = fixed
            changes.append((name, value, fixed, "statutory identifiers are upper case"))

    for name in ("uan", "bank_account"):
        value = str(fields.get(name, "") or "")
        fixed = "".join(ch for ch in value if ch.isdigit())
        if fixed != value and fixed:
            fields[name] = fixed
            changes.append((name, value, fixed, "kept the digits only"))

    # An exit date is unambiguous evidence that someone has left, so a record
    # carrying one while still marked Active is a contradiction with exactly one
    # sensible reading. The reverse - Inactive with no exit date - has no such
    # reading, and is escalated instead.
    if _as_date(fields.get("date_of_exit")) and str(fields.get("status", "")) == "Active":
        fields["status"] = "Inactive"
        changes.append(
            ("status", "Active", "Inactive", "an exit date is recorded, so they have left")
        )

    for target in schema.fields:
        if target.default is not None and not str(fields.get(target.name, "") or "").strip():
            fields[target.name] = target.default
            changes.append(
                (target.name, "", str(target.default), f"schema default for {target.name}")
            )

    return changes


def validate(
    records: list[TargetRecord],
    schema: TargetSchema,
    run_id: str,
    pending_fields: set[str] | None = None,
    pending_per_record: dict[str, set[str]] | None = None,
    decisions: dict[str, Any] | None = None,
    emit: Emit = lambda _: None,
) -> tuple[list[Escalation], list[AuditEntry]]:
    pending = pending_fields or set()
    per_record = pending_per_record or {}
    decisions = decisions or {}
    pii_fields = schema.pii_fields
    escalations: list[Escalation] = []
    audit: list[AuditEntry] = []

    if pending:
        emit(
            f"Holding {', '.join(sorted(pending))} as pending - the columns feeding "
            f"them are still awaiting a decision"
        )

    # Corrections and reassignments a consultant supplied are applied before
    # validation runs, so the record is judged in its corrected state rather than
    # being reported as broken and then patched.
    for record in records:
        answer = decisions.get(f"record:{record.key}")
        if isinstance(answer, dict) and answer.get("action") == "edit":
            for name, value in (answer.get("fields") or {}).items():
                before = record.fields.get(name, "")
                if str(before) == str(value):
                    continue
                record.fields[name] = value
                audit.append(
                    AuditEntry(
                        run_id=run_id,
                        actor=Actor.HUMAN,
                        action="correct_value",
                        entity=record.key,
                        # A consultant retyping a PAN to fix a validation failure
                        # must not thereby write it into the audit trail in clear.
                        before=redact_value(name, before, pii_fields),
                        after=redact_value(name, value, pii_fields),
                        disposition=Disposition.AUTO,
                        rationale="Supplied by a consultant resolving a validation failure.",
                    )
                )
        elif answer == "skip":
            record.push_status = "skipped"
            record.errors = []
            audit.append(
                AuditEntry(
                    run_id=run_id,
                    actor=Actor.HUMAN,
                    action="skip_record",
                    entity=record.key,
                    before=None,
                    after="skipped",
                    disposition=Disposition.AUTO,
                    rationale="A consultant chose not to migrate this record.",
                )
            )

        manager_answer = decisions.get(
            f"manager:{str(record.fields.get('manager_email', '') or '').strip().lower()}"
        )
        if manager_answer == "clear":
            record.fields["manager_email"] = ""
        elif isinstance(manager_answer, str) and manager_answer.startswith("reassign:"):
            record.fields["manager_email"] = manager_answer.split(":", 1)[1]

        if decisions.get(f"cycle-clear:{record.key}"):
            record.fields["manager_email"] = ""

    repaired_count = 0
    for record in records:
        if record.push_status == "skipped":
            continue
        waiting = per_record.get(record.key, set())
        issues = check(record, schema, pending, waiting)
        if not issues:
            record.errors = []
            continue

        changes = repair(record, schema)
        if changes:
            repaired_count += 1
            for name, before, after, why in changes:
                audit.append(
                    AuditEntry(
                        run_id=run_id,
                        actor=Actor.AGENT,
                        action="repair_value",
                        entity=record.key,
                        before=redact_value(name, before, pii_fields),
                        after=redact_value(name, after, pii_fields),
                        disposition=Disposition.AUTO,
                        rationale=why,
                    )
                )

        issues = check(record, schema, pending, waiting)
        record.errors = issues
        if not issues:
            continue

        escalations.append(
            _validation_escalation(run_id, record, issues, schema, pending | waiting)
        )

    emit(
        f"Validated {len(records)} records - repaired {repaired_count}, "
        f"{len(escalations)} still need a decision"
    )

    hierarchy, hierarchy_audit = check_hierarchy(
        records, schema, run_id, pending, decisions, emit
    )
    escalations.extend(hierarchy)
    audit.extend(hierarchy_audit)
    return escalations, audit


def _validation_escalation(
    run_id: str,
    record: TargetRecord,
    issues: list[str],
    schema: TargetSchema,
    pending: set[str],
) -> Escalation:
    """A card carrying the record, what is wrong, and an editable field list."""
    faulty = [
        target.name
        for target in schema.fields
        if any(issue.startswith(f"{target.name} ") for issue in issues)
    ]
    if not faulty:
        faulty = [t.name for t in schema.required_fields if t.name not in pending]

    pii_fields = schema.pii_fields
    name = f"{record.fields.get('first_name', '')} {record.fields.get('last_name', '')}".strip()
    return Escalation(
        run_id=run_id,
        type=EscalationType.VALIDATION_FAILED,
        subject=f"record:{record.key}",
        title=f"{name or record.key} cannot be loaded",
        question=(
            f"This record still fails after an automatic repair pass, so the remaining "
            f"problems are not mechanical: {'; '.join(issues)}."
        ),
        evidence={
            "record_key": record.key,
            "name": name,
            "employee_code": record.fields.get("employee_code"),
            "issues": issues,
            "sources": record.sources,
            "editable_fields": faulty,
            "record": {
                key: ("****" if key in pii_fields and value else value)
                for key, value in record.fields.items()
                if not key.startswith("_")
            },
        },
        options=[
            {"value": "edit", "label": "Correct the values", "detail": "supply what is missing"},
            {"value": "skip", "label": "Skip this record", "detail": "do not migrate it"},
        ],
        affected_records=[record.key],
    )


def check_hierarchy(
    records: list[TargetRecord],
    schema: TargetSchema,
    run_id: str,
    pending: set[str],
    decisions: dict[str, Any] | None = None,
    emit: Emit = lambda _: None,
) -> tuple[list[Escalation], list[AuditEntry]]:
    """Reporting lines must resolve inside the dataset, and must not loop."""
    if "work_email" in pending or "manager_email" in pending:
        emit("Skipping reporting-line checks until the email columns are confirmed")
        return [], [
            AuditEntry(
                run_id=run_id,
                actor=Actor.AGENT,
                action="defer_hierarchy_check",
                entity="dataset",
                before=None,
                after=None,
                disposition=Disposition.FLAGGED,
                rationale=(
                    "Manager resolution needs the full set of work emails, and a column "
                    "feeding one is still awaiting a decision. Deferred rather than run "
                    "against an incomplete set, which would report false orphans."
                ),
            )
        ]

    known: dict[str, TargetRecord] = {}
    for record in records:
        email = str(record.fields.get("work_email", "") or "").strip().lower()
        if email:
            known[email] = record

    escalations: list[Escalation] = []

    # Orphans, grouped by the manager who is missing rather than by report, so a
    # departed manager with nine reports is one question and not nine.
    orphans: dict[str, list[TargetRecord]] = defaultdict(list)
    for record in records:
        manager = str(record.fields.get("manager_email", "") or "").strip().lower()
        if manager and manager not in known:
            orphans[manager].append(record)

    for manager, reports in orphans.items():
        if (decisions or {}).get(f"manager:{manager}"):
            continue
        emit(f"{manager} is nobody's record but {len(reports)} report to them - asking")
        escalations.append(
            Escalation(
                run_id=run_id,
                type=EscalationType.HIERARCHY_ORPHAN,
                subject=f"manager:{manager}",
                title=f"Who do {len(reports)} people report to?",
                question=(
                    f"{len(reports)} record(s) report to '{manager}', but no employee in "
                    f"these files has that work email. Either the manager is missing from "
                    f"the export, or they have left and the reporting line was never "
                    f"reassigned. Loading this as-is leaves the reporting tree broken."
                ),
                evidence={
                    "missing_manager": manager,
                    "reports": [
                        {
                            "key": r.key,
                            "name": f"{r.fields.get('first_name', '')} {r.fields.get('last_name', '')}".strip(),
                            "employee_code": r.fields.get("employee_code"),
                            "department": r.fields.get("department"),
                        }
                        for r in reports
                    ],
                },
                options=[
                    {
                        "value": "clear",
                        "label": "Clear the reporting line",
                        "detail": "load these records with no manager",
                    },
                    {
                        "value": "reassign",
                        "label": "Reassign to another manager",
                        "detail": "supply a work email",
                    },
                ],
                affected_records=[r.key for r in reports],
            )
        )

    escalations.extend(_detect_cycles(records, known, run_id, decisions or {}, emit))
    return escalations, []


def _detect_cycles(
    records: list[TargetRecord],
    known: dict[str, TargetRecord],
    run_id: str,
    decisions: dict[str, Any],
    emit: Emit,
) -> list[Escalation]:
    """Find reporting loops. Each loop is reported once, not once per member."""
    seen_cycles: set[frozenset[str]] = set()
    out: list[Escalation] = []

    for record in records:
        path: list[str] = []
        seen: set[str] = set()
        current = record
        while current is not None:
            email = str(current.fields.get("work_email", "") or "").strip().lower()
            if not email:
                break
            if email in seen:
                cycle = path[path.index(email):]
                signature = frozenset(cycle)
                if len(cycle) > 1 and signature not in seen_cycles:
                    seen_cycles.add(signature)
                    members = [known[e] for e in cycle if e in known]
                    subject = "cycle:" + "|".join(sorted(m.key for m in members))
                    if decisions.get(subject):
                        break
                    names = [
                        f"{m.fields.get('first_name', '')} {m.fields.get('last_name', '')}".strip()
                        for m in members
                    ]
                    emit(f"Reporting loop: {' -> '.join(names)} - asking")
                    out.append(
                        Escalation(
                            run_id=run_id,
                            type=EscalationType.HIERARCHY_CYCLE,
                            subject=subject,
                            title=f"{' and '.join(names)} report to each other",
                            question=(
                                f"The reporting chain loops: {' reports to '.join(names)} "
                                f"reports back to {names[0]}. An HRMS cannot store a "
                                f"circular hierarchy, and picking which line to cut changes "
                                f"who approves whose leave, so it is not the agent's call."
                            ),
                            evidence={
                                "cycle": [
                                    {
                                        "key": m.key,
                                        "name": f"{m.fields.get('first_name', '')} {m.fields.get('last_name', '')}".strip(),
                                        "employee_code": m.fields.get("employee_code"),
                                        "work_email": m.fields.get("work_email"),
                                        "manager_email": m.fields.get("manager_email"),
                                        "designation": m.fields.get("designation"),
                                    }
                                    for m in members
                                ],
                            },
                            options=[
                                {
                                    "value": f"cycle-clear:{m.key}",
                                    "label": f"Clear {m.fields.get('first_name', '')}'s manager",
                                    "detail": "breaks the loop there",
                                }
                                for m in members
                            ],
                            affected_records=[m.key for m in members],
                        )
                    )
                break
            seen.add(email)
            path.append(email)
            manager = str(current.fields.get("manager_email", "") or "").strip().lower()
            current = known.get(manager) if manager else None

    return out

"""Identity Resolver: decide which rows describe the same human.

The asymmetry here is severe and drives the whole policy. A duplicate that
survives is visible - two rows, one person, someone notices and deletes one. A
wrong merge is not: two people become one, and the record that disappeared took
its salary, its leave balance and its reporting line with it. So the agent
merges only on identifiers that are unique by construction, and asks about
everything softer.

The case worth dwelling on is the rehire. Someone who left in 2019 and rejoined
in 2022 has two employee codes and one PAN, which is indistinguishable from a
duplicate to any generic dedup routine. Merging them looks like tidying up and
actually destroys the service history that gratuity and tenure are computed
from. The agent cannot tell these apart from the data alone - and neither can a
consultant, without asking HR - so it surfaces the pair and says why it matters.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable

from rapidfuzz import fuzz

from app import policy
from app.models import (
    Actor,
    AuditEntry,
    Disposition,
    Escalation,
    EscalationType,
    TargetRecord,
)
from app.schema import TargetSchema

Emit = Callable[[str], None]
PUNCT = re.compile(r"[^a-z]")


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _name_of(row: dict[str, Any]) -> str:
    return f"{_norm(row.get('first_name'))} {_norm(row.get('last_name'))}".strip()


def _completeness(row: dict[str, Any]) -> int:
    return sum(1 for key, value in row.items() if not key.startswith("_") and value)


def _abbreviates(a: str, b: str) -> bool:
    """Is one surname a shortened form of the other? "Q." against "Qureshi"."""
    a_clean, b_clean = PUNCT.sub("", a), PUNCT.sub("", b)
    if not a_clean or not b_clean or a_clean == b_clean:
        return False
    shorter, longer = sorted([a_clean, b_clean], key=len)
    return len(shorter) <= 3 and longer.startswith(shorter)


def resolve(
    rows: list[dict[str, Any]],
    schema: TargetSchema,
    run_id: str,
    decisions: dict[str, Any] | None = None,
    emit: Emit = lambda _: None,
) -> tuple[list[TargetRecord], list[Escalation], list[AuditEntry]]:
    decisions = decisions or {}
    escalations: list[Escalation] = []
    audit: list[AuditEntry] = []

    # Group on identifiers that are unique by construction. Work email is issued
    # once per person per system; PAN is issued once per person nationally.
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        email = _norm(row.get("work_email"))
        code = _norm(row.get("employee_code"))
        key = f"email:{email}" if email else (f"code:{code}" if code else f"row:{row['_source']}")
        groups[key].append(row)

    records: list[TargetRecord] = []
    for key, members in groups.items():
        record = _merge(members, key, run_id, audit, emit)
        records.append(record)

    escalations.extend(_detect_shared_pan(records, run_id, decisions, audit, emit))
    escalations.extend(_detect_near_duplicates(records, run_id, decisions, audit, emit))
    records = _apply_merges(records, decisions, run_id, audit)

    merged = sum(1 for record in records if len(record.sources) > 1)
    emit(
        f"Reconciled {len(rows)} rows into {len(records)} people "
        f"({merged} merged from multiple sources)"
    )
    return records, escalations, audit


def _merge(
    members: list[dict[str, Any]],
    key: str,
    run_id: str,
    audit: list[AuditEntry],
    emit: Emit,
) -> TargetRecord:
    """Combine rows known to be the same person, preferring completeness."""
    ordered = sorted(members, key=_completeness, reverse=True)
    fields: dict[str, Any] = {}
    conflicts: list[str] = []

    for row in ordered:
        for column, value in row.items():
            if column.startswith("_") or value in (None, ""):
                continue
            if column not in fields:
                fields[column] = value
            elif _norm(fields[column]) != _norm(value):
                conflicts.append(f"{column}: kept '{fields[column]}', also saw '{value}'")

    record = TargetRecord(
        key=str(fields.get("employee_code") or fields.get("work_email") or key),
        fields=fields,
        sources=[row["_source"] for row in ordered],
    )
    for row in ordered:
        record.errors.extend(row.get("_issues", []))

    if len(ordered) > 1:
        basis = "the same work email" if key.startswith("email:") else "the same employee code"
        audit.append(
            AuditEntry(
                run_id=run_id,
                actor=Actor.AGENT,
                action="merge_duplicate",
                entity=record.key,
                before=" + ".join(record.sources),
                after=record.key,
                disposition=Disposition.AUTO,
                rationale=(
                    f"{len(ordered)} rows share {basis}, which is unique per person, so they "
                    f"are the same record. Kept the most complete value for each field."
                    + (f" Conflicting values noted: {'; '.join(conflicts)}." if conflicts else "")
                ),
            )
        )
    return record


def _pair_subject(prefix: str, a: str, b: str) -> str:
    """Order-independent key, so the same pair is the same question either way."""
    first, second = sorted([a, b])
    return f"{prefix}:{first}|{second}"


def _apply_merges(
    records: list[TargetRecord],
    decisions: dict[str, Any],
    run_id: str,
    audit: list[AuditEntry],
) -> list[TargetRecord]:
    """Carry out merges a consultant authorised, dropping the absorbed record."""
    keep_targets: dict[str, str] = {}
    for key, answer in decisions.items():
        if not (key.startswith(("identity:", "rehire:")) and str(answer).startswith("merge:")):
            continue
        winner = str(answer).split(":", 1)[1]
        _, pair = key.split(":", 1)
        for member in pair.split("|"):
            if member != winner:
                keep_targets[member] = winner

    if not keep_targets:
        return records

    by_key = {record.key: record for record in records}
    survivors: list[TargetRecord] = []
    for record in records:
        winner_key = keep_targets.get(record.key)
        if winner_key and winner_key in by_key:
            winner = by_key[winner_key]
            for column, value in record.fields.items():
                if value and not winner.fields.get(column):
                    winner.fields[column] = value
            winner.sources.extend(record.sources)
            audit.append(
                AuditEntry(
                    run_id=run_id,
                    actor=Actor.HUMAN,
                    action="merge_records",
                    entity=winner.key,
                    before=record.key,
                    after=winner.key,
                    disposition=Disposition.AUTO,
                    rationale=(
                        f"A consultant confirmed {record.key} and {winner.key} are the same "
                        f"person. Merged, keeping values already present on {winner.key}."
                    ),
                )
            )
            continue
        survivors.append(record)
    return survivors


def _detect_shared_pan(
    records: list[TargetRecord],
    run_id: str,
    decisions: dict[str, Any],
    audit: list[AuditEntry],
    emit: Emit,
) -> list[Escalation]:
    """One PAN across two employee codes: a rehire, or a genuine duplicate."""
    by_pan: dict[str, list[TargetRecord]] = defaultdict(list)
    for record in records:
        pan = _norm(record.fields.get("pan"))
        if pan:
            by_pan[pan].append(record)

    out: list[Escalation] = []
    for pan, group in by_pan.items():
        codes = {_norm(r.fields.get("employee_code")) for r in group}
        if len(group) < 2 or len(codes) < 2:
            continue
        ordered = sorted(group, key=lambda r: _norm(r.fields.get("date_of_joining")))
        earlier, later = ordered[0], ordered[-1]
        subject = _pair_subject("rehire", earlier.key, later.key)
        answer = decisions.get(subject)
        if answer:
            audit.append(
                AuditEntry(
                    run_id=run_id,
                    actor=Actor.HUMAN,
                    action="resolve_rehire",
                    entity=f"{earlier.key} + {later.key}",
                    before="one PAN under two employee codes",
                    after="kept separate" if answer == "separate" else str(answer),
                    disposition=Disposition.AUTO,
                    rationale=(
                        "A consultant confirmed this is a rehire, so both spells of service "
                        "are preserved."
                        if answer == "separate"
                        else "A consultant confirmed these are one record duplicated."
                    ),
                )
            )
            continue
        emit(f"Same PAN under two employee codes ({', '.join(sorted(codes))}) - asking")
        out.append(
            Escalation(
                run_id=run_id,
                type=EscalationType.REHIRE_SUSPECTED,
                subject=subject,
                title=f"Is {_name_of(later.fields).title()} a rehire or a duplicate?",
                question=(
                    f"Two records share one PAN but carry different employee codes "
                    f"({', '.join(sorted(codes))}). That is what a rehire looks like, and "
                    f"also what a duplicate looks like. Merging a rehire destroys the earlier "
                    f"service history that gratuity and tenure are calculated from, so this "
                    f"one is not safe to decide from the data."
                ),
                evidence={
                    "shared_pan": f"****{pan[-4:].upper()}",
                    "records": [
                        {
                            "key": record.key,
                            "employee_code": record.fields.get("employee_code"),
                            "name": _name_of(record.fields).title(),
                            "work_email": record.fields.get("work_email"),
                            "date_of_joining": record.fields.get("date_of_joining"),
                            "date_of_exit": record.fields.get("date_of_exit"),
                            "status": record.fields.get("status"),
                            "sources": record.sources,
                        }
                        for record in ordered
                    ],
                },
                options=[
                    {
                        "value": "separate",
                        "label": "Keep both - this is a rehire",
                        "detail": "preserves the earlier spell of service",
                    },
                    {
                        "value": f"merge:{later.key}",
                        "label": f"Merge into {later.key}",
                        "detail": "same person, duplicated record",
                    },
                    {
                        "value": f"merge:{earlier.key}",
                        "label": f"Merge into {earlier.key}",
                        "detail": "same person, duplicated record",
                    },
                ],
                affected_records=[record.key for record in ordered],
            )
        )
    return out


def _detect_near_duplicates(
    records: list[TargetRecord],
    run_id: str,
    decisions: dict[str, Any],
    audit: list[AuditEntry],
    emit: Emit,
) -> list[Escalation]:
    """Same birthday, same first name, surname that might be the same surname."""
    by_dob: dict[str, list[TargetRecord]] = defaultdict(list)
    for record in records:
        dob = _norm(record.fields.get("date_of_birth"))
        if dob:
            by_dob[dob].append(record)

    out: list[Escalation] = []
    for dob, group in by_dob.items():
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                if _norm(left.fields.get("pan")) and _norm(left.fields.get("pan")) == _norm(
                    right.fields.get("pan")
                ):
                    continue    # already covered by the PAN check
                if _norm(left.fields.get("first_name")) != _norm(right.fields.get("first_name")):
                    continue
                left_last = _norm(left.fields.get("last_name"))
                right_last = _norm(right.fields.get("last_name"))
                similarity = float(fuzz.WRatio(left_last, right_last))
                if not (
                    similarity >= policy.IDENTITY_NAME_SIMILARITY
                    or _abbreviates(left_last, right_last)
                ):
                    continue
                subject = _pair_subject("identity", left.key, right.key)
                answer = decisions.get(subject)
                if answer:
                    audit.append(
                        AuditEntry(
                            run_id=run_id,
                            actor=Actor.HUMAN,
                            action="resolve_duplicate",
                            entity=f"{left.key} + {right.key}",
                            before="same birthday, same first name, similar surname",
                            after="kept separate" if answer == "separate" else str(answer),
                            disposition=Disposition.AUTO,
                            rationale="A consultant adjudicated the suspected duplicate.",
                        )
                    )
                    continue
                emit(f"Possible duplicate: {left.key} and {right.key} - asking")
                out.append(
                    Escalation(
                        run_id=run_id,
                        type=EscalationType.DUPLICATE_SUSPECTED,
                        subject=subject,
                        title=f"Are these the same person? {_name_of(left.fields).title()}",
                        question=(
                            f"Both records share a date of birth and a first name, and the "
                            f"surnames look related ('{left_last.title()}' against "
                            f"'{right_last.title()}'). But the email addresses and employee "
                            f"codes differ, and nothing unique ties them together, so this "
                            f"could equally be two people or one person entered twice."
                        ),
                        evidence={
                            "date_of_birth": dob,
                            "surname_similarity": round(similarity, 1),
                            "records": [
                                {
                                    "key": record.key,
                                    "employee_code": record.fields.get("employee_code"),
                                    "name": _name_of(record.fields).title(),
                                    "work_email": record.fields.get("work_email"),
                                    "department": record.fields.get("department"),
                                    "designation": record.fields.get("designation"),
                                    "date_of_joining": record.fields.get("date_of_joining"),
                                    "sources": record.sources,
                                }
                                for record in (left, right)
                            ],
                        },
                        options=[
                            {
                                "value": "separate",
                                "label": "Two different people",
                                "detail": "keep both records",
                            },
                            {
                                "value": f"merge:{left.key}",
                                "label": f"Same person - keep {left.key}",
                                "detail": "merge the other into it",
                            },
                            {
                                "value": f"merge:{right.key}",
                                "label": f"Same person - keep {right.key}",
                                "detail": "merge the other into it",
                            },
                        ],
                        affected_records=[left.key, right.key],
                    )
                )
    return out

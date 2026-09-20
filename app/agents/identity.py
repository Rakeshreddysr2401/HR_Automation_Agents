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

    # Group on identifiers that are unique by construction: the schema's
    # `identity: strong` fields. Work email is issued once per person per
    # system; PAN once per person nationally; the employee code once per person
    # per HRIS.
    #
    # Rows are joined transitively across *any* shared strong identifier rather
    # than on one preferred key each. That distinction is the whole multi-file
    # case: a legacy export keyed by email and a payroll export keyed by
    # employee code describe the same people, and picking one identifier per row
    # puts them in different groups where they can never meet. Preferring email
    # did exactly that - two files, zero merges, every person duplicated.
    groups, keys_used = _group_by_shared_identifiers(rows, schema)

    records: list[TargetRecord] = []
    for members, matched_on in zip(groups, keys_used):
        record = _merge(members, matched_on, run_id, audit, emit)
        records.append(record)

    escalations.extend(_detect_shared_pan(records, run_id, decisions, audit, emit))
    # The per-pair narration is held back until it is known whether the pairs
    # are one question or many - 275 "possible duplicate" lines followed by
    # "asking once" would be the log version of the flood.
    held: list[str] = []
    near = _detect_near_duplicates(records, run_id, decisions, audit, held.append)
    near, decisions = _collapse_cross_file_flood(near, records, run_id, decisions, audit, emit)
    if any(e.type is EscalationType.DUPLICATE_SUSPECTED for e in near):
        for line in held:
            emit(line)
    escalations.extend(near)
    records = _apply_merges(records, decisions, run_id, audit)

    merged = sum(1 for record in records if len(record.sources) > 1)
    emit(
        f"Reconciled {len(rows)} rows into {len(records)} people "
        f"({merged} merged from multiple sources)"
    )
    return records, escalations, audit


# Identifiers that identify an *employment record*, not a person.
#
# The distinction is the rehire, and getting it wrong is the worst thing this
# module can do. PAN is `identity: strong` and identifies a human nationally -
# but one human can hold two employment records, which is exactly what a rehire
# is. Unioning on PAN would silently merge the 2016-2019 stint with the 2022 one
# and destroy the service history gratuity is computed from. So PAN never joins
# rows here; it raises a question instead, via `_detect_shared_pan`.
#
# Work email and employee code are issued once per employment record, so they
# may join.
RECORD_IDENTIFIERS = ("employee_code", "work_email")


def _record_identifiers(schema: TargetSchema) -> list[str]:
    """Strong identifiers that are safe to merge on, in schema order."""
    strong = {f.name for f in schema.identity_fields}
    return [name for name in RECORD_IDENTIFIERS if name in strong] or list(
        RECORD_IDENTIFIERS
    )


def _group_by_shared_identifiers(
    rows: list[dict[str, Any]], schema: TargetSchema
) -> tuple[list[list[dict[str, Any]]], list[str]]:
    """Union rows that share any strong identifier, transitively.

    Union-find rather than a single grouping key, because identifier coverage
    differs between files: row A carries an email, row B the same person's
    employee code, row C both. Only C can prove A and B are the same person, and
    only a transitive join will let it.

    Returns the groups and, for each, the identifier that joined it - which the
    audit trail states as the basis for the merge.
    """
    strong = _record_identifiers(schema)

    parent: dict[int, int] = {i: i for i in range(len(rows))}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # First index holder of each identifier value, so the second holder unions.
    seen: dict[tuple[str, str], int] = {}
    joined_on: dict[int, str] = {}
    for index, row in enumerate(rows):
        for field_name in strong:
            value = _norm(row.get(field_name))
            if not value:
                continue
            identifier = (field_name, value)
            if identifier in seen:
                union(seen[identifier], index)
                joined_on.setdefault(find(index), field_name)
            else:
                seen[identifier] = index

    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(rows):
        buckets[find(index)].append(row)

    groups = list(buckets.values())
    bases = [joined_on.get(root, "") for root in buckets]
    return groups, bases


# How the audit trail names the identifier a merge was made on.
IDENTIFIER_PHRASES = {
    "work_email": "the same work email",
    "employee_code": "the same employee code",
    "pan": "the same PAN",
}


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
        key=str(
            fields.get("employee_code")
            or fields.get("work_email")
            or ordered[0]["_source"]
        ),
        fields=fields,
        sources=[row["_source"] for row in ordered],
    )
    for row in ordered:
        record.errors.extend(row.get("_issues", []))

    if len(ordered) > 1:
        basis = IDENTIFIER_PHRASES.get(key, "a shared unique identifier")
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


def _file_of(record: TargetRecord) -> str | None:
    files = {source.rsplit("#", 1)[0] for source in record.sources}
    return next(iter(files)) if len(files) == 1 else None


def _collapse_cross_file_flood(
    escalations: list[Escalation],
    records: list[TargetRecord],
    run_id: str,
    decisions: dict[str, Any],
    audit: list[AuditEntry],
    emit: Emit,
) -> tuple[list[Escalation], dict[str, Any]]:
    """Many near-matches between the same two files are one question, not many.

    Returns the escalations to raise and the decisions to apply - a batch
    answer of "merge them all" is expanded into the per-pair merges that
    `_apply_merges` already knows how to carry out.
    """
    by_key = {record.key: record for record in records}
    pairs_by_files: dict[tuple[str, str], list[Escalation]] = defaultdict(list)
    for esc in escalations:
        left, right = (by_key.get(k) for k in esc.affected_records[:2])
        if not left or not right:
            continue
        files = (_file_of(left), _file_of(right))
        if files[0] and files[1] and files[0] != files[1]:
            pairs_by_files[tuple(sorted(files))].append(esc)  # type: ignore[arg-type]
    if not pairs_by_files:
        return escalations, decisions

    (file_a, file_b), pairs = max(pairs_by_files.items(), key=lambda kv: len(kv[1]))
    rows_in = {
        f: sum(1 for r in records if _file_of(r) == f) for f in (file_a, file_b)
    }
    if not policy.duplicates_are_a_flood(len(pairs), min(rows_in.values())):
        return escalations, decisions

    subject = f"identity-batch:{file_a}|{file_b}"
    answer = decisions.get(subject)
    others = [e for e in escalations if e not in pairs]

    if answer == "review":
        return escalations, decisions

    if answer in ("merge_all", "separate_all"):
        expanded = dict(decisions)
        for esc in pairs:
            left, right = (by_key[k] for k in esc.affected_records[:2])
            if answer == "merge_all":
                winner = max((left, right), key=lambda r: _completeness(r.fields))
                expanded.setdefault(esc.subject, f"merge:{winner.key}")
            else:
                expanded.setdefault(esc.subject, "separate")
        audit.append(
            AuditEntry(
                run_id=run_id,
                actor=Actor.HUMAN,
                action="resolve_duplicate_batch",
                entity=f"{file_a} + {file_b}",
                before=f"{len(pairs)} pairs matching on full name and date of birth",
                after="merged pairwise" if answer == "merge_all" else "all kept separate",
                disposition=Disposition.AUTO,
                rationale=(
                    f"A consultant confirmed the two files describe the same people"
                    if answer == "merge_all"
                    else "A consultant confirmed these are different people despite the matches"
                ),
            )
        )
        return others, expanded

    emit(
        f"{len(pairs)} near-matches between {file_a} and {file_b} - asking once about "
        f"the two files, not once per pair"
    )
    examples = [
        _name_of(by_key[e.affected_records[0]].fields).title() for e in pairs[:6]
    ]
    others.append(
        Escalation(
            run_id=run_id,
            type=EscalationType.BATCH_ANOMALY,
            subject=subject,
            title=f"{file_a} and {file_b} look like two exports of the same people",
            question=(
                f"{len(pairs)} pairs of records - one from each file - share a full name and "
                f"date of birth, but carry different employee codes and no shared unique "
                f"identifier, so nothing joins them automatically. That is not {len(pairs)} "
                f"coincidences; it is two systems describing the same staff. Merging is the "
                f"usual answer, but a wrong merge is invisible once loaded, so it is one "
                f"decision for you rather than {len(pairs)}."
            ),
            evidence={
                "pair_count": len(pairs),
                "files": {file_a: rows_in[file_a], file_b: rows_in[file_b]},
                "basis": "full name and date of birth",
                "examples": examples,
            },
            options=[
                {
                    "value": "merge_all",
                    "label": "Same people - merge each pair",
                    "detail": "keeps the more complete record, fills gaps from the other",
                },
                {
                    "value": "separate_all",
                    "label": "Different people - keep all",
                    "detail": f"loads all {sum(rows_in.values())} as separate employees",
                },
                {
                    "value": "review",
                    "label": "Review each pair",
                    "detail": f"{len(pairs)} individual questions",
                },
            ],
            affected_records=[k for e in pairs for k in e.affected_records],
        )
    )
    return others, decisions


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

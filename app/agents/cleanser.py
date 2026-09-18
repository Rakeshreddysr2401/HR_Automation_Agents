"""Cleanser: apply the mapping, then make the values legal.

Split by blast radius, which is the only division that matters here:

  cosmetic   trimming, casing, punctuation in phone numbers. Always applied,
             never queued, summarised per column in the audit trail. If one of
             these is somehow wrong it is visible on the first screen a human
             looks at and costs nothing to correct.
  inferred   a date convention deduced from unambiguous rows in the same
             column, an enum value that is a near-certain typo. Applied, but
             recorded per record and surfaced, because the reasoning deserves a
             glance even though it does not deserve a question.
  contested  an all-ambiguous date column, an enum value sitting in the grey
             band. Not applied. Asked once per column or per distinct value -
             never once per row, because forty identical questions is the same
             failure as guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Callable

import pandas as pd
from rapidfuzz import fuzz

from app import dates, policy
from app.models import (
    Actor,
    AuditEntry,
    ColumnMapping,
    Disposition,
    Escalation,
    EscalationType,
)
from app.schema import TargetField, TargetSchema

Emit = Callable[[str], None]

WHITESPACE = re.compile(r"\s+")
NON_PHONE = re.compile(r"[^\d+]")


@dataclass
class CleanResult:
    rows: list[dict[str, Any]] = dc_field(default_factory=list)
    escalations: list[Escalation] = dc_field(default_factory=list)
    audit: list[AuditEntry] = dc_field(default_factory=list)
    date_plans: dict[str, dates.ColumnPlan] = dc_field(default_factory=dict)
    blocked_fields: dict[str, set[str]] = dc_field(default_factory=dict)


def smart_title(text: str) -> str:
    """Title-case only the tokens that clearly need it.

    Names arrive as "AARAV", "aarav" or "Aarav". The first two want fixing; the
    third does not need touching, and neither does "McDonald" or "O'Brien",
    which naive title-casing would quietly damage.
    """
    out = []
    for token in text.split():
        if token.isupper() or token.islower():
            out.append(token[:1].upper() + token[1:].lower())
        else:
            out.append(token)
    return " ".join(out)


def normalise(value: str, target: TargetField) -> str:
    text = WHITESPACE.sub(" ", str(value or "")).strip()
    if not text:
        return ""
    if target.format == "email":
        return text.lower()
    if target.format == "phone":
        cleaned = NON_PHONE.sub("", text)
        return f"+{cleaned.lstrip('+')}" if text.strip().startswith("+") else cleaned
    if target.format in ("pan", "ifsc"):
        return text.upper().replace(" ", "")
    if target.name in ("uan", "bank_account"):
        return text.replace(" ", "")
    if target.name in ("first_name", "last_name"):
        return smart_title(text)
    return text


def canonicalise_enum(
    value: str, target: TargetField
) -> tuple[str | None, float, Disposition]:
    """Map a raw value onto the schema's vocabulary.

    Returns (canonical value or None, score, disposition).
    """
    text = value.strip()
    if not text:
        return None, 0.0, Disposition.AUTO

    lowered = text.lower()
    exact = {option.lower(): option for option in target.enum}
    if lowered in exact:
        return exact[lowered], 100.0, Disposition.AUTO

    # Standard abbreviations are knowledge, not inference.
    alias = policy.SAFE_ALIASES.get(target.name, {}).get(lowered)
    if alias and alias in target.enum:
        return alias, 100.0, Disposition.AUTO

    best, score = None, 0.0
    for option in target.enum:
        candidate = float(fuzz.WRatio(lowered, option.lower()))
        if candidate > score:
            best, score = option, candidate

    disposition = policy.classify_enum_match(score)
    if disposition is Disposition.AUTO:
        return best, score, disposition
    return None, score, disposition


def _mapping_index(mappings: list[ColumnMapping]) -> dict[str, list[ColumnMapping]]:
    index: dict[str, list[ColumnMapping]] = {}
    for mapping in mappings:
        if mapping.target_field and mapping.disposition in (
            Disposition.AUTO,
            Disposition.FLAGGED,
        ):
            index.setdefault(mapping.source_file, []).append(mapping)
    return index


def clean(
    frames: dict[str, pd.DataFrame],
    mappings: list[ColumnMapping],
    schema: TargetSchema,
    run_id: str,
    decisions: dict[str, Any] | None = None,
    emit: Emit = lambda _: None,
) -> CleanResult:
    decisions = decisions or {}
    result = CleanResult()
    index = _mapping_index(mappings)
    by_name = schema.by_name

    # Pass one: settle each date column before touching any row, because the
    # convention is a property of the column and no single row can reveal it.
    conventions: dict[tuple[str, str], str | None] = {}
    for source_file, file_mappings in index.items():
        frame = frames[source_file]
        for mapping in file_mappings:
            target = by_name.get(mapping.target_field or "")
            if not target or target.type != "date":
                continue
            values = frame[mapping.column].astype(str).tolist()
            plan = dates.analyse_column(values)
            key = f"{source_file}:{mapping.column}"
            result.date_plans[key] = plan

            answered = decisions.get(f"date:{source_file}:{mapping.column}")
            if answered in (dates.DMY, dates.MDY):
                conventions[(source_file, mapping.column)] = answered
                emit(
                    f"'{mapping.column}' in {source_file} reads as "
                    f"{dates.describe(answered)} - confirmed by a consultant"
                )
                result.audit.append(
                    AuditEntry(
                        run_id=run_id,
                        actor=Actor.HUMAN,
                        action="set_date_convention",
                        entity=f"column:{source_file}:{mapping.column}",
                        before="ambiguous",
                        after=dates.describe(answered),
                        disposition=Disposition.AUTO,
                        rationale="Nothing in the column settled it, so a consultant did.",
                    )
                )
                continue

            safe = policy.date_convention_is_safe(plan.anchors, plan.agreement)
            if plan.convention == dates.ISO or (plan.convention and safe):
                conventions[(source_file, mapping.column)] = plan.convention
                if plan.inferred:
                    emit(
                        f"'{mapping.column}' in {source_file} reads as "
                        f"{dates.describe(plan.convention)} - {plan.anchors} rows prove it"
                    )
                    result.audit.append(
                        AuditEntry(
                            run_id=run_id,
                            actor=Actor.AGENT,
                            action="infer_date_convention",
                            entity=f"column:{source_file}:{mapping.column}",
                            before="ambiguous",
                            after=dates.describe(plan.convention),
                            disposition=Disposition.FLAGGED,
                            rationale=(
                                f"{plan.anchors} of {plan.total} values have a day above 12, "
                                f"and {plan.agreement:.0%} of them agree, so the column is "
                                f"{dates.describe(plan.convention)}. Applied to all rows."
                            ),
                        )
                    )
                continue

            if not plan.ambiguous_values:
                conventions[(source_file, mapping.column)] = plan.convention
                continue

            # Nothing in the column settles it. Ask once, for the column.
            conventions[(source_file, mapping.column)] = None
            result.blocked_fields.setdefault(source_file, set()).add(mapping.target_field or "")
            affected = [
                f"{source_file}#{position + 2}"
                for position, value in enumerate(values)
                if dates.read_value(str(value)).ambiguous
            ]
            emit(f"'{mapping.column}' in {source_file} has no readable date - asking")
            result.escalations.append(
                Escalation(
                    run_id=run_id,
                    type=EscalationType.DATE_CONVENTION,
                    subject=f"date:{source_file}:{mapping.column}",
                    title=f"Is '{mapping.column}' day-first or month-first?",
                    question=(
                        f"Every date in '{mapping.column}' ({source_file}) has both parts at "
                        f"12 or below, so nothing in the column reveals whether 05/03/2021 "
                        f"means 5 March or 3 May. Getting this wrong silently distorts "
                        f"tenure and leave balances, so it needs confirming."
                    ),
                    evidence={
                        "source_file": source_file,
                        "column": mapping.column,
                        "target_field": mapping.target_field,
                        "sample_values": plan.ambiguous_values[:6],
                        "ambiguous_count": len(plan.ambiguous_values),
                        "total_values": plan.total,
                        "anchors_found": plan.anchors,
                    },
                    options=[
                        {
                            "value": dates.DMY,
                            "label": "Day first (05/03/2021 = 5 March)",
                            "detail": "common outside the United States",
                        },
                        {
                            "value": dates.MDY,
                            "label": "Month first (05/03/2021 = 3 May)",
                            "detail": "common in United States systems",
                        },
                    ],
                    affected_records=affected,
                )
            )

    # Pass two: build the records.
    enum_problems: dict[tuple[str, str], dict[str, Any]] = {}
    cosmetic: dict[str, int] = {}

    for source_file, frame in frames.items():
        file_mappings = index.get(source_file, [])
        if not file_mappings:
            continue
        for position, raw_row in enumerate(frame.to_dict(orient="records")):
            row: dict[str, Any] = {
                "_source": f"{source_file}#{position + 2}",   # +2 = header plus 1-indexing
                "_file": source_file,
            }
            for mapping in file_mappings:
                target = by_name.get(mapping.target_field or "")
                if not target:
                    continue
                raw_value = str(raw_row.get(mapping.column, "") or "")

                if mapping.transform == "split_full_name":
                    first, last = _split_name(raw_value)
                    row["first_name"] = smart_title(first)
                    row["last_name"] = smart_title(last)
                    continue

                cleaned = normalise(raw_value, target)
                if cleaned != raw_value.strip() and cleaned and raw_value.strip():
                    cosmetic[f"{source_file}:{mapping.column}"] = (
                        cosmetic.get(f"{source_file}:{mapping.column}", 0) + 1
                    )

                if target.type == "date" and cleaned:
                    convention = conventions.get((source_file, mapping.column))
                    parsed, error = dates.apply_convention(cleaned, convention)
                    if parsed:
                        row[target.name] = parsed.isoformat()
                    else:
                        row[target.name] = ""
                        row.setdefault("_issues", []).append(
                            f"{target.name}: {error or 'unreadable date'} ({cleaned})"
                        )
                    continue

                if target.type == "enum" and cleaned:
                    answered = decisions.get(f"enum:{target.name}:{cleaned.lower()}")
                    if answered:
                        row[target.name] = "" if answered == "__blank__" else answered
                        continue
                    canonical, score, disposition = canonicalise_enum(cleaned, target)
                    if canonical:
                        row[target.name] = canonical
                        if canonical.lower() != cleaned.lower():
                            result.audit.append(
                                AuditEntry(
                                    run_id=run_id,
                                    actor=Actor.AGENT,
                                    action="canonicalise_value",
                                    entity=row["_source"],
                                    before=cleaned,
                                    after=canonical,
                                    disposition=Disposition.AUTO
                                    if score >= policy.ENUM_AUTO_MIN
                                    else Disposition.FLAGGED,
                                    rationale=(
                                        f"'{cleaned}' matches the {target.name} value "
                                        f"'{canonical}' at {score:.0f}%."
                                    ),
                                )
                            )
                    else:
                        row[target.name] = ""
                        key = (target.name, cleaned.lower())
                        entry = enum_problems.setdefault(
                            key,
                            {
                                "field": target.name,
                                "raw": cleaned,
                                "score": score,
                                "rows": [],
                                "source_file": source_file,
                                "column": mapping.column,
                            },
                        )
                        entry["rows"].append(row["_source"])
                    continue

                row[target.name] = cleaned

            # Defaults are part of the schema contract, not a guess.
            for target in schema.fields:
                if target.default is not None and not row.get(target.name):
                    row[target.name] = target.default
            result.rows.append(row)

    for location, count in sorted(cosmetic.items()):
        source_file, column = location.split(":", 1)
        result.audit.append(
            AuditEntry(
                run_id=run_id,
                actor=Actor.AGENT,
                action="normalise_values",
                entity=f"column:{source_file}:{column}",
                before=f"{count} values with stray spacing or casing",
                after="normalised",
                disposition=Disposition.AUTO,
                rationale=(
                    "Whitespace and casing were corrected. A wrong correction here is "
                    "visible on sight and trivially reversible, so it was not queued."
                ),
            )
        )

    for entry in enum_problems.values():
        target = by_name[entry["field"]]
        emit(f"Unrecognised {entry['field']} value '{entry['raw']}' - asking")
        result.escalations.append(_enum_escalation(run_id, entry, target))

    emit(
        f"Built {len(result.rows)} records from {len(frames)} files; "
        f"{len(result.escalations)} cleaning questions"
    )
    return result


def _enum_escalation(run_id: str, entry: dict[str, Any], target: TargetField) -> Escalation:
    ranked = sorted(
        ((option, float(fuzz.WRatio(entry["raw"].lower(), option.lower()))) for option in target.enum),
        key=lambda pair: pair[1],
        reverse=True,
    )
    near = ranked[0]
    question = (
        f"'{entry['raw']}' appears in '{entry['column']}' ({entry['source_file']}) but is not "
        f"one of the {target.name} values this schema accepts."
    )
    if near[1] >= policy.ENUM_ESCALATE_MIN:
        question += (
            f" It resembles '{near[0]}' at {near[1]:.0f}%, which is close enough to suspect "
            f"and too far to assume."
        )
    return Escalation(
        run_id=run_id,
        type=EscalationType.ENUM_VALUE,
        subject=f"enum:{target.name}:{entry['raw'].lower()}",
        title=f"What does '{entry['raw']}' mean?",
        question=question,
        evidence={
            "source_file": entry["source_file"],
            "column": entry["column"],
            "target_field": target.name,
            "raw_value": entry["raw"],
            "best_match": near[0],
            "best_score": round(near[1], 1),
            "allowed_values": target.enum,
            "affected_rows": len(entry["rows"]),
        },
        options=[
            {"value": option, "label": option, "detail": f"{score:.0f}% similar"}
            for option, score in ranked[:4]
        ]
        + [{"value": "__blank__", "label": "Leave empty", "detail": ""}],
        affected_records=entry["rows"],
    )


def _split_name(full: str) -> tuple[str, str]:
    parts = WHITESPACE.sub(" ", full or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])

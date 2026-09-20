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
    # Distinct values per enum-mapped column, split by whether they fit the
    # target field's vocabulary. Counted distinctly rather than per row: one bad
    # value repeated four hundred times is one piece of evidence, not four
    # hundred. Used below to tell "messy values" from "wrong mapping".
    enum_fit: dict[tuple[str, str, str], dict[str, set[str]]] = {}

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
                    fit = enum_fit.setdefault(
                        (source_file, mapping.column, target.name),
                        {"matched": set(), "unmatched": set(), "provenance": set()},
                    )
                    fit["matched" if canonical else "unmatched"].add(cleaned.lower())
                    fit["provenance"].add(mapping.provenance)
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

    # One entry per name column recording which convention it was read as. The
    # surname-first case is settled by the comma; the other is an assumption,
    # and FLAGGED is what lets it be audited without blocking the migration.
    for source_file, frame in frames.items():
        for mapping in index.get(source_file, []):
            if mapping.transform != "split_full_name":
                continue
            values = [str(v) for v in frame[mapping.column].dropna().tolist()]
            entry = _name_order_audit(run_id, source_file, mapping.column, values)
            if entry:
                result.audit.append(entry)

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

    # A column whose values mostly do not belong to the field's vocabulary is
    # evidence against the *mapping*, not against the values. Asking about each
    # value would be several questions pointing at the wrong problem.
    contradicted: set[tuple[str, str, str]] = set()
    for (source_file, column, field_name), fit in enum_fit.items():
        total = len(fit["matched"]) + len(fit["unmatched"])
        # Once a consultant has confirmed this column *is* the field, asking
        # again would be re-asking a question they already answered - and since
        # the mapping is re-derived every pass, it would be asked on every
        # round until the loop limit. Their answer stands; the values become
        # the question instead, which is what the option they chose promised.
        if "human" in fit["provenance"]:
            continue
        if policy.mapping_is_contradicted_by_values(len(fit["unmatched"]), total):
            contradicted.add((source_file, column, field_name))
            target = by_name[field_name]
            emit(
                f"'{column}' in {source_file} does not look like {field_name} - "
                f"{len(fit['unmatched'])} of {total} values are outside its vocabulary, "
                f"so the mapping is in question rather than the values"
            )
            result.escalations.append(
                _vocabulary_mismatch_escalation(
                    run_id, source_file, column, target, fit
                )
            )
            # The field cannot be trusted until this is settled, so it is
            # pending rather than merely empty - which keeps the validator from
            # reporting it as a missing required field on every record.
            result.blocked_fields.setdefault(source_file, set()).add(field_name)

    for entry in enum_problems.values():
        target = by_name[entry["field"]]
        if (entry["source_file"], entry["column"], entry["field"]) in contradicted:
            continue   # already covered by the one mapping-level question
        emit(f"Unrecognised {entry['field']} value '{entry['raw']}' - asking")
        result.escalations.append(_enum_escalation(run_id, entry, target))

    emit(
        f"Built {len(result.rows)} records from {len(frames)} files; "
        f"{len(result.escalations)} cleaning questions"
    )
    return result


def _vocabulary_mismatch_escalation(
    run_id: str,
    source_file: str,
    column: str,
    target: TargetField,
    fit: dict[str, set[str]],
) -> Escalation:
    """One question: is this column really this field?

    Raised instead of a question per unrecognised value. The evidence that makes
    it answerable at a glance is the two lists side by side - what the column
    actually contains, and what the field accepts. A consultant seeing race
    categories against Male/Female/Other does not need the question explained.
    """
    unmatched = sorted(fit["unmatched"])
    matched = sorted(fit["matched"])
    total = len(matched) + len(unmatched)
    return Escalation(
        run_id=run_id,
        type=EscalationType.COLUMN_MAPPING,
        # Keyed on the mapping, not the values, so answering it survives a
        # re-run and is remembered like any other mapping decision.
        subject=f"map:{source_file}:{column}",
        # The title reports the evidence rather than presupposing the cause,
        # because both causes are common and they look identical from here. A
        # column of race categories mapped to gender is a wrong mapping; a
        # column genuinely called Department whose values are "Production" and
        # "IT/IS" is a schema vocabulary that does not fit this client. The
        # consultant can tell these apart at a glance; the agent cannot.
        title=f"'{column}' holds {len(unmatched)} value(s) that are not {target.name} values",
        question=(
            f"'{column}' was mapped to {target.name}, but {len(unmatched)} of its "
            f"{total} distinct values are outside that field's vocabulary "
            f"({', '.join(repr(v) for v in unmatched[:4])}"
            f"{', …' if len(unmatched) > 4 else ''}). Either the column is not "
            f"{target.name} at all, or it is and this schema's list of accepted "
            f"{target.name} values does not cover this client."
        ),
        evidence={
            "source_file": source_file,
            "column": column,
            "target_field": target.name,
            "unmatched_values": unmatched[:12],
            "matched_values": matched[:12],
            "unmatched_count": len(unmatched),
            "total_values": total,
            "allowed_values": target.enum,
            "vocabulary_mismatch": True,
        },
        options=[
            {
                "value": "__ignore__",
                "label": f"Not {target.name} — leave it unmapped",
                "detail": "the column is something this schema has no field for",
            },
            {
                "value": target.name,
                "label": f"It is {target.name} — ask me about each value",
                "detail": f"{len(unmatched)} value question(s) instead",
            },
        ],
        affected_records=[],
    )


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


# Suffixes and particles that must not be mistaken for the surname. "Smith,
# John Jr" has surname Smith; "van der Berg, Jan" has surname "van der Berg".
NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v", "phd", "md"}
SURNAME_PARTICLES = {"van", "von", "de", "del", "della", "der", "den", "di",
                     "da", "dos", "du", "la", "le", "bin", "binte", "ibn", "al"}


def _split_name(full: str) -> tuple[str, str]:
    """Split one full name into (given names, surname).

    Two opposite conventions turn up in real exports:

        "Wilson Adinolfi"         given name first
        "Adinolfi, Wilson  K"     surname first, comma-delimited

    The comma is the tell, and it is reliable: no HR system writes
    "First, Last". Reading it the wrong way round is the archetypal silent
    error this project exists to avoid - both fields end up holding plausible
    strings, every format check passes, and yet every employee in the file has
    their name inverted with a stray comma attached. Nothing downstream
    complains, which is exactly why it must be handled here rather than
    discovered by the client.

    With no comma the surname is taken to be the final token and everything
    before it is given names - the convention nearly every system uses. That is
    wrong for compound surnames ("Garcia Marquez") and for cultures that write
    the family name first, and no amount of staring at a name string can settle
    which applies. So the column reports the assumption it made (see
    `_name_order_audit`) rather than hiding it.
    """
    text = WHITESPACE.sub(" ", str(full or "")).strip()
    if not text:
        return "", ""

    # Surname-first. Everything before the first comma is the family name,
    # which handles particles ("van der Berg, Jan") without special-casing.
    if "," in text:
        surname, _, given = text.partition(",")
        surname, given = surname.strip(), given.strip()
        if surname and given:
            return given, surname
        # A trailing comma and nothing after it: "Adinolfi," is just a surname.
        return ("", surname) if surname else (given, "")

    parts = text.split()
    if len(parts) == 1:
        # One token is a given name, not a surname: a mononym is far more often
        # someone's first name in an HR export, and last_name is required, so
        # guessing the other way would fabricate a surname.
        return parts[0], ""

    # Drop a trailing suffix from consideration, then take the surname from the
    # end, pulling in any particles that belong to it.
    suffix: list[str] = []
    while len(parts) > 2 and parts[-1].lower().strip(".") in NAME_SUFFIXES:
        suffix.insert(0, parts.pop())

    cut = len(parts) - 1
    while cut > 1 and parts[cut - 1].lower() in SURNAME_PARTICLES:
        cut -= 1

    given = " ".join(parts[:cut])
    surname = " ".join(parts[cut:] + suffix)
    return given, surname


def _name_order_audit(
    run_id: str, source_file: str, column: str, values: list[str]
) -> AuditEntry | None:
    """Record which naming convention a column was read as.

    One entry per column rather than per row, for the same reason dates get one
    question per column: the convention is a property of the system that wrote
    the file, not of any individual row.

    Surname-first is AUTO because a comma settles it outright. Given-name-first
    is FLAGGED: it is the right call for the overwhelming majority of exports
    and not worth blocking a migration over, but it is still an assumption, and
    a consultant who knows this client writes family names first should be able
    to see it was made and in seconds.
    """
    sampled = [v for v in values if v and str(v).strip()][:200]
    if not sampled:
        return None

    with_comma = sum(1 for v in sampled if "," in str(v))
    entity = f"column:{source_file}:{column}"

    if with_comma >= len(sampled) * 0.5:
        return AuditEntry(
            run_id=run_id,
            actor=Actor.AGENT,
            action="infer_name_order",
            entity=entity,
            before="ambiguous",
            after="surname first",
            disposition=Disposition.AUTO,
            rationale=(
                f"{with_comma} of {len(sampled)} values contain a comma, so this "
                f"column is written surname-first. Split on the comma, which is "
                f"unambiguous - no HR system writes 'First, Last'."
            ),
        )

    multi = sum(1 for v in sampled if len(str(v).split()) > 2)
    return AuditEntry(
        run_id=run_id,
        actor=Actor.AGENT,
        action="infer_name_order",
        entity=entity,
        before="ambiguous",
        after="given name first",
        disposition=Disposition.FLAGGED,
        rationale=(
            f"No commas in {len(sampled)} sampled values, so the column reads as "
            f"given-name-first and the surname is the final token. "
            + (
                f"{multi} value(s) have three or more parts, where a compound "
                f"surname would be read as a middle name instead. "
                if multi
                else ""
            )
            + "Applied to the whole column; correct it here if this client writes "
            "family names first."
        ),
    )

"""Schema Mapper: decide which target field each source column means.

Scoring blends three independent signals, because each one fails differently:

    semantic   embedding of the column (name + redacted samples) against the
               target field's description. Catches "worker_category" ->
               employment_type, where the strings share nothing.
    lexical    fuzzy match of the column name against the field name and the
               aliases named in its description. Catches "DOB" and "DOJ", where
               embeddings of three-letter abbreviations are weak.
    structural type agreement between what the column contains and what the
               field accepts. A column of dates cannot be an email address, no
               matter how the header is worded.

The model's role is bounded on purpose: where the score is ambiguous it writes
the recommendation shown on the escalation card, but it is never allowed to
apply one. A suggestion a human accepts is auditable; a suggestion a model
applies silently is not.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable

from rapidfuzz import fuzz

from app import llm, policy
from app.models import (
    ColumnMapping,
    ColumnProfile,
    Disposition,
    Escalation,
    EscalationType,
    MappingCandidate,
)
from app.schema import TargetField, TargetSchema

Emit = Callable[[str], None]

# Column types that can legitimately carry each target field type.
TYPE_COMPATIBILITY: dict[str, set[str]] = {
    "date": {"date"},
    "email": {"email", "string"},
    # Deliberately excludes "id": an employee code like E1021 is not a phone
    # number, and the word "number" in both descriptions makes them embed
    # closely enough that the structural signal has to break the tie.
    "phone": {"phone", "number"},
    "enum": {"string"},
    "string": {"string", "id", "number", "email", "phone", "date"},
}

TYPE_BONUS = 0.08
TYPE_PENALTY = 0.18

# Only "Also called ..." lists aliases. "such as ..." lists example *values*
# ("such as engineering, sales or finance"), and treating those as aliases would
# make a column literally named "Sales" look like the department field itself.
_ALIAS_SPLIT = re.compile(r"also called\s*(.+?)(?:\.|$)", re.IGNORECASE)
_NAME_HINT = re.compile(r"\b(name|employee|staff|person)\b", re.IGNORECASE)


def _alias_terms(field: TargetField) -> list[str]:
    """Field name plus the aliases its description spells out."""
    terms = [field.name.replace("_", " ")]
    for match in _ALIAS_SPLIT.finditer(field.description):
        for part in re.split(r",| or ", match.group(1)):
            cleaned = part.strip(" .")
            if cleaned:
                terms.append(cleaned)
    return terms


def _expected_column_type(field: TargetField) -> str:
    if field.type == "date":
        return "date"
    if field.format in ("email", "phone"):
        return field.format
    if field.type == "enum":
        return "enum"
    return "string"


def _structural_adjustment(profile: ColumnProfile, field: TargetField) -> float:
    expected = _expected_column_type(field)
    allowed = TYPE_COMPATIBILITY.get(expected, {"string"})
    if profile.inferred_type in allowed:
        # Only reward a genuinely informative agreement. Everything matches
        # "string", so agreeing on it says nothing.
        return TYPE_BONUS if expected != "string" else 0.0
    return -TYPE_PENALTY


def _lexical_score(column: str, field: TargetField) -> float:
    """Blend a permissive and a strict fuzzy metric.

    Neither works alone, and they fail in opposite directions. Permissive
    metrics score a subset as a perfect match, so "Office" looks identical to
    "office email". Strict metrics punish legitimate abbreviation, scoring
    "pan number" against "pan" at 0.46. Averaging them keeps abbreviations
    scoring well while pulling bare-substring coincidences back down.
    """
    column_norm = column.replace("_", " ").strip().lower()
    best = 0.0
    for term in _alias_terms(field):
        alias = term.lower()
        blended = 0.5 * fuzz.WRatio(column_norm, alias) + 0.5 * fuzz.token_sort_ratio(
            column_norm, alias
        )
        best = max(best, blended)
    return best / 100.0


def _column_embed_text(profile: ColumnProfile) -> str:
    samples = ", ".join(profile.samples[:5])
    return f"{profile.column.replace('_', ' ')}. Example values: {samples}"


def _looks_like_full_name(profile: ColumnProfile) -> bool:
    """A single column holding "Aarav Sharma" feeds two target fields."""
    if not _NAME_HINT.search(profile.column):
        return False
    if re.search(r"\b(first|last|sur|given|middle|father|mother)\b", profile.column, re.I):
        return False
    samples = [s.strip() for s in profile.raw_samples if s.strip()]
    if not samples:
        return False
    two_parts = sum(1 for s in samples if 2 <= len(s.split()) <= 4)
    return two_parts / len(samples) >= 0.8


def _relative_semantic(cosines: dict[str, float]) -> dict[str, float]:
    """Rescale raw cosines into a usable spread.

    Every field in an HR schema is describing an employee, so raw cosine over
    this candidate set has a high floor - the observed range is roughly 0.45 to
    0.78, with the correct field typically two to four standard deviations above
    the mean of its own candidate set. Comparing raw values across columns is
    meaningless because each column sits at its own baseline; comparing a field
    against the other candidates *for the same column* is exactly the question
    being asked. So the score is standardised within each column's candidate set.
    """
    values = list(cosines.values())
    if not values or max(values) <= 0.0:
        return {name: 0.0 for name in cosines}
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    spread = variance**0.5
    if spread < 1e-6:
        return {name: 0.0 for name in cosines}
    return {
        name: max(0.0, min(1.0, (value - mean) / (policy.SEMANTIC_Z_FULL_SCALE * spread)))
        for name, value in cosines.items()
    }


def score_column(
    profile: ColumnProfile,
    schema: TargetSchema,
    field_vectors: dict[str, list[float]],
) -> list[MappingCandidate]:
    column_vector = llm.embed(_column_embed_text(profile))
    cosines = {
        field.name: llm.cosine(column_vector, field_vectors.get(field.name))
        for field in schema.fields
    }
    relative = _relative_semantic(cosines)
    has_semantic = column_vector is not None and any(cosines.values())

    candidates: list[MappingCandidate] = []
    for field in schema.fields:
        lexical = _lexical_score(profile.column, field)
        if has_semantic:
            blended = (
                policy.EMBEDDING_WEIGHT * relative[field.name]
                + policy.FUZZY_WEIGHT * lexical
            )
        else:
            # No model server: lexical evidence carries the whole score. The
            # thresholds then escalate more, which is the safe direction to fail.
            blended = lexical
        blended = max(0.0, min(1.0, blended + _structural_adjustment(profile, field)))
        candidates.append(
            MappingCandidate(
                target_field=field.name,
                score=blended,
                embedding_score=cosines[field.name],
                fuzzy_score=lexical,
            )
        )
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def _recommendation(profile: ColumnProfile, top: list[MappingCandidate]) -> str:
    """Ask the local model to explain the tie in one sentence. Never binding."""
    options = ", ".join(f"{c.target_field} (score {c.score:.2f})" for c in top[:3])
    prompt = (
        "You are helping an HR data migration consultant resolve an ambiguous column "
        "mapping. Reply with JSON only.\n\n"
        f"Source column: {profile.column}\n"
        f"Detected type: {profile.inferred_type}\n"
        f"Example values: {', '.join(profile.samples[:5])}\n"
        f"Candidate target fields: {options}\n\n"
        'Reply as {"recommendation": "<target field name>", "reason": "<one short sentence>"}'
    )
    result = llm.ask_json(prompt)
    if not result:
        return ""
    field = str(result.get("recommendation", "")).strip()
    reason = str(result.get("reason", "")).strip()
    valid = {c.target_field for c in top}
    if field in valid and reason:
        return f"Model suggests {field}: {reason}"
    return reason


def map_columns(
    profiles: list[ColumnProfile],
    schema: TargetSchema,
    run_id: str,
    memory: dict[str, str] | None = None,
    decisions: dict[str, Any] | None = None,
    emit: Emit = lambda _: None,
) -> tuple[list[ColumnMapping], list[Escalation]]:
    memory = memory or {}
    decisions = decisions or {}
    emit(f"Scoring {len(profiles)} source columns against {len(schema.fields)} target fields")

    field_vectors = {f.name: llm.embed(f.embed_text) for f in schema.fields}
    if not any(field_vectors.values()):
        emit("No local model reachable - scoring on column names alone, which escalates more")

    mappings: list[ColumnMapping] = []
    escalations: list[Escalation] = []

    by_file: dict[str, list[ColumnProfile]] = defaultdict(list)
    for profile in profiles:
        by_file[profile.source_file].append(profile)

    for source_file, file_profiles in by_file.items():
        file_mappings, file_escalations = _map_one_file(
            source_file, file_profiles, schema, field_vectors, run_id, memory, decisions, emit
        )
        mappings.extend(file_mappings)
        escalations.extend(file_escalations)

    auto = sum(1 for m in mappings if m.disposition is Disposition.AUTO)
    flagged = sum(1 for m in mappings if m.disposition is Disposition.FLAGGED)
    asked = sum(1 for m in mappings if m.disposition is Disposition.ESCALATED)
    emit(f"Mapped {auto + flagged} columns on its own, {asked} need a decision")
    return mappings, escalations


def _map_one_file(
    source_file: str,
    profiles: list[ColumnProfile],
    schema: TargetSchema,
    field_vectors: dict[str, list[float]],
    run_id: str,
    memory: dict[str, str],
    decisions: dict[str, Any],
    emit: Emit,
) -> tuple[list[ColumnMapping], list[Escalation]]:
    """Resolve one file's columns as an assignment, not as independent guesses.

    A target field can only be filled from one column of a given file, so
    columns compete for fields: the strongest claim is settled first, the field
    is consumed, and every losing column re-evaluates against what is left. This
    is what separates "genuinely ambiguous" from "merely contested" - when a
    file has both an 'Official Email' and a 'Mail ID', the first wins work_email
    outright and the second is judged on whether it is convincingly the personal
    address, which is the question a consultant would actually ask.
    """
    scored: dict[str, list[MappingCandidate]] = {}
    for profile in profiles:
        scored[profile.column] = score_column(profile, schema, field_vectors)

    by_column = {p.column: p for p in profiles}
    mappings: list[ColumnMapping] = []
    escalations: list[Escalation] = []
    consumed: set[str] = set()
    resolved: set[str] = set()

    # A human answer is an input to this pass, not a patch applied afterwards.
    # Re-running the whole pipeline with the answer folded in is what keeps the
    # result consistent: confirming which column is work_email does not just fill
    # that field, it lets the identity resolver reconcile the two files against
    # each other, which changes how records merge downstream.
    for profile in profiles:
        answer = decisions.get(f"map:{source_file}:{profile.column}")
        if not answer or profile.column in resolved:
            continue
        if answer == "__ignore__":
            mappings.append(
                ColumnMapping(
                    source_file=source_file,
                    column=profile.column,
                    target_field=None,
                    disposition=Disposition.IGNORED,
                    confidence=1.0,
                    margin=1.0,
                    rationale="A consultant marked this column as not for migration.",
                    candidates=scored[profile.column][:4],
                    provenance="human",
                )
            )
            resolved.add(profile.column)
            continue
        if schema.field(answer):
            splits = _looks_like_full_name(profile)
            mappings.append(
                ColumnMapping(
                    source_file=source_file,
                    column=profile.column,
                    target_field=answer,
                    disposition=Disposition.AUTO,
                    confidence=1.0,
                    margin=1.0,
                    rationale=f"A consultant confirmed this column is {answer}.",
                    candidates=scored[profile.column][:4],
                    transform="split_full_name" if splits else None,
                    provenance="human",
                )
            )
            consumed.add(answer)
            if splits:
                consumed.update({"first_name", "last_name"})
            resolved.add(profile.column)

    # Decisions a human already made outrank anything scoring can conclude.
    for profile in profiles:
        remembered = memory.get(_memory_key(profile))
        if not remembered or not schema.field(remembered) or remembered in consumed:
            continue
        splits = _looks_like_full_name(profile)
        mappings.append(
            ColumnMapping(
                source_file=source_file,
                column=profile.column,
                target_field=remembered,
                disposition=Disposition.FLAGGED,
                confidence=1.0,
                margin=1.0,
                rationale=(
                    f"Applied a mapping to {remembered} that a consultant confirmed on a "
                    f"previous run of this column."
                ),
                candidates=scored[profile.column][:4],
                transform="split_full_name" if splits else None,
                provenance="memory",
            )
        )
        consumed.add(remembered)
        if splits:
            consumed.update({"first_name", "last_name"})
        resolved.add(profile.column)

    # A column holding "Aarav Sharma" feeds two target fields. That is a
    # structural transform, not an ambiguity: every sampled value is two words,
    # so the evidence points one way only.
    for profile in profiles:
        if profile.column in resolved:
            continue
        top = scored[profile.column][0]
        if not _looks_like_full_name(profile):
            continue
        if top.target_field not in ("first_name", "last_name"):
            continue
        if {"first_name", "last_name"} & consumed:
            continue
        mappings.append(
            ColumnMapping(
                source_file=source_file,
                column=profile.column,
                target_field="first_name",
                disposition=Disposition.FLAGGED,
                confidence=top.score,
                margin=top.score,
                rationale=(
                    "Every sampled value is a full name, so it was split into "
                    "first_name and last_name."
                ),
                candidates=scored[profile.column][:4],
                transform="split_full_name",
            )
        )
        consumed.update({"first_name", "last_name"})
        resolved.add(profile.column)

    # Settle the confident claims first, strongest first, consuming as we go.
    while True:
        best: tuple[float, float, str, str] | None = None   # score, margin, column, field
        for profile in profiles:
            if profile.column in resolved:
                continue
            available = [c for c in scored[profile.column] if c.target_field not in consumed]
            if not available:
                continue
            top = available[0]
            runner_up = available[1].score if len(available) > 1 else 0.0
            margin = top.score - runner_up
            lexical_best = max(c.fuzzy_score for c in scored[profile.column])
            if policy.classify_mapping(top.score, runner_up, lexical_best) is not Disposition.AUTO:
                continue
            if best is None or top.score > best[0]:
                best = (top.score, margin, profile.column, top.target_field)
        if best is None:
            break
        score, margin, column, field_name = best

        # Before taking the field, check whether another column has an equally
        # good claim on it. A column can be individually confident and still be
        # the wrong source: when a file carries both 'Official Email' and
        # 'Mail ID', each looks like the work address on its own, and only the
        # comparison between them reveals the doubt. Assigning the marginally
        # higher score here would quietly put the personal address in the field
        # the whole HRMS keys off.
        rivals = _rivals_for(field_name, column, profiles, scored, resolved, score)
        if rivals:
            contenders = [column, *rivals]
            winner = decisions.get(f"contest:{source_file}:{field_name}")
            if winner in contenders:
                for contender in contenders:
                    if contender == winner:
                        continue
                    resolved.discard(contender)
                mappings.append(
                    ColumnMapping(
                        source_file=source_file,
                        column=winner,
                        target_field=field_name,
                        disposition=Disposition.AUTO,
                        confidence=1.0,
                        margin=1.0,
                        rationale=(
                            f"A consultant confirmed '{winner}' holds {field_name}, over "
                            f"{', '.join(repr(c) for c in contenders if c != winner)}."
                        ),
                        candidates=scored[winner][:4],
                        provenance="human",
                    )
                )
                consumed.add(field_name)
                resolved.add(winner)
                continue
            emit(f"'{field_name}' is claimed by {len(contenders)} columns in {source_file} - asking")
            escalations.append(
                _contest_escalation(run_id, source_file, field_name, contenders, scored, by_column)
            )
            for contender in contenders:
                rival_score = _score_for(scored[contender], field_name)
                mappings.append(
                    ColumnMapping(
                        source_file=source_file,
                        column=contender,
                        target_field=None,
                        disposition=Disposition.ESCALATED,
                        confidence=rival_score,
                        margin=0.0,
                        rationale=(
                            f"Competes with "
                            f"{', '.join(repr(c) for c in contenders if c != contender)} "
                            f"for {field_name}; the scores are too close to pick between them."
                        ),
                        candidates=scored[contender][:4],
                    )
                )
                resolved.add(contender)
            consumed.add(field_name)
            continue

        mappings.append(
            ColumnMapping(
                source_file=source_file,
                column=column,
                target_field=field_name,
                disposition=Disposition.AUTO,
                confidence=score,
                margin=margin,
                rationale=(
                    f"Clear match at {score:.2f}, {margin:.2f} clear of the next "
                    f"candidate still available."
                ),
                candidates=scored[column][:4],
            )
        )
        consumed.add(field_name)
        resolved.add(column)

    # Whatever is left is either not in the schema at all, or genuinely contested.
    for profile in profiles:
        if profile.column in resolved:
            continue
        available = [c for c in scored[profile.column] if c.target_field not in consumed]
        candidates = available or scored[profile.column]
        top = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        runner_up_score = runner_up.score if runner_up else 0.0
        margin = top.score - runner_up_score
        lexical_best = max(c.fuzzy_score for c in scored[profile.column])
        disposition = policy.classify_mapping(top.score, runner_up_score, lexical_best)

        if disposition is Disposition.IGNORED:
            mappings.append(
                ColumnMapping(
                    source_file=source_file,
                    column=profile.column,
                    target_field=None,
                    disposition=Disposition.IGNORED,
                    confidence=top.score,
                    margin=margin,
                    rationale=(
                        f"Nothing in the target schema describes this column - the closest, "
                        f"{top.target_field}, only reaches {top.score:.2f}. Left behind rather "
                        f"than migrated."
                    ),
                    candidates=candidates[:4],
                )
            )
            continue

        why = (
            f"scores {top.score:.2f} for {top.target_field} against "
            f"{runner_up_score:.2f} for {runner_up.target_field} - too close to call"
            if runner_up and margin < policy.MAPPING_MARGIN_MIN
            else f"the best available match only reaches {top.score:.2f}"
        )
        emit(f"Ambiguous column '{profile.column}' in {source_file} - asking")
        escalations.append(
            Escalation(
                run_id=run_id,
                type=EscalationType.COLUMN_MAPPING,
                subject=f"map:{source_file}:{profile.column}",
                title=f"Which field is '{profile.column}'?",
                question=f"Column '{profile.column}' in {source_file} {why}.",
                evidence={
                    "source_file": source_file,
                    "column": profile.column,
                    "inferred_type": profile.inferred_type,
                    "sample_values": profile.samples[:5],
                    "null_rate": round(profile.null_rate, 2),
                    "distinct_values": profile.cardinality,
                    "rows": profile.row_count,
                    "scores": [c.as_dict() for c in candidates[:4]],
                    "recommendation": _recommendation(by_column[profile.column], candidates[:3]),
                },
                options=[
                    {
                        "value": c.target_field,
                        "label": c.target_field,
                        "detail": f"score {c.score:.2f}",
                    }
                    for c in candidates[:4]
                ]
                + [
                    {
                        "value": "__ignore__",
                        "label": "Do not migrate this column",
                        "detail": "",
                    }
                ],
                affected_records=[],
            )
        )
        mappings.append(
            ColumnMapping(
                source_file=source_file,
                column=profile.column,
                target_field=None,
                disposition=Disposition.ESCALATED,
                confidence=top.score,
                margin=margin,
                rationale=why,
                candidates=candidates[:4],
            )
        )

    return mappings, escalations


def _score_for(candidates: list[MappingCandidate], field_name: str) -> float:
    for candidate in candidates:
        if candidate.target_field == field_name:
            return candidate.score
    return 0.0


def _rivals_for(
    field_name: str,
    winner: str,
    profiles: list[ColumnProfile],
    scored: dict[str, list[MappingCandidate]],
    resolved: set[str],
    winning_score: float,
) -> list[str]:
    """Other unresolved columns with an equally strong claim on the same field."""
    rivals: list[str] = []
    for profile in profiles:
        if profile.column == winner or profile.column in resolved:
            continue
        rival_score = _score_for(scored[profile.column], field_name)
        if rival_score < policy.MAPPING_AUTO_MIN:
            continue
        if winning_score - rival_score < policy.MAPPING_MARGIN_MIN:
            rivals.append(profile.column)
    return rivals


def _contest_escalation(
    run_id: str,
    source_file: str,
    field_name: str,
    contenders: list[str],
    scored: dict[str, list[MappingCandidate]],
    by_column: dict[str, ColumnProfile],
) -> Escalation:
    ranked = sorted(
        contenders, key=lambda c: _score_for(scored[c], field_name), reverse=True
    )
    return Escalation(
        run_id=run_id,
        type=EscalationType.COLUMN_MAPPING,
        subject=f"contest:{source_file}:{field_name}",
        title=f"Which column is '{field_name}'?",
        question=(
            f"{' and '.join(repr(c) for c in ranked)} in {source_file} both look like "
            f"{field_name}, and only one of them can be. Which holds the real value?"
        ),
        evidence={
            "source_file": source_file,
            "target_field": field_name,
            "contest": True,
            "columns": [
                {
                    "column": column,
                    "score": round(_score_for(scored[column], field_name), 3),
                    "sample_values": by_column[column].samples[:5],
                    "null_rate": round(by_column[column].null_rate, 2),
                    "distinct_values": by_column[column].cardinality,
                }
                for column in ranked
            ],
        },
        options=[
            {
                "value": column,
                "label": f"'{column}' is {field_name}",
                "detail": f"score {_score_for(scored[column], field_name):.2f}",
            }
            for column in ranked
        ],
    )


def _memory_key(profile: ColumnProfile) -> str:
    """Columns are remembered by normalised name, not by file.

    The same legacy system exports the same header to every client, so a
    decision made once should carry across runs and across customers.
    """
    return profile.column.strip().lower().replace("_", " ")

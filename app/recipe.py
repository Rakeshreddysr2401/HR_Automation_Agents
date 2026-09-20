"""The migration recipe: a run's decisions, exported as something reusable.

This is the productisation step, and the reason it exists is a claim about what
the agent is actually for.

A single migration is a service engagement. What a consultant learns doing it -
that this client's `emp_cd` is the employee code, that their HRIS writes dates
day-first, that `Engg` means Engineering - is knowledge that currently evaporates
the moment the project closes. The next client, and often the next *file from the
same client*, starts from nothing.

A recipe is that knowledge as a file. It captures every rule the run settled on,
separated by how it was reached:

    confirmed   a human answered it, so it is authoritative
    inferred    the agent applied it and flagged it for audit
    automatic   deterministic or unambiguous

Feeding it back in (``POST /api/runs`` with ``recipe``) pre-answers those subjects
on the next run, so the second migration of a similar export asks a fraction of
what the first one did. It is plain YAML on purpose: a consultant can read it,
diff it in a pull request, and correct a line by hand without the app.

What it deliberately does *not* contain is any record data. A recipe is rules
only - which is the same property that lets the pipeline scale flatly, applied to
a different problem. It can be committed to a repository without a PII review.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import yaml

from app.schema import TargetSchema, get_schema
from app.store import Store

# Audit actions that record a rule rather than a per-row edit. Everything else
# in the trail is an application of one of these, and belongs in the audit view
# rather than in a recipe.
RULE_ACTIONS = {
    "infer_date_convention": "inferred",
    "set_date_convention": "confirmed",
    "normalise_values": "automatic",
}

PROVENANCE_RANK = {"human": 0, "memory": 1, "scored": 2}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build(
    run_id: str,
    store: Store,
    schema: TargetSchema | None = None,
) -> dict[str, Any]:
    """Assemble the recipe for one run from what was persisted about it."""
    schema = schema or get_schema()
    run = store.get_run(run_id) or {}
    mappings = store.list_mappings(run_id)
    audit = store.list_audit(run_id)
    decisions = store.get_decisions(run_id)
    summary = run.get("summary") or {}

    return {
        "recipe_version": 1,
        "generated_at": _now(),
        "source_run": run_id,
        "target": {
            "entity": schema.entity,
            "schema_version": schema.version,
        },
        "provenance": {
            "files": run.get("files", []),
            "columns_seen": summary.get("columns", 0),
            "records_produced": summary.get("records", 0),
            "questions_asked": len(decisions),
        },
        "field_mappings": _field_mappings(mappings),
        "ignored_columns": _ignored(mappings),
        "date_conventions": _date_conventions(audit),
        "value_mappings": _value_mappings(audit, decisions),
        "identity_rules": _identity_rules(decisions),
        "answers": _answers(decisions),
        "notes": _notes(summary, decisions),
    }


def to_yaml(recipe: dict[str, Any]) -> str:
    """Render as YAML, keeping the authored key order rather than sorting it.

    Order carries meaning here - mappings before conventions before answers is
    the order a reader needs them in - and alphabetising would scatter it.
    """
    header = (
        "# Migration recipe\n"
        "#\n"
        "# Every rule this run settled on, and how each one was reached:\n"
        "#   confirmed - a human answered it\n"
        "#   inferred  - the agent applied it and flagged it\n"
        "#   automatic - deterministic, or the evidence left one answer\n"
        "#\n"
        "# Contains rules only, never records. Safe to commit.\n"
        "# Replay it with:  POST /api/runs  {\"recipe\": <this file>}\n\n"
    )
    return header + yaml.safe_dump(recipe, sort_keys=False, allow_unicode=True, width=88)


def _field_mappings(mappings: list[dict]) -> list[dict[str, Any]]:
    """One entry per source column that reached a target field."""
    rows = [m for m in mappings if m.get("target_field")]
    rows.sort(key=lambda m: (m["source_file"], m["column"]))
    return [
        {
            "source_file": m["source_file"],
            "source_column": m["column"],
            "target_field": m["target_field"],
            "how": {
                "human": "confirmed",
                "memory": "confirmed",
                "scored": "inferred" if m["disposition"] == "flagged" else "automatic",
            }.get(m.get("provenance", "scored"), "automatic"),
            "confidence": m.get("confidence"),
            "margin": m.get("margin"),
            **({"transform": m["transform"]} if m.get("transform") else {}),
        }
        for m in rows
    ]


def _ignored(mappings: list[dict]) -> list[dict[str, Any]]:
    """Columns dropped on purpose.

    Worth exporting: on the next run these are the ones to check first, because
    "no home in the target schema" is the judgment most likely to be wrong when
    the schema grows a field.
    """
    return [
        {
            "source_file": m["source_file"],
            "source_column": m["column"],
            "reason": m.get("rationale", ""),
        }
        for m in mappings
        if not m.get("target_field")
    ]


def _date_conventions(audit: list[dict]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in audit:
        action = entry.get("action")
        if action not in ("infer_date_convention", "set_date_convention"):
            continue
        entity = str(entry.get("entity", ""))
        if not entity.startswith("column:"):
            continue
        _, _, rest = entity.partition("column:")
        source_file, _, column = rest.partition(":")
        out.append(
            {
                "source_file": source_file,
                "source_column": column,
                "convention": entry.get("after"),
                "how": RULE_ACTIONS.get(action, "automatic"),
                "evidence": entry.get("rationale", ""),
            }
        )
    return out


def _value_mappings(audit: list[dict], decisions: dict[str, Any]) -> list[dict[str, Any]]:
    """Enum vocabulary: raw client value -> the schema's word for it.

    Collapsed to the distinct pairs. The audit has one entry per row that was
    rewritten; the rule is the pair, and repeating it four hundred times would
    make the recipe unreadable and no more true.
    """
    seen: dict[tuple[str, str], dict[str, Any]] = {}

    for entry in audit:
        if entry.get("action") != "canonicalise_value":
            continue
        before, after = entry.get("before"), entry.get("after")
        if before is None or after is None:
            continue
        key = (str(before).lower(), str(after))
        seen.setdefault(
            key,
            {
                "from": str(before),
                "to": str(after),
                "how": "inferred" if entry.get("disposition") == "flagged" else "automatic",
                "rows": 0,
            },
        )
        seen[key]["rows"] += 1

    # A human answer overrides whatever the agent scored for the same value.
    for subject, answer in decisions.items():
        if not subject.startswith("enum:") or not isinstance(answer, str):
            continue
        # subject shape: "enum:<target_field>:<raw value>"
        parts = subject.split(":", 2)
        if len(parts) < 3:
            continue
        field_name, raw = parts[1], parts[2]
        seen[(raw.lower(), answer)] = {
            "field": field_name,
            "from": raw,
            "to": "(blank)" if answer == "__blank__" else answer,
            "how": "confirmed",
            "rows": 0,
        }

    return sorted(seen.values(), key=lambda v: (-v["rows"], v["from"]))


def _identity_rules(decisions: dict[str, Any]) -> list[dict[str, Any]]:
    """How duplicate-looking pairs were adjudicated.

    Exported separately from the other answers because this is the judgment a
    reviewer most wants to see carried forward deliberately rather than
    silently: "keep both" on a rehire is a policy statement about the client's
    data, not a fact about two rows.
    """
    def _meaning(ans: Any) -> str:
        s = str(ans)
        if s == "merge" or s.startswith("merge:"):
            return "one person, two rows - combine them"
        if s == "separate":
            return "two distinct employment records - keep both"
        return s

    return [
        {
            "pair": subject.split(":", 1)[1],
            "decision": answer,
            "meaning": _meaning(answer),
        }
        for subject, answer in sorted(decisions.items())
        if subject.startswith(("identity:", "rehire:"))
    ]


def _answers(decisions: dict[str, Any]) -> dict[str, Any]:
    """Every human answer, keyed by the stable subject that replays it.

    This is the half of the file the machine reads. The sections above are the
    half a person reads; this one is what `apply` turns back into decisions.
    """
    return {subject: answer for subject, answer in sorted(decisions.items())}


def _notes(summary: dict[str, Any], decisions: dict[str, Any]) -> list[str]:
    notes = []
    columns = summary.get("columns") or 0
    if columns:
        settled = columns - int(summary.get("columns_ignored") or 0)
        notes.append(
            f"{settled} of {columns} columns reached the target schema; "
            f"{len(decisions)} question(s) needed a person."
        )
    if summary.get("breaker_tripped"):
        notes.append(
            "The batch circuit breaker tripped on this run - treat these rules as "
            "provisional until a clean run confirms them."
        )
    notes.append(
        "Replaying this pre-answers the subjects under 'answers'. Anything the next "
        "export does differently still comes back as a question."
    )
    return notes


def apply(recipe: dict[str, Any]) -> dict[str, Any]:
    """Turn a recipe back into decisions the pipeline can be seeded with.

    Only the `answers` block is replayed, and deliberately so. The mappings and
    conventions in the rest of the file are a *record* of what this run decided,
    not instructions - re-deriving them against the new file is what catches the
    case where the next export genuinely differs. Replaying a human's answer is
    safe because subjects are stable and semantic: if the new file has no such
    column, its subject never comes up and the answer is simply unused.
    """
    if not isinstance(recipe, dict):
        raise ValueError("a recipe must be a mapping")
    version = recipe.get("recipe_version")
    if version not in (None, 1):
        raise ValueError(f"unsupported recipe_version {version!r}; this build reads version 1")
    answers = recipe.get("answers") or {}
    if not isinstance(answers, dict):
        raise ValueError("'answers' must be a mapping of subject -> answer")
    return dict(answers)


def parse(text: str) -> dict[str, Any]:
    """Read a recipe from YAML (or JSON, which is a subset of it)."""
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError("a recipe file must contain a YAML mapping")
    return loaded

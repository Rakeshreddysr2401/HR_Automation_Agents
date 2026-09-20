"""The dry run: exactly what will be sent, before anything is sent.

Every migration tool a client has ever trusted has this screen, and the reason
is not caution — it is that "the agent says 41 records are ready" and "here are
the 41 payloads, and here is the 12 fields' worth of edits inside them that you
never approved" are different claims, and only the second one is checkable.

It matters more here than in a hand-built migration, because this agent's whole
argument is that most decisions *should not* be approved individually. That
argument only holds if the aggregate is inspectable at the end. The escalation
queue is where the agent asks; this is where a consultant can audit everything it
didn't ask about, per record, in the shape it will actually arrive.

Built entirely from what is already persisted — records, mappings and the audit
trail — so producing it costs no model calls, touches no source file, and cannot
disagree with what the push will do.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.schema import TargetSchema, get_schema
from app.store import Store

# Audit actions that changed a value inside a record, as opposed to recording a
# column-level rule. These are what a reviewer wants attributed per record.
VALUE_ACTIONS = {
    "canonicalise_value": "value mapped to the schema's vocabulary",
    "repair_value": "malformed value repaired",
    "merge_duplicate": "merged with another row for the same person",
    "normalise_values": "spacing and casing tidied",
}


def build(run_id: str, store: Store, schema: TargetSchema | None = None) -> dict[str, Any]:
    """The full plan: per-record payloads, their edits, and what is held back."""
    schema = schema or get_schema()
    records = store.list_records(run_id)
    mappings = store.list_mappings(run_id)
    audit = store.list_audit(run_id)

    edits = _edits_by_entity(audit)
    origin = _field_origin(mappings)
    pii = schema.pii_fields

    will_send: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []

    for record in records:
        entry = _describe(record, edits, origin, pii, schema)
        if record.get("ready") and record.get("push_status") in ("pending", "failed"):
            will_send.append(entry)
        else:
            held.append(entry)

    changed = sum(len(r["changes"]) for r in will_send)
    return {
        "run_id": run_id,
        "entity": schema.entity,
        "will_send": will_send,
        "held_back": held,
        "totals": {
            "will_send": len(will_send),
            "held_back": len(held),
            "fields_changed": changed,
            "records_with_changes": sum(1 for r in will_send if r["changes"]),
            "already_loaded": sum(
                1 for r in records if r.get("push_status") == "success"
            ),
        },
    }


def _edits_by_entity(audit: list[dict]) -> dict[str, list[dict[str, Any]]]:
    """Value-level audit entries, grouped by the record they touched.

    Column-level entries (`column:<file>:<name>`) are skipped here: they are
    rules, and a rule shown against all fifty records it applied to is noise.
    They surface in the Decisions view instead.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in audit:
        action = item.get("action")
        if action not in VALUE_ACTIONS:
            continue
        entity = str(item.get("entity", ""))
        if not entity or entity.startswith("column:"):
            continue
        grouped[entity].append(
            {
                "action": action,
                "what": VALUE_ACTIONS[action],
                "before": item.get("before"),
                "after": item.get("after"),
                "why": item.get("rationale", ""),
                "disposition": item.get("disposition"),
            }
        )
    return grouped


def _field_origin(mappings: list[dict]) -> dict[str, list[str]]:
    """Target field -> the source columns that feed it.

    A field fed by two files is the interesting case: it means the reconciler
    had to pick, and a reviewer should be able to see that it did.
    """
    origin: dict[str, list[str]] = defaultdict(list)
    for mapping in mappings:
        target = mapping.get("target_field")
        if not target:
            continue
        origin[target].append(f"{mapping['source_file']}.{mapping['column']}")
    return dict(origin)


def _describe(
    record: dict[str, Any],
    edits: dict[str, list[dict[str, Any]]],
    origin: dict[str, list[str]],
    pii: set[str],
    schema: TargetSchema,
) -> dict[str, Any]:
    """One record's row in the dry run."""
    fields = {k: v for k, v in (record.get("fields") or {}).items() if not k.startswith("_")}

    # Every audit entry that named one of this record's source rows. Records are
    # keyed by identity, source rows by "file.csv#12", so a merged person
    # collects the edits made to both of its halves.
    changes: list[dict[str, Any]] = []
    for source in record.get("sources") or []:
        changes.extend(edits.get(source, []))
    changes.extend(edits.get(record.get("key", ""), []))

    payload = {
        name: fields.get(name)
        for name in (f.name for f in schema.fields)
        if fields.get(name) not in (None, "")
    }

    return {
        "key": record.get("key"),
        "employee_code": fields.get("employee_code"),
        "name": " ".join(
            part for part in (fields.get("first_name"), fields.get("last_name")) if part
        ).strip(),
        "sources": record.get("sources") or [],
        "merged": len(record.get("sources") or []) > 1,
        # The exact body the loader will POST, with PII fields named so the UI
        # can mask them on screen. The values are real - this is the payload -
        # but nothing here has ever been near a model.
        "payload": payload,
        "pii_fields": sorted(pii & set(payload)),
        "multi_source_fields": sorted(
            name for name in payload if len(origin.get(name, [])) > 1
        ),
        "changes": changes,
        "errors": record.get("errors") or [],
        "blocked_by": record.get("blocked_by") or [],
        "push_status": record.get("push_status"),
        "reason_held": _reason_held(record),
    }


def _reason_held(record: dict[str, Any]) -> str:
    if record.get("ready") and record.get("push_status") == "success":
        return "already loaded"
    if record.get("blocked_by"):
        return f"waiting on {len(record['blocked_by'])} open question(s)"
    if record.get("errors"):
        return "; ".join(str(e) for e in record["errors"][:3])
    if record.get("push_status") == "rejected":
        return "the target system refused it"
    if record.get("push_status") == "skipped":
        return "deliberately skipped"
    return ""

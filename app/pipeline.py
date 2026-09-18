"""The migration, as a pure function of its inputs.

    run(files, decisions) -> MigrationResult

That signature is the design. Human answers are not patches applied to a finished
result; they are *inputs*, and the pipeline is re-run with them folded in. Two
things follow.

**Consistency.** Confirming which column holds `work_email` does not merely fill one
field. It lets the identity resolver match the two files against each other, which
changes which records merge, which changes what validates, which changes what gets
pushed. Patching the output would leave every one of those downstream effects stale.
Re-running cannot.

**Replayability.** The same files and the same decisions always produce the same
result, so a migration can be re-run, diffed, tested against a golden expectation,
and exported as a reusable recipe. Everything expensive is cached or deterministic,
so a re-run costs little - embeddings are memoised, and the model is consulted only
for the wording of questions.

Decisions are keyed by escalation `subject`, a stable description of *what was
asked* that survives re-runs - unlike escalation ids, which are regenerated each
time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app import supervisor
from app.agents import cleanser, identity, mapper, profiler, validator
from app.models import (
    AuditEntry,
    ColumnMapping,
    ColumnProfile,
    Disposition,
    Escalation,
    TargetRecord,
)
from app.schema import TargetSchema, get_schema

Emit = Callable[[str], None]

MAX_ROUNDS = 6


@dataclass
class MigrationResult:
    run_id: str
    profiles: list[ColumnProfile] = field(default_factory=list)
    mappings: list[ColumnMapping] = field(default_factory=list)
    records: list[TargetRecord] = field(default_factory=list)
    escalations: list[Escalation] = field(default_factory=list)
    audit: list[AuditEntry] = field(default_factory=list)
    breaker: Escalation | None = None
    elapsed_seconds: float = 0.0

    @property
    def open_escalations(self) -> list[Escalation]:
        return list(self.escalations)

    @property
    def ready_records(self) -> list[TargetRecord]:
        return [
            r
            for r in self.records
            if r.ready and r.push_status not in ("skipped", "success")
        ]

    def summary(self) -> dict[str, Any]:
        auto = sum(1 for m in self.mappings if m.disposition is Disposition.AUTO)
        flagged = sum(1 for m in self.mappings if m.disposition is Disposition.FLAGGED)
        ignored = sum(1 for m in self.mappings if m.disposition is Disposition.IGNORED)
        return {
            "run_id": self.run_id,
            "columns": len(self.mappings),
            "columns_auto": auto,
            "columns_flagged": flagged,
            "columns_ignored": ignored,
            "records": len(self.records),
            "records_ready": len(self.ready_records),
            "records_blocked": sum(1 for r in self.records if r.blocked_by),
            "records_skipped": sum(1 for r in self.records if r.push_status == "skipped"),
            "escalations": len(self.escalations),
            "escalations_by_type": {
                t: sum(1 for e in self.escalations if e.type.value == t)
                for t in {e.type.value for e in self.escalations}
            },
            "audit_entries": len(self.audit),
            "breaker_tripped": self.breaker is not None,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }


def run(
    files: list[str],
    run_id: str,
    decisions: dict[str, Any] | None = None,
    memory: dict[str, str] | None = None,
    schema: TargetSchema | None = None,
    emit: Emit = lambda _: None,
) -> MigrationResult:
    started = time.monotonic()
    decisions = dict(decisions or {})
    schema = schema or get_schema()
    result = MigrationResult(run_id=run_id)

    emit(f"Reading {len(files)} source file(s)")
    frames = profiler.load_sources(files)
    result.profiles = profiler.profile_all(frames)
    emit(
        f"Profiled {len(result.profiles)} columns across "
        f"{sum(len(f) for f in frames.values())} rows"
    )

    pii_columns = [p for p in result.profiles if p.is_pii]
    if pii_columns:
        emit(
            f"Masked {len(pii_columns)} column(s) holding personal identifiers - "
            f"raw values stay out of the model and the audit trail"
        )

    result.mappings, mapping_escalations = mapper.map_columns(
        result.profiles, schema, run_id, memory=memory, decisions=decisions, emit=emit
    )

    cleaned = cleanser.clean(frames, result.mappings, schema, run_id, decisions, emit)
    result.audit.extend(cleaned.audit)

    result.records, identity_escalations, identity_audit = identity.resolve(
        cleaned.rows, schema, run_id, decisions, emit
    )
    result.audit.extend(identity_audit)

    # Questions raised so far already stand for the records they touch. Linking
    # them first is what stops the validator asking the same thing a second time
    # in a different shape.
    early = mapping_escalations + cleaned.escalations + identity_escalations
    pending = supervisor.pending_fields(result.mappings, cleaned.blocked_fields)
    per_record = supervisor.link_to_records(early, result.records)

    validation_escalations, validation_audit = validator.validate(
        result.records,
        schema,
        run_id,
        pending_fields=pending,
        pending_per_record=per_record,
        decisions=decisions,
        emit=emit,
    )
    result.audit.extend(validation_audit)

    result.escalations = early + validation_escalations
    supervisor.attach_blocks(result.escalations, result.records)

    result.breaker = supervisor.evaluate_batch(
        result.escalations, result.records, result.mappings, run_id
    )
    if result.breaker and decisions.get(result.breaker.subject) != "continue":
        emit(f"Stopping early: {result.breaker.title.lower()}")
        result.escalations = [result.breaker]
        result.elapsed_seconds = time.monotonic() - started
        return result

    result.elapsed_seconds = time.monotonic() - started
    emit(
        f"Run complete in {result.elapsed_seconds:.1f}s - "
        f"{len(result.ready_records)} records ready, {len(result.escalations)} questions open"
    )
    return result

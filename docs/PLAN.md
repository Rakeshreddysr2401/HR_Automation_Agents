# Build plan

Phases are ordered so that each one leaves something demonstrable. If the build had
to stop at the end of any phase, what exists would still run end to end.

Legend: `[x]` done · `[~]` in progress · `[ ]` not started

---

## Phase 0 — Foundations `[x]`

- [x] Target schema authored (`schema/target_employee.yaml`), 21 fields with
      alias-bearing descriptions, formats, enums, PII flags and business rules.
      Nothing was supplied with the brief, so both the schema and the source data
      are ours to define.
- [x] Sample data generator (`scripts/make_sample_data.py`) producing three files.
      Every defect is deliberate and exercises exactly one policy branch, so the
      golden test can assert the precise escalation set.
- [x] Settings, PII masking, provider-agnostic model layer with graceful
      degradation when no model server is reachable.

## Phase 1 — The decision core `[x]`

- [x] `app/policy.py` — every act-vs-ask threshold in one reviewable file.
- [x] **Profiler** — reads files, profiles columns, detects PII by name and shape.
- [x] **Schema Mapper** — semantic + lexical + structural scoring, resolved as a
      per-file assignment so columns compete for fields.
- [x] **Cleanser** — normalisation, date-convention inference, enum canonicalisation.
- [x] `app/dates.py` — infers a column's convention from its unambiguous rows.
- [x] **Identity Resolver** — merges on unique identifiers, escalates rehire-vs-duplicate.

Result on the sample data: 35 columns → 34 mapped autonomously, 52 people
reconciled, **5 escalations**, all of them genuine.

## Phase 2 — Validation and integrity `[~]`

- [ ] **Validator** — required fields, formats, enums, business rules; one
      deterministic repair attempt, then escalate on the second failure.
- [ ] Referential integrity — `manager_email` must resolve to an employee in the
      dataset; orphan managers escalate.
- [ ] Reporting-cycle detection — one escalation per cycle, listing its members.
- [ ] Fields pending an unresolved mapping are marked *pending*, not *invalid*.

## Phase 3 — Orchestration `[ ]`

- [ ] `MigrationState` and the LangGraph pipeline wiring the agents together.
- [ ] Supervisor gate: aggregate the queue, apply the circuit breaker, `interrupt()`.
- [ ] Resume with human decisions via `Command(resume=...)`, re-validate, continue.
- [ ] SQLite persistence for runs, escalations, audit, records and mapping memory.
- [ ] `SqliteSaver` checkpointing so a run survives a server restart mid-review.

## Phase 4 — Integration `[ ]`

- [ ] Mock target API with deterministic failure injection and idempotency keys.
- [ ] **Loader** — push per record, auto-retry 5xx with backoff, escalate 4xx.
- [ ] Rollback via compensating deletes, recorded in the audit trail.
- [ ] Dry-run diff: exactly what will change, before anything is sent.

## Phase 5 — Supervision UI `[ ]`

- [ ] FastAPI routes and an SSE stream of live agent activity.
- [ ] React + TypeScript + Vite app, built output served by FastAPI.
- [ ] Run view — file drop, live timeline, counters for auto / flagged / escalated.
- [ ] Escalation queue — a rich card per escalation type, each showing enough
      evidence to decide at a glance; approve, correct inline, or reject.
- [ ] Bulk resolution and keyboard triage, so one decision can settle forty rows.
- [ ] Decisions view — everything the agent did alone, transparent but not blocking.
- [ ] Push results with retry and rollback controls.
- [ ] Audit trail — timestamp, actor, before → after, rationale. PII masked.

## Phase 6 — The differentiators `[ ]`

- [ ] **Mapping memory** — a human resolution becomes a reusable rule, so the same
      column is never asked about twice. Turns review from a recurring cost into a
      compounding asset, which is the whole point in an implementation practice.
- [ ] **Migration recipe** — export the decision set as reviewable YAML, replayable
      against the next client's files.
- [ ] **Circuit breaker** — when too much escalates, raise one batch-level question
      instead of flooding the queue.
- [ ] **Threshold sweep** (`scripts/sweep_thresholds.py`) — measure what each
      threshold choice costs, so "why 0.82?" has an answer backed by numbers.

## Phase 7 — Delivery `[ ]`

- [ ] `pytest` suite: policy boundaries, a golden run asserting the exact escalation
      set, interrupt/resume, retry/rollback, recipe round-trip.
- [ ] Frontend tests for the SSE parser and escalation-card decisions.
- [ ] `docs/WRITEUP.md` — one page: approach, where the line was drawn and why,
      what would come next.
- [ ] `docs/DEMO.md` — a 90-second script that resolves an escalation end to end.
- [ ] Dockerfile and compose for a one-command run.

---

## Deliberately not built

Recorded here because scope discipline is part of the answer, and because these are
the honest next steps rather than gaps nobody noticed.

- **Effective-dated history.** HR records are temporal; promotions and transfers are
  changes over time, not overwrites. A real migration carries that history.
- **Multi-entity dependency ordering.** Org units before employees before payroll,
  since each references the last.
- **Active learning on thresholds.** Resolution history is labelled training data;
  the thresholds could be fitted to it rather than set by hand.
- **Connector-based ingestion.** File drops are the demo; real clients want SAP,
  PeopleSoft and Zoho pulled directly.
- **Parallel chunked processing.** The decision/execution split already makes this
  straightforward — rules are decided once, then applied to shards independently.

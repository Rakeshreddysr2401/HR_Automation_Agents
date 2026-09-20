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

Result on the sample data: 35 columns → 33 mapped or deliberately ignored
autonomously, 54 rows reconciled into 41 people, **11 questions** across three
review rounds, all of them genuine.

## Phase 2 — Validation and integrity `[x]`

- [x] **Validator** — required fields, formats, enums, business rules; one
      deterministic repair attempt, then escalate on the second failure.
- [x] Referential integrity — `manager_email` must resolve to an employee in the
      dataset; orphan managers escalate, grouped by the missing manager rather than
      by report, so one departed manager is one question.
- [x] Reporting-cycle detection — one escalation per cycle, listing its members.
- [x] Fields pending an unresolved mapping are marked *pending*, not *invalid*.
- [x] **Supervisor** — links questions to the records they already cover, so the
      validator never re-asks something the queue is holding in another shape.

## Phase 3 — Orchestration `[x]`

- [x] `pipeline.run(files, decisions)` as a **pure function** — human answers are
      inputs re-run through the whole pipeline, not patches applied to its output.
      This is what keeps downstream results consistent with an upstream answer.
- [x] Stable escalation `subject` keys that survive a re-run, which is what lets an
      answer be replayed and remembered.
- [x] `MigrationState` and the LangGraph graph: analyse → gate → analyse, then push.
- [x] Supervisor gate: aggregate the queue, apply the circuit breaker, `interrupt()`.
- [x] Resume with human decisions via `Command(resume=...)`, re-analyse, continue.
- [x] SQLite persistence for runs, escalations, audit, records and mapping memory.
- [x] `AsyncSqliteSaver` checkpointing so a run survives a restart mid-review.

## Phase 4 — Integration `[~]`

- [x] Mock target API with deterministic failure injection and idempotency keys.
- [x] **Loader** — push per record, auto-retry 5xx with backoff, escalate 4xx.
- [x] Rollback via compensating deletes, requiring a reason, recorded in the audit.
- [x] Dry-run diff (`app/plan.py`): exactly what will be sent, per record,
      with every autonomous edit attributed and PII masked on screen.

## Phase 5 — Supervision UI `[~]`

- [x] FastAPI routes and an SSE stream of live agent activity.
- [x] React + TypeScript + Vite app, built output served by FastAPI.
- [x] Run view — file drop, live timeline, counters for auto / flagged / escalated.
- [x] Escalation queue — a rich card per escalation type, each showing enough
      evidence to decide at a glance; approve, correct inline, or reject.
- [x] Bulk resolution and keyboard triage (`j`/`k` to move, `1-9` to choose,
      `u` to undo), so a queue is worked rather than clicked through.
- [x] Decisions view — everything the agent did alone, transparent but not blocking,
      plus what it has learned from previous answers.
- [x] Push results with retry and rollback controls (rollback demands a reason).
- [x] Audit trail — timestamp, actor, before → after, rationale. PII masked.
      Filterable by actor, exportable as CSV.
- [x] Mapping view — every column, its target, its score and its candidate set.
- [x] Dry-run view — per-record payloads and the recipe export.
- [x] Boundary view — `app/policy.py` rendered live over `GET /api/policy`, so the
      screen explaining the agent's judgment cannot drift from the code enforcing it.
- [x] Design token layer (`web/src/styles/tokens.css`) — theme, accent and density
      as three runtime-switchable axes; Tailwind aliased to the tokens so a theme
      flip needs no rebuild.
- [x] Command palette (`⌘K`), shortcut sheet (`?`), toasts, run history.
- [ ] Visual check in a browser — **still outstanding**; no browser tooling was
      available in this session. The build, the typecheck, the compiled CSS
      (all three axes present) and every API path have been verified, but layout
      and spacing have not been seen by a human.

## Phase 6 — The differentiators `[~]`

- [x] **Migration recipe** (`app/recipe.py`) — the decision set as reviewable YAML,
      replayable against the next client's files. Verified: a fresh run seeded with
      a previous run's recipe asks 1 question where it previously asked 10.
- [x] **Circuit breaker** — when too much escalates, one batch-level question
      instead of a flooded queue (`policy.should_trip_breaker`,
      `supervisor.evaluate_batch`).
- [x] **Threshold sweep** (`scripts/sweep_thresholds.py`) — measures what each
      threshold choice costs, so "why 0.82?" has an answer backed by numbers.
- [x] **Mapping memory** — a human answer becomes a reusable rule; the second run of
      the same files asks less, and `test_graph.py` asserts it.

## Phase 7 — Delivery `[~]`

- [x] `pytest` suite — 106 tests: policy boundaries and the self-description that
      keeps the UI honest, a golden run asserting the exact escalation set,
      interrupt/resume, retry/rollback, dates, PII, the recipe's no-record-data
      guarantee, and the dry run's completeness.
- [x] Frontend tests — 22 in Vitest: the SSE frame parser (including a frame split
      across chunks, the case a naive split loses silently), the appearance store,
      and escalation-card staging.
- [x] `docs/WRITEUP.md` — one page: approach, where the line was drawn and why,
      what would come next.
- [x] `docs/DEMO.md` — a 90-second script that resolves an escalation end to end.
- [x] Dockerfile and compose for a one-command run. Two stages so the runtime
      image carries no Node; state under one volume. **Not yet built** — no Docker
      daemon was running in this session, though the env-var contract it relies on
      is verified.

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

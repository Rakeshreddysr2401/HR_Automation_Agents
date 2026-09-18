# Architecture

## The one decision everything else follows from

**The model decides rules; deterministic code applies them.**

No record is ever put in a prompt. Each agent receives a *column profile* — name,
inferred type, null rate, distinct count, and five redacted sample values — and
returns a decision about that column. Python then applies the decision to all N rows.

Four things fall out of this, and they are the reason it is worth stating first:

- **It scales flatly.** A run costs roughly the same twenty to thirty model calls
  whether the file holds fifty rows or fifty thousand.
- **It is replayable.** Transformations are deterministic, so re-running the same
  inputs produces identical output, and a decision set can be exported and reused.
- **It is explainable.** Every decision carries a numeric basis, so "why did it do
  that?" has a real answer instead of "the model said so".
- **It is PII-safe.** Only redacted profiles leave the process, so PAN, Aadhaar and
  bank details never reach a model.

The alternative — stream rows through an LLM and ask it to emit cleaned records — is
faster to write and loses all four properties at once.

## Agents

Agents are separated by **kind of judgment**, not by pipeline stage. Each owns a
different question, and each question carries its own confidence policy, its own
evidence, and its own way of explaining itself to a human.

| Agent | The question it answers | When it refuses to answer |
|---|---|---|
| **Profiler** | What is in this column? | Never — it observes, it does not decide |
| **Schema Mapper** | Which target field is this column? | Two candidates are too close; or two columns claim one field |
| **Cleanser** | Can I safely rewrite this value? | A date column with no anchor; an enum value in the grey band |
| **Identity Resolver** | Are these rows the same human? | A near-match; a shared PAN that could be a rehire |
| **Validator** | Is this record loadable? | It still fails after one repair attempt |
| **Loader** | Is this failure retryable? | The target rejected it on business grounds |

A **Supervisor** owns run state, sequences the specialists, aggregates escalations
into a single queue, and makes the batch-level call the per-record agents cannot:
if a third of the file is escalating, the premise is more likely wrong than the data,
and the right response is one question rather than two hundred.

## How the agents communicate

Through **shared typed state**, not chat messages. A `MigrationState` acts as a
blackboard; each agent reads what it needs and writes its decisions back.

This is a deliberate departure from the conversational multi-agent pattern, where
agents hand off to each other through an LLM that decides who goes next. That design
suits problems where the next step is itself a judgment call. Here the sequence is
known in advance, so routing through a model would add latency, cost and
non-determinism and buy nothing. Passing several hundred employee records through
chat messages would be worse still — expensive, lossy, and unauditable.

Data flows through state. Only decisions and rationales pass through a model.

## Pipeline

```
ingest → profile → map_columns → clean → resolve_identity → validate → hierarchy_check
       → supervisor_gate ──(escalations?)──► interrupt() ──► [human resolves] ──► resume
                │                                                                  │
                └──────────────── none ────────────────────────────────────────────┤
                                                                                   ▼
                                              apply_resolutions → re-validate → dry_run_diff
                                                                  → push_to_target → summarise
```

Notes on the shape:

- **Escalations stream as they are found.** They are written to SQLite and pushed to
  the UI immediately, so a consultant can start triaging while the agent is still
  working. The `interrupt()` at the gate is the blocking point, not the discovery.
- **One gate, not one per record.** The whole queue is presented together. Asking
  forty separate questions that all have the same answer is the same failure as
  guessing, just louder.
- **Resolutions can unblock more than they touch.** Confirming which column holds
  `work_email` lets the identity resolver reconcile the two files against each other,
  which merges ten records that could not previously be matched.
- **Push failures open a second gate.** Retryable errors are retried automatically;
  a business rejection goes back to the human with the target's own reason attached.

## Human-in-the-loop mechanics

The pipeline is a LangGraph graph with a SQLite checkpointer. At the supervisor gate
it calls `interrupt()` with the escalation queue; the API surfaces that over SSE. When
the consultant submits decisions, the API resumes the same `thread_id` with
`Command(resume={...})`, and the graph continues from the checkpoint.

Because the run is checkpointed, review is not a race: the server can restart while a
queue is sitting unresolved and the run picks up where it stopped.

## Persistence

| Store | Holds | Why |
|---|---|---|
| `migration.db` | runs, records, escalations, audit trail, mapping memory | the reviewable history of what happened and why |
| `checkpoints.db` | LangGraph checkpoints | lets an interrupted run resume across restarts |

Mapping memory outlives the run on purpose: a column a consultant has already
identified should never be asked about again, in this client or the next one.

## Failure behaviour

The agent degrades rather than stops.

- **No model server.** Semantic scoring is unavailable, so mapping falls back to
  lexical evidence alone. Scores spread less, more columns fall below the confidence
  bar, and the agent escalates more. Failing toward asking is the correct direction.
- **A model returns nonsense.** Model output is only ever a *recommendation* rendered
  on an escalation card. It is never applied, so a bad suggestion costs a human one
  glance, not a corrupted field.
- **The target API is down.** Transient failures retry with backoff; persistent ones
  surface per record, with rollback available for whatever did land.

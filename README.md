# HR Work Automation

An autonomous agent that migrates a client's messy HR exports into a target HRMS
schema — mapping, cleaning and validating on its own, and stopping to ask a human
only where the data genuinely supports more than one answer.

Built for the Darwinbox Forward Deployed Engineer take-home.

---

## The problem this models

Every enterprise HRMS implementation starts the same way: the client sends employee
data spread across a legacy HRIS export, a payroll spreadsheet and whatever HR ops
kept by hand. Column names disagree, dates are written three ways, the same person
appears twice under different codes, and required fields are missing. An
implementation consultant then hand-maps it, which is slow and does not get faster
with the next client.

The interesting problem is not "clean the data". It is **deciding what the agent
should settle by itself and what it must escalate** — and building a supervision UI
that keeps a consultant informed without asking them to approve every field.

## What it does

1. **Ingests multiple files** describing the same entity with different shapes, and
   reconciles them into one dataset without being told the mapping field by field.
2. **Maps and cleans autonomously** — source-to-target field mapping, date formats,
   duplicates, casing and whitespace — without a human confirming each decision.
3. **Escalates only genuine ambiguity** — a column that could be two target fields, a
   date column with no way to tell day-first from month-first, a record that fails
   validation after a repair attempt, a pair that could be a rehire or a duplicate.
4. **Supervision UI** — live view of the agent working, a queue of escalations with
   the evidence needed to decide at a glance, and approve / correct / reject.
5. **Pushes to a mock target API** with per-record success and failure, automatic
   retry for transient errors, rollback, and a complete audit trail.

## Quickstart

```bash
uv venv --python 3.11
VIRTUAL_ENV="$PWD/.venv" uv pip install -e ".[dev]"

cd web && npm install && npm run build && cd ..   # the API serves the built UI
.venv/bin/uvicorn app.main:app --port 8000        # then open http://localhost:8000
```

Press *Run the sample migration*. The agent reads both bundled exports and stops
with **ten questions** out of 35 source columns and 52 people — everything else it
settles on its own.

Full instructions, model configuration and troubleshooting:
**[docs/RUNNING.md](docs/RUNNING.md)**. What is still outstanding:
**[docs/TODO.md](docs/TODO.md)**.

Models are optional. With a local Ollama or llama.cpp server reachable the agent
uses embeddings to score column mappings; with nothing reachable it falls back to
lexical scoring, escalates somewhat more, and still completes the run. Copy
`.env.example` to `.env` to point it at your own servers — chat and embeddings are
configured separately, because they usually run on different machines.

## How it decides

> **Escalate when being wrong is silent and irreversible.**
> **Auto-fix when being wrong would be loud and cheap to undo.**

Trimming a trailing space is safe: a wrong correction is visible immediately and
costs seconds to reverse. Choosing the wrong reading of `03/04/2021` is not: nothing
downstream looks wrong, and the error quietly distorts tenure, leave accrual and
gratuity for years. Same size of edit, opposite blast radius — so they sit on
opposite sides of the line.

Every threshold lives in one file, [`app/policy.py`](app/policy.py), so the boundary
can be reviewed and tuned without reading the pipeline. The reasoning behind each
number is in [docs/ESCALATION-POLICY.md](docs/ESCALATION-POLICY.md).

On the bundled sample data — 35 source columns across 2 files, 52 people — the agent
resolves everything on its own except **five** questions:

| Question | Why it is not the agent's call |
|---|---|
| Which column is `work_email`? | Two columns both score as the work address; only one can be |
| Is `joining_dt` day-first or month-first? | Every value has both parts ≤ 12, so nothing in the column settles it |
| What does `Engg` mean? | Resembles `Engineering` closely enough to suspect, too loosely to assume |
| Is Rakesh Reddy a rehire or a duplicate? | One PAN, two employee codes — merging would destroy service history |
| Are these the same person? | Same birthday and first name, related surnames, nothing unique tying them |

## Architecture at a glance

The core design decision: **the model decides rules, deterministic code applies them.**
Records never enter a prompt. Each agent sees a redacted *column profile* and returns
a decision about the column; Python then applies that decision to every row. So a run
costs the same handful of model calls whether the file has fifty rows or fifty
thousand, every transformation is replayable, and PII never reaches the model.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the agent topology and pipeline.

## Repo layout

```
app/
  policy.py          every threshold that decides act-vs-ask, in one file
  agents/            profiler, mapper, cleanser, identity, validator, loader
  dates.py           reads the column, not the value
  pii.py             masking; PII never reaches a model or the audit log
  graph.py           the LangGraph pipeline and its interrupt gate
schema/              the target HRMS schema
data/                generated sample exports, each defect deliberate
web/                 React supervision UI
docs/                plan, architecture, escalation policy, write-up
```

## Tech stack

Python 3.11 · FastAPI · LangGraph (`interrupt()`/resume for human-in-the-loop) ·
SQLite · pandas · rapidfuzz · local open-source models via Ollama or any
OpenAI-compatible server (llama.cpp, vLLM) · React + TypeScript + Vite.

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
6. **Shows the dry run before anything is sent** — the exact payload per record, and
   every edit inside it that you were never asked to approve.
7. **Exports a reusable migration recipe** — the whole decision set as reviewable
   YAML, replayable against the next client's files. Build once, deploy to many.

## Quickstart

Either one command with Docker:

```bash
docker compose up --build        # then open http://localhost:8000
```

Or locally, if you would rather see the pieces:

```bash
uv venv --python 3.11
VIRTUAL_ENV="$PWD/.venv" uv pip install -e ".[dev]"

cd web && npm install && npm run build && cd ..   # the API serves the built UI
.venv/bin/uvicorn app.main:app --port 8000        # then open http://localhost:8000
```

Press *Run the sample migration*. The agent reads both bundled exports, reconciles
54 rows into **42 people**, and stops with **eight questions** out of 35 source
columns — everything else it settles on its own.

It has also been run against real public HR exports — two versions of the Kaggle
*Human Resources Data Set* together (64 columns, 621 rows → 15 questions, 346
people loaded) and the IBM attrition extract (correctly refused as not employee
data). What those files taught it is in [docs/REAL-DATA.md](docs/REAL-DATA.md).
Drop your own exports into `data/real/` (git-ignored) or upload them in the UI.

To test it on shapes you choose, `python scripts/make_testkit.py` writes twelve
files that each provoke exactly one behaviour; [docs/TESTING.md](docs/TESTING.md)
says what each should do.

```bash
.venv/bin/python -m pytest        # 155 backend tests
cd web && npm test                # 22 frontend tests
```

### Tested against real data, not just the sample

The bundled exports are deliberately defective, but their defects are the ones we
thought of. Pointing the agent at real public HR datasets found three things that
were **silently** wrong — every name in the file inverted, race data auto-mapped
into `gender`, and one missing field turning into 300 identical questions — and
four that were already right. All three are fixed and pinned by tests;
[docs/REAL-DATA.md](docs/REAL-DATA.md) is the write-up.

**[docs/TESTING.md](docs/TESTING.md)** — what to give it, what comes back, and a
kit of twelve files that each provoke one behaviour.
**[docs/CAPABILITIES.md](docs/CAPABILITIES.md)** — what it can do and how a run
works, end to end. **[docs/REAL-DATA.md](docs/REAL-DATA.md)** — what broke when it
was pointed at real public HR datasets, and what was fixed.
**[docs/RUNNING.md](docs/RUNNING.md)** — setup, models, troubleshooting.
**[docs/TODO.md](docs/TODO.md)** — what is still outstanding.

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

On the bundled sample data — 35 source columns across 2 files, 54 rows — the agent
maps 30 columns silently, applies 1 more and flags it, drops 2 as having no home in
the schema, and stops with **eight** questions:

| Question | Records | Why it is not the agent's call |
|---|---|---|
| Which column is `work_email`? | — | Two columns both score as the work address; only one can be |
| Is `joining_dt` day-first or month-first? | 21 | Every value has both parts ≤ 12, so nothing in the column settles it |
| What does `Engg` mean? | 2 | Resembles `Engineering` closely enough to suspect, too loosely to assume |
| Is Rakesh Reddy a rehire or a duplicate? | 2 | One PAN, two employee codes — merging would destroy the service history gratuity is computed from |
| Are these the same person? (Sana Qureshi) | 2 | Same birthday and first name, related surnames, nothing unique tying them |
| Three records that will not load | 1 each | A malformed PAN, and two inactive employees with no exit date — still wrong after one deterministic repair attempt |

Answering them shows the cascade the design exists for. Confirming which column holds
the work email settles what the *other* email column can be, and lets the reporting
tree be checked at all: **54 rows reconcile into 41 people**, and three further
questions surface — which field `Mail ID` feeds, a reporting loop, and a manager
nobody in the files has. Those are deliberately deferred until the email columns are
known, because resolving managers against an incomplete set would report false
orphans. Eleven questions in all, then 39 records load and one is refused by the
target and escalated rather than retried.

Then it pushes: **38 loaded, two transient failures retried and succeeded, one
business rejection escalated** rather than retried forever.

Because a human answer is remembered against the stable *subject* of the question,
the **second** run of the same files asks fewer — the mapping questions are already
settled. That is the point of the memory table, and it is why the count you see
depends on whether the database is fresh.

## The supervision UI

Eight views, because a consultant needs to answer different questions at different
moments and none of them should require reading the code.

| View | What it answers |
|---|---|
| **Run** | What is it doing right now? A live log of its reasoning, line by line |
| **Review** | What needs me? The queue, each card carrying enough evidence to decide at a glance |
| **Mapping** | Did it actually understand my file? Every column, where it went, and on what score |
| **Dry run** | What exactly will be sent? Per-record payloads, and every edit I was never asked to approve |
| **Records** | What happened at the target? Per-record results, retry and rollback |
| **Decisions** | What did it settle alone? Grouped, with the reasoning, read-only on purpose |
| **Audit** | Who changed what, and why? Filterable by actor, exportable as CSV |
| **Boundary** | Where is the line drawn, and why there? |

Two of those are worth singling out.

**Dry run** is the counterweight to the whole argument. The queue is where the agent
asks; this is where you can audit everything it *didn't* ask about, per record, in
the shape the target will receive it. A claim that most decisions shouldn't need
individual approval only holds if the aggregate is inspectable before it is sent.

**Boundary** renders `app/policy.py` live, over `GET /api/policy`. The thresholds are
not restated in TypeScript, because a second copy could drift from the real ones and
then the screen explaining the agent's judgment would be the least trustworthy thing
on it. A test asserts the described values *are* the module constants.

The queue is built to be worked from the keyboard: `j`/`k` to move, `1`–`9` to pick
an option (which advances automatically), `u` to undo, `⌘↵` to apply. `⌘K` opens a
command palette; `?` lists the shortcuts. Answers are staged locally and submitted
as a batch, because every answer re-runs the whole pipeline — submitting one at a
time would mean a dozen full re-analyses for a queue meant to be cleared in one pass.

### Styling

The entire look lives in [`web/src/styles/tokens.css`](web/src/styles/tokens.css),
as three independently switchable axes:

- `[data-theme]` — light or dark, or follow the OS (watched live, so it changes at dusk without a reload)
- `[data-accent]` — indigo, cyan, violet or emerald
- `[data-density]` — comfortable or compact row heights and type scale

Tailwind's colour namespace is aliased to those variables rather than to literals
(`--color-surface: var(--s-surface)`), so utilities resolve through the token layer
at paint time. Flipping an attribute on `<html>` restyles the whole app instantly —
no second stylesheet, no rebuild, and opacity modifiers like `border-ask/30` still
work because Tailwind wraps them in `color-mix()`.

Colour is never decorative: **amber always means the agent inferred this**, **rose
always means this is blocked on you**, **green always means it settled this itself**.
A reviewer should be able to read disposition off the screen without reading a word.

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
  pipeline.py        the migration as a pure function of (files, decisions)
  plan.py            the dry run: what will be sent, and what was changed
  recipe.py          the decision set as replayable YAML
schema/              the target HRMS schema
data/                generated sample exports, each defect deliberate
web/
  src/styles/        design tokens — theme, accent and density in one file
  src/components/    the supervision UI, one panel per view
docs/                plan, architecture, escalation policy, write-up
```

## Tech stack

Python 3.11 · FastAPI · LangGraph (`interrupt()`/resume for human-in-the-loop) ·
SQLite · pandas · rapidfuzz · local open-source models via Ollama or any
OpenAI-compatible server (llama.cpp, vLLM) · React 19 + TypeScript + Vite ·
Tailwind v4 over a CSS-variable token layer · Zustand · Vitest · Docker.

No paid API is used anywhere. The models are open-source and run locally, and the
pipeline completes with none of them reachable.

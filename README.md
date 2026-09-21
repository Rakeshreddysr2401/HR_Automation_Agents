# HR Data Migration Agent

An AI agent that migrates a client's messy HR exports (CSV / Excel, inconsistent
columns, mixed date formats, duplicates, missing fields) into a target HRMS schema
and pushes the result to a mock target API — **stopping to ask a human only where
the data genuinely supports more than one answer.** A small web UI lets a
non-technical implementation consultant watch it work, resolve what it is unsure
about, and see a record of everything it did.

Built for the Darwinbox Forward Deployed Engineer take-home. The assessment is
about *how the agent's autonomy is scoped*, so the escalation boundary is the
product and everything else exists to make it demonstrable.

**Deliverables**

| | Where |
|---|---|
| Working prototype | Run instructions below — one command with Docker, or two without |
| Source code | This repo |
| Write-up (1 page) | [docs/WRITEUP.md](docs/WRITEUP.md) — approach, where the line between deciding and asking is drawn, what to build next |
| Demo script | [docs/DEMO.md](docs/DEMO.md) — the 3-minute walkthrough the recording follows |

---

## Contents

1. [Acceptance criteria, and where each is met](#1-acceptance-criteria-and-where-each-is-met)
2. [Run it](#2-run-it)
3. [Try it — test data and a 5-minute walkthrough](#3-try-it)
4. [How it decides what to ask](#4-how-it-decides-what-to-ask)
5. [The supervision UI](#5-the-supervision-ui)
6. [Where the results are](#6-where-the-results-are)
7. [Architecture](#7-architecture)
8. [Tested against real data](#8-tested-against-real-data)
9. [Tests](#9-tests)
10. [Tech stack](#10-tech-stack)
11. [Documentation index](#11-documentation-index)

---

## 1. Acceptance criteria, and where each is met

| # | Criterion | How it is met | See it |
|---|---|---|---|
| 1 | **Multi-file ingestion** — several files for the same entity, different columns, reconciled without field-by-field instruction | Reads CSV and Excel as text, profiles every column, maps each file independently, then joins rows across files on any shared unique identifier (employee code, work email). Near-matches on name + date of birth are asked about. | Run the sample: 2 files, 35 columns, 54 rows → 41 people |
| 2 | **Autonomous mapping and cleanup** | Three mapping signals (semantic embedding, lexical alias match, structural fit of the values) with columns *competing* for fields. Dates inferred per column from unambiguous rows. Casing, whitespace, vocabulary aliases (`M`→`Male`, `FTE`→`Permanent`) applied silently and reported. | **Mapping** tab, **Auto decisions** tab |
| 3 | **Defensible escalation boundary** | Three dispositions — *auto*, *flagged* (applied but surfaced), *escalated* (blocking). Every threshold in one file, [`app/policy.py`](app/policy.py), each with the reasoning beside it. Asks once per column or per distinct value, never once per row; floods collapse into one batch question. | **Rules** tab, [docs/ESCALATION-POLICY.md](docs/ESCALATION-POLICY.md) |
| 4 | **Human-in-the-loop UI** | Live log of the agent's reasoning; a review queue where each card carries the evidence to decide at a glance (samples, scores, both records side by side); approve / correct / reject, keyboard-driven; a preview of every record before sending. | **Run**, **Review**, **Preview** tabs |
| 5 | **Mock system integration** | Per-record push to a stub API with idempotency keys; transient errors (5xx, timeout) retried with backoff; business rejections (4xx) escalated, not retried; rollback with a mandatory reason; full audit trail of every change, who made it, before/after, why. | **Records** tab, **Audit log** tab |
| 6 | **Delta on top of what AI does** | Records never enter a prompt (the model decides *rules*, code applies them); PII masked before anything leaves the process; a replayable **recipe** so the next migration for the same client asks nothing; mapping memory across runs; batch-level circuit breakers; tested and hardened on real public HR exports. | [§7](#7-architecture), [§8](#8-tested-against-real-data) |

---

## 2. Run it

### One command (Docker)

```bash
docker compose up --build        # then open http://localhost:8000
```

### Locally

```bash
uv venv --python 3.11
VIRTUAL_ENV="$PWD/.venv" uv pip install -e ".[dev]"

cd web && npm install && npm run build && cd ..   # the API serves the built UI
.venv/bin/uvicorn app.main:app --port 8000        # open http://localhost:8000
```

### Models (optional, open-source, local)

The agent uses two local open-source models: an **embedding** model to score column
mappings and a **chat** model to write the recommendation shown on each card. Both
are optional — with nothing reachable it falls back to lexical scoring, asks somewhat
more, and still completes every run. No paid API is used anywhere.

```bash
ollama pull nomic-embed-text      # embeddings
ollama pull gemma4                # recommendations on cards
cp .env.example .env              # edit if your models run elsewhere
```

The header of the UI shows which models are reachable. Full setup and
troubleshooting: [docs/RUNNING.md](docs/RUNNING.md).

> **Fresh start.** The agent remembers column answers between runs, so a second run
> of the same files asks fewer questions. For a clean demo, stop the server and
> delete `migration.db` and `checkpoints.db`.

---

## 3. Try it

Three tiers of test data are included.

### a) The bundled sample — press *Run Sample Migration*, nothing to upload

`data/legacy_hris_export.csv` + `data/payroll_system.xlsx`: 35 columns, 54 rows,
every defect planted to exercise one policy branch. Expect **8 questions**, then 2,
then 1, then one rejection from the target: **41 people, 40 loaded**.

### b) The small demo pair — best for a live walkthrough

`data/demo/old_hr_system.csv` + `data/demo/payroll_export.xlsx`: 9 + 7 people,
**one story per row**. Upload both together.

| Person | Demonstrates |
|---|---|
| Aarav Sharma | `"  aarav  SHARMA "` fixed silently — open him in Preview to see before → after |
| Priya Nair ↔ Rohan Mehta | Report to each other: a reporting loop |
| Diya Patel | Department `Engg` — 77% like Engineering; asked, not guessed |
| Vikram Rao | Inactive with no exit date — fails validation twice, you supply it |
| Meera Joshi | Malformed PAN — you supply it |
| Sana Qureshi / Sana Q. | Same birthday and first name, different codes — duplicate or two people? |
| Rakesh Reddy ×2 | Same PAN, left 2019, back 2023 — rehire or duplicate? Merging would destroy his first stint |
| Arjun Iyer | Reports to someone who has left; then the HRMS refuses his code on push |
| Nikhil Agarwal | The HRMS times out once on push, succeeds on retry |

**The walkthrough (about 5 minutes):**

1. **Run** → drop both files → *Start Migration*. Watch the log narrate itself.
2. **Review** → 7 questions out of 29 columns and 16 rows. Open the rehire card
   (the strongest moment: nothing in the data can settle it, and it says why it
   matters). Answer with the keyboard: `1`–`9` picks, `⌘↵` applies. Exact answers
   are in [`data/demo/README.md`](data/demo/README.md).
3. The banner explains **round 2**: 3 questions it *couldn't* ask before — which
   field the losing email column feeds, the reporting loop, the missing manager.
4. **Preview (before send)** → click Aarav: the exact record the HRMS will receive
   on the left, every fix the agent made without asking on the right.
5. Apply → the push runs on its own: two transient failures retried, **one business
   rejection comes back as a card**. Leave it out.
6. **Records (after send)** → 10 loaded, 1 skipped. Tick a row → *Roll back* (a
   reason is required). **Download results (Excel)**.
7. **Audit log** → filter *You*: the two values you typed, PAN masked even so.
8. **Rules** → the thresholds, read live from `policy.py`.

### c) Real public HR exports

Drop your own files into `data/real/` (git-ignored) or upload them in the UI. The
agent has been run against the Kaggle *Human Resources Data Set* (two versions of
the same 300 real employees, uploaded together: 64 columns, 621 rows → 15 questions
→ 346 people loaded) and the IBM attrition extract (correctly refused as not
employee data with a single question). See [§8](#8-tested-against-real-data).

### d) One-behaviour files

`python scripts/make_testkit.py` writes twelve small files to `data/testkit/`, each
provoking exactly one behaviour — clean file, renamed columns, ambiguous dates,
unknown values, duplicates, broken records, hierarchy, wrong file, missing column,
surname-first names. [docs/TESTING.md](docs/TESTING.md) says what each should do.

---

## 4. How it decides what to ask

> **Escalate when being wrong is silent and irreversible.**
> **Auto-fix when being wrong would be loud and cheap to undo.**

Trimming a trailing space is safe: a wrong correction is visible immediately and
costs seconds to reverse. Reading `03/04/2021` as 3 April rather than 4 March is
not: nothing complains, and the error quietly distorts tenure and gratuity for
years. Same size of edit, opposite blast radius — so they sit on opposite sides of
the line.

**Three dispositions, not two.** *Auto* (applied silently, reported), *flagged*
(applied, but surfaced for a look — e.g. a full-name column split into first/last),
*escalated* (blocking until a human answers). The middle tier is what keeps the
queue short while the agent stays honest.

**Every threshold lives in [`app/policy.py`](app/policy.py)** with the reasoning
beside it, and the **Rules** tab renders that file live so the numbers on screen
can never drift from the ones in force.

**On the sample data** the agent maps 30 of 35 columns silently, applies one more
and flags it, drops two as having no home in the schema, and stops with eight
questions:

| Question | Records | Why it is not the agent's call |
|---|---|---|
| Which column is `work_email`? | — | Two columns both score as the work address; only one can be |
| Is `joining_dt` day-first or month-first? | 21 | Every value has both parts ≤ 12; nothing in the column settles it |
| What does `Engg` mean? | 2 | 77% like `Engineering` — close enough to suspect, too far to assume |
| Is Rakesh Reddy a rehire or a duplicate? | 2 | One PAN, two employee codes — merging destroys the service history gratuity is computed from |
| Are these the same person? (Sana Qureshi) | 2 | Same birthday and first name, related surnames, nothing unique tying them |
| Three records that will not load | 1 each | Still wrong after one deterministic repair attempt |

Answering them lets the agent run checks it deliberately held back — the reporting
tree cannot be verified until the email columns are known — so three more questions
surface in round two. Eleven in all; everything else it settled itself.

**Floods become one question.** Forty identical cards is the same failure as
guessing. So: a required field empty on every record is one question about the
field; two files that near-match each other wholesale are one question about the
files; most of a batch refused by the target for one reason is one question about
the batch; a file that does not look like employee data at all is one question
before anything else. Details in [docs/ESCALATION-POLICY.md](docs/ESCALATION-POLICY.md).

---

## 5. The supervision UI

Eight tabs, in the order a run moves through them.

| Tab | Answers | Notes |
|---|---|---|
| **Run** | What is it doing right now? | Upload; a live log, one line per decision or question; paste a recipe to replay |
| **Review** | What needs me? | One card per genuine ambiguity, each standing for every record it covers. Evidence, options, keyboard triage (`j`/`k`, `1`–`9`, `u`, `⌘↵`). Answers are batched and re-run through the whole pipeline |
| **Mapping** | Did it understand my file? | Every source column → target field with its disposition and the three scores behind it |
| **Preview (before send)** | What exactly will be sent? | Per employee: the final record as the HRMS will receive it, and every fix made automatically (before → after, and why). Nothing has been sent yet. Export the recipe here |
| **Records (after send)** | What happened at the target? | Per employee: loaded / failed (retry) / rejected (back to Review) / skipped / rolled back. Roll back with a reason; push again. **Download results** |
| **Auto decisions** | What did it settle alone? | Rules and fixes grouped by kind, each with its evidence; what it will remember for next time |
| **Audit log** | Who changed what, and why? | Every change: actor, record, before → after, reason. PII masked. Filter by *agent* / *you*; export CSV |
| **Rules** | Where is the line, and why there? | `app/policy.py` rendered live: the three tiers and every threshold with its reasoning |

Colour is never decorative: **green** = the agent settled it, **amber** = it inferred
this and flagged it, **rose** = blocked on you. Light/dark theme, accent and density
are switchable from the header.

---

## 6. Where the results are

| What | Where |
|---|---|
| The migrated dataset (Excel or CSV) — every employee in the target schema, plus `migration_result`, the HRMS id, and which source rows it came from | **Records (after send)** → *Download results* |
| What the mock HRMS actually holds | **Records** → *View in mock HRMS* (`GET /mock-target/v1/employees`) |
| The full change history (CSV) | **Audit log** → *CSV* |
| The rules and answers, for replaying on the next migration (YAML, no employee data) | **Preview** → *Recipe* → *Export* |

---

## 7. Architecture

**The model decides rules; deterministic code applies them.** No record ever enters
a prompt. Each agent sees a redacted *column profile* — name, inferred type, null
rate, a few masked sample values — and returns a decision about the column; Python
applies it to every row. So a run costs the same ~20 model calls whether the file
has 50 rows or 50,000, every transformation is replayable, each decision carries a
numeric basis, and PAN, Aadhaar and bank details never reach a model.

Model output is a **recommendation, never an action**: on an ambiguous card the chat
model writes a suggestion for the human to accept, and nothing auto-applies from it.

Agents are split by the *kind of judgment* they make, each with its own confidence
policy and its own way of explaining itself:

| Agent | Question it answers | When it refuses to answer |
|---|---|---|
| **Profiler** | What is in this column? | Never — it observes |
| **Mapper** | Which target field is this column? | Two candidates too close; two columns claim one field |
| **Cleanser** | Can I safely rewrite this value? | A date column with no anchor; a value outside the vocabulary |
| **Identity** | Are these rows the same human? | A near-match; a shared PAN that could be a rehire |
| **Validator** | Is this record loadable? | Still failing after one repair; a broken reporting line |
| **Loader** | Did the target accept it? | A business rejection (4xx) |
| **Supervisor** | Is this run worth continuing? | Trips a breaker when the premise looks wrong |

The pipeline is a LangGraph graph with one `interrupt()` gate: analyse → *ask the
human everything at once* → analyse again with the answers folded in → push. Each
answer re-runs the whole analysis rather than patching the output, which is what
lets one answer cascade (confirming the work-email column is what allows the
reporting tree to be checked).

More: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) ·
[docs/CAPABILITIES.md](docs/CAPABILITIES.md).

```
app/
  policy.py          every threshold that decides act-vs-ask, in one file — read this first
  agents/            profiler, mapper, cleanser, identity, validator, loader
  supervisor.py      batch-level judgment: breakers, flood collapse, what blocks what
  pipeline.py        the migration as a pure function of (files, decisions)
  graph.py           the LangGraph pipeline and its human gate
  plan.py            the preview: what will be sent, and what was changed
  recipe.py          the decision set as replayable YAML
  dates.py           column-level date convention inference
  pii.py             detection and masking
  mock_target.py     the stub HRMS API
schema/              the target HRMS schema (field descriptions drive the mapping)
data/                sample exports, the demo pair, the one-behaviour test kit
web/src/components/  the supervision UI, one panel per tab
docs/                architecture, policy, write-up, demo script, real-data findings
tests/               184 backend tests; web/src for the 23 frontend tests
```

---

## 8. Tested against real data

The bundled exports are deliberately defective, but their defects are the ones we
thought of. Pointing the agent at real public HR datasets found things that were
**silently wrong** — every name in a file inverted, race data auto-mapped into
`gender`, one missing field turning into 300 identical questions — and then, with
two versions of the same file uploaded together, **290 questions and a false
"wrong file" stop**: analytics columns scoring high against statutory-ID fields
their values could never satisfy, and 275 separate "same person?" cards for two
exports of the same staff.

All of it is fixed, each fix pinned by a test, and each threshold explained in
`policy.py`. The same two files now produce 15 questions and load 346 people.
The full account is [docs/REAL-DATA.md](docs/REAL-DATA.md).

---

## 9. Tests

```bash
.venv/bin/python -m pytest        # 184 backend tests, ~35s (embeddings live if reachable)
cd web && npm test                # 23 frontend tests
```

A golden test pins the exact set of questions the sample data must produce, so a
drifting threshold fails loudly and names what changed. `scripts/sweep_thresholds.py`
shows how the question count moves as each threshold does.

---

## 10. Tech stack

Python 3.11 · FastAPI · LangGraph (`interrupt()`/resume for the human gate) ·
SQLite · pandas · rapidfuzz · open-source models served locally via Ollama or any
OpenAI-compatible server (llama.cpp, vLLM) — `nomic-embed-text` for embeddings,
`gemma` for card recommendations · React 19 + TypeScript + Vite · Tailwind v4 over
a CSS-variable token layer · Zustand · Vitest · Docker.

Built with AI coding tools (Claude), as the brief permits. No paid model API is
used at runtime; the pipeline completes with no model reachable at all.

---

## 11. Documentation index

| Document | What it covers |
|---|---|
| [docs/WRITEUP.md](docs/WRITEUP.md) | The one-page write-up: approach, the boundary, what next |
| [docs/DEMO.md](docs/DEMO.md) | The demo script |
| [docs/ESCALATION-POLICY.md](docs/ESCALATION-POLICY.md) | Every threshold and why it sits where it does |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Agents, pipeline, the design decision everything follows from |
| [docs/CAPABILITIES.md](docs/CAPABILITIES.md) | What it can do, measured on the sample data |
| [docs/REAL-DATA.md](docs/REAL-DATA.md) | What real public HR exports broke, and what was fixed |
| [docs/RUNNING.md](docs/RUNNING.md) | Setup, models, troubleshooting |
| [docs/TESTING.md](docs/TESTING.md) | The one-behaviour test kit and what each file should do |
| [data/demo/README.md](data/demo/README.md) | The small demo pair, row by row, with the answers |
| [docs/TODO.md](docs/TODO.md) | Known rough edges and what is deliberately not built |

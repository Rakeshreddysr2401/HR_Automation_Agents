# CLAUDE.md — working notes for this repo

Read `docs/ARCHITECTURE.md` and `docs/ESCALATION-POLICY.md` before changing agent
behaviour. `docs/CAPABILITIES.md` describes what the system does and how a run works;
`docs/PLAN.md` and `docs/TODO.md` track what is built and what is next.

## What this is

An agent that migrates messy client HR exports into a target HRMS schema, escalating
to a human only on genuine ambiguity. Built for the Darwinbox FDE take-home. The
assessment is about **how agent autonomy is scoped**, not code volume — so the
escalation boundary is the product, and the code exists to make it demonstrable.

## Non-negotiables

- **Records never enter a prompt.** Agents see redacted `ColumnProfile`s and decide
  *rules*; deterministic Python applies them to rows. This is what makes the system
  scale flatly, stay replayable, and keep PII away from models. Do not "simplify" it
  by feeding rows to a model.
- **Every threshold lives in `app/policy.py`.** No magic numbers elsewhere. If a new
  decision needs a cutoff, it goes there with a comment explaining the reasoning.
- **Model output is a recommendation, never an action.** `llm.ask_json` results are
  rendered on escalation cards for a human to accept. Nothing auto-applies from them.
- **The pipeline must complete with no model server.** `app/llm.py` returns `None`
  everywhere on failure and callers fall back to lexical scoring. Failing toward
  asking is correct; failing toward crashing is not.
- **Ask once per column or per distinct value, never once per row.** Forty identical
  questions is the same failure as guessing.
- **Three dispositions, not two.** `AUTO`, `FLAGGED` (applied but surfaced),
  `ESCALATED` (blocking). `FLAGGED` is what keeps the queue short and the agent honest.

## Layout

```
app/policy.py          the escalation boundary; the file a reviewer should read first
app/agents/            profiler, mapper, cleanser, identity, validator, loader
app/dates.py           column-level date convention inference
app/pii.py             detection and masking
app/graph.py           LangGraph pipeline + interrupt gate
schema/                target schema; field `description` text is embedded for mapping
scripts/               sample data generator, threshold sweep
web/                   React supervision UI
```

## Commands

```bash
uv pip install -e ".[dev]"
python scripts/make_sample_data.py     # regenerate sample exports
uvicorn app.main:app --reload
pytest
```

## Gotchas

- `uv` follows `VIRTUAL_ENV` from the shell. Pass `VIRTUAL_ENV="$PWD/.venv"`
  explicitly when installing, or packages land in whatever venv is active.
- Schema field `description` text is not documentation — it is the string embedded
  when scoring source columns. Only the `Also called ...` clause is parsed for
  aliases; `such as ...` lists example *values* and is deliberately ignored.
- Sample-data defects are load-bearing. Each one exercises a specific policy branch
  and the golden test asserts the exact resulting escalation set. Changing the data
  means changing that test on purpose, not fixing it afterwards.

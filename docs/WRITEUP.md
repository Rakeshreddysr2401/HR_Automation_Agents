# Approach

**Repo:** https://github.com/Rakeshreddysr2401/HR_Automation_Agents · **Run it:** [docs/RUNNING.md](RUNNING.md)

An agent that migrates employee exports into a target HRMS schema — profiling columns,
working out the mapping, cleaning, validating, reconciling records across files, and
pushing to a mock target with retry, rollback and an audit trail. It stops to ask only
where the data genuinely supports more than one answer. On the two bundled exports (35
columns, 52 people) it settles everything itself except **ten questions**, then loads 41
records.

## The decision that shapes everything else

**The model decides rules; deterministic code applies them.** No record enters a prompt.
Each agent sees a *column profile* — name, type, null rate, five redacted samples — and
returns a decision about the column; Python applies it to every row.

So a run costs ~20 model calls whether the file has 50 rows or 50,000; every
transformation is replayable; each decision has a numeric basis, so "why did it do that?"
has a real answer; and PAN, Aadhaar and bank details never reach a model.

Where a mapping is ambiguous the model writes the recommendation shown on the card, but
is never permitted to apply one. A suggestion a human accepts is auditable; one a model
applies silently is not.

## Where I drew the line

> **Escalate when being wrong is silent and irreversible. Auto-fix when being wrong would
> be loud and cheap to undo.**

Not difficulty, and not the agent's confidence — both are the intuitive criteria and both
are wrong. Trimming `"  Engineering "` is safe: a wrong correction is visible immediately
and costs seconds. Reading `03/04/2021` as 3 April rather than 4 March is not: the result
looks valid, nothing complains, and it quietly misstates that person's tenure and gratuity
for years. Same edit size, opposite blast radius.

**Three tiers, not two.** Auto-and-ask alone forces a choice between an agent that hides
its reasoning and one that interrupts constantly. The middle tier does the work:

- **Applied** — deterministic, or the evidence leaves one answer standing.
- **Applied and flagged** — *"this column reads as day/month, 18 rows prove it, applied to
  all 33."* Deserves a glance, not a decision.
- **Blocked** — the evidence genuinely supports more than one answer.

Three cases show where the judgment lives:

**The rehire.** One PAN, two employee codes, non-overlapping service — exactly what a
duplicate looks like *and* what a rehire looks like. Generic dedup merges them and
destroys the service history gratuity is computed from. Neither the agent nor a consultant
can tell from the data alone, so it asks, and says what is at stake.

**Confident absence is not ambiguity.** `ctc_annual` has no home in an employee master.
The agent isn't uncertain — it's certain there's no match. Unmapped columns are reported,
never queued.

**Ask once.** An ambiguous date column is one question covering 21 rows, not 21 questions.
A supervisor links each question to the records it already covers so the validator never
re-asks in a different shape what the queue already holds — that bug existed, and the
supervisor exists to kill it.

Above all of it, a circuit breaker: if over a quarter of records need a human, or the file
barely maps to the schema, it raises **one** batch-level question. An agent that floods the
queue has failed as surely as one that guesses — it has moved the work, not done it.

## Two things I'd say honestly

**The thresholds aren't what's keeping this correct.** `scripts/sweep_thresholds.py`
re-runs the migration across a grid of confidence and margin values. On this sample *no*
setting produces a wrong mapping, including the most permissive. What's doing the work is
the assignment step — columns compete for each target field, so ambiguity resolves
structurally rather than numerically. I kept the thresholds tight anyway: a 35-column
sample can't show a loose setting is safe on inputs it doesn't contain, only fail to find
a counter-example. The defaults cost two extra questions here. That's the premium.

**I deliberately didn't use a multi-agent chat framework.** The six agents share typed
state; the sequence is fixed and the edges deterministic. Routing between them through an
LLM would add latency, cost and non-determinism for nothing, and passing 52 records
through chat messages would be worse. It was the obvious reach and the wrong one.

## What I'd build next

**Effective-dated history** — HR records are temporal; promotions are changes over time,
not overwrites. **Multi-entity ordering** — org units before employees before payroll.
**Active learning on thresholds** — every resolved escalation is a labelled example, so
they could be fitted to a client's history rather than set by hand. **Connector-based
ingestion** from SAP, PeopleSoft and Zoho, with the same boundary on top; file drops are
the demo, not the product.

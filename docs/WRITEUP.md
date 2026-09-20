# Approach

**Repo:** https://github.com/Rakeshreddysr2401/HR_Automation_Agents · **Run it:** [docs/RUNNING.md](RUNNING.md)

An agent that migrates employee exports into a target HRMS schema — profiling columns,
working out the mapping, cleaning, validating, reconciling records across files, and
pushing to a mock target with retry, rollback and an audit trail. It stops to ask only
where the data genuinely supports more than one answer. On the two bundled exports (35
columns) it maps 30 columns silently and stops with **eight questions**; three more
surface as answers unlock checks it could not yet run. Answering them reconciles 54
rows into 41 people and loads 39, with one refused by the target and escalated rather
than retried.

## The decision that shapes everything else

**The model decides rules; deterministic code applies them.** No record enters a prompt.
Each agent sees a *column profile* — name, type, null rate, five redacted samples — and
returns a decision about the column; Python applies it to every row.

So a run costs ~20 model calls whether the file has 50 rows or 50,000; every
transformation is replayable; each decision has a numeric basis; and PAN, Aadhaar and
bank details never reach a model.

Where a mapping is ambiguous the model writes the recommendation on the card but is never
permitted to apply one. A suggestion a human accepts is auditable; one a model applies
silently is not.

## Where I drew the line

> **Escalate when being wrong is silent and irreversible. Auto-fix when being wrong would
> be loud and cheap to undo.**

Not difficulty, and not the agent's confidence — both are intuitive and both are wrong.
Trimming `"  Engineering "` is safe: a wrong correction is visible immediately and costs
seconds. Reading `03/04/2021` as 3 April rather than 4 March is not — the result looks
valid, nothing complains, and it quietly misstates that person's tenure and gratuity for
years. Same edit size, opposite blast radius.

**Three tiers, not two.** Auto-and-ask alone forces a choice between an agent that hides
its reasoning and one that interrupts constantly. The middle tier does the work:
**applied** (deterministic, or one answer stands); **applied and flagged** — *"reads as
day/month, 18 rows prove it, applied to all 33"* — a glance, not a decision; and
**blocked**. Three cases show where the judgment lives:

**The rehire.** One PAN, two employee codes, non-overlapping service — exactly what a
duplicate looks like *and* what a rehire looks like. Generic dedup merges them and
destroys the service history gratuity is computed from. Nothing in the data settles it, so
it asks, and says what is at stake.

**Confident absence is not ambiguity.** `ctc_annual` has no home in an employee master —
the agent isn't uncertain, it's certain there's no match. Unmapped columns are reported,
never queued.

**Ask once.** An ambiguous date column is one question covering 21 rows, not 21.

Above all of it, a circuit breaker: if over a quarter of records need a human, or the file
barely maps to the schema, it raises **one** batch-level question. An agent that floods the
queue has failed as surely as one that guesses — it moved the work rather than doing it.

## The delta on top of what the model does

The model does one thing: score a column against a schema description, and word the
question. Everything that makes it usable sits on top.

**The assignment step** — columns compete for each target field, so ambiguity resolves
structurally. That, not the thresholds, is what keeps the mapping correct.
**The supervisor**, linking each question to the records it already covers so the same
thing is never asked twice in two shapes; that bug existed. **Mapping memory**, keyed by
a question's stable *subject*, so an answer compounds across clients instead of
evaporating. **The dry run**, which makes the aggregate inspectable before the push —
without it, "most decisions shouldn't need individual approval" is an assertion rather
than a checkable claim. And **the recipe**: the decision set as YAML, rules only and no
records, so it can be committed and replayed. Seeding a fresh run with a previous recipe
takes it from eleven questions to one — the difference between a service engagement and a
product.

## Three things I'd say honestly

**The thresholds aren't what's keeping this correct.** `scripts/sweep_thresholds.py`
re-runs the migration over a 63-cell grid of confidence and margin values. On this
sample *no* setting produces a wrong mapping, including the most permissive — the
assignment step is doing the work. I kept them tight anyway: a 35-column sample can't
show a loose setting is safe on inputs it doesn't contain, only fail to find a
counter-example. The defaults cost two extra questions. That's the premium.

**Pointed at real data, it was wrong in three ways — all silent.** The bundled exports'
defects are the ones I thought of. Against real public HR datasets it inverted every name
in the file (`"Adinolfi, Wilson K"` → first name `"Adinolfi,"`), auto-mapped a race column
into `gender` at 0.85 and then asked seven questions blaming the *values*, and turned one
missing required field into 300 identical per-record questions. Nothing crashed and no
validation failed — the exact failure mode the policy is written to prevent, found in my
own code. All three are fixed, with thresholds in `policy.py` and tests pinning the shape
([docs/REAL-DATA.md](REAL-DATA.md)).

**I deliberately didn't use a multi-agent chat framework.** The six agents share typed
state; the sequence is fixed and the edges deterministic. Routing between them through an
LLM would add latency, cost and non-determinism for nothing — the obvious reach and the
wrong one.

## What I'd build next

**Effective-dated history** — HR records are temporal; promotions are changes over time,
not overwrites. **Multi-entity ordering** — org units before employees before payroll.
**A per-client value vocabulary**, learned on the first migration and carried in the
recipe: the real datasets showed the schema's enums fit one client, not all of them.
**Connector-based ingestion** from SAP, PeopleSoft and Zoho with the same boundary on
top; file drops are the demo, not the product.

# The escalation boundary

This is the part of the system that matters. Everything else is plumbing around a
single question: *what may the agent settle by itself?*

All of it is implemented in one file, [`app/policy.py`](../app/policy.py), so the
boundary can be reviewed and argued with directly.

## The governing principle

> **Escalate when being wrong is silent and irreversible.**
> **Auto-fix when being wrong would be loud and cheap to undo.**

Note what this is *not* based on: difficulty, or the agent's own sense of confidence.
Those are the intuitive criteria and they are both wrong.

Consider two edits of identical size. Trimming `"  Engineering "` to `"Engineering"`
is safe — if it were somehow wrong, a human sees it on the first screen they look at
and fixes it in seconds. Reading `03/04/2021` as 3 April rather than 4 March is not —
the result is a perfectly valid-looking date, nothing downstream complains, and the
error quietly misstates that person's tenure, leave accrual and gratuity for years.

Same-sized edit. Opposite blast radius. So they belong on opposite sides of the line,
and "how sure am I?" never entered into it.

## Three tiers, not two

Most systems offer only *auto* and *ask*, which forces a choice between an agent that
hides its reasoning and one that interrupts constantly. The middle tier is what lets
the queue stay short while the agent stays transparent.

| Tier | Meaning | Example |
|---|---|---|
| **AUTO** | Applied silently. Deterministic, or the evidence leaves one answer standing. | trimming whitespace; `M` → `Male`; merging rows with the same work email |
| **FLAGGED** | Applied, not blocking, but surfaced prominently. | "this column reads as day/month — 18 rows prove it — applied to all 33" |
| **ESCALATED** | Blocked. The evidence genuinely supports more than one answer. | the five questions below |

FLAGGED is the tier that does the real work. An inference drawn from strong evidence
should not cost a consultant a decision, but it should cost them a glance.

## What gets escalated, and why

### A column that could be two fields

Mapping combines three signals that fail differently: semantic similarity of the
column against the field's description, lexical similarity of the names, and
structural agreement between the column's contents and the field's type.

A mapping is applied only when it is both **confident** (≥ 0.82) and **unrivalled**
(≥ 0.12 clear of the runner-up). The margin test is the important half. A column
scoring 0.91 for `work_email` and 0.89 for `personal_email` is not a confident
mapping — it is a coin flip wearing a high score, and confidence alone would
auto-apply it and quietly corrupt the field the whole HRMS keys off.

Columns are resolved as a per-file **assignment** rather than independently: a target
field can only be filled from one column, so columns compete for fields and losers
re-evaluate against what is left. This distinguishes *genuinely ambiguous* from
*merely contested*, and it catches the inverse case too — when two columns both look
like the work email, each is individually confident and only the comparison between
them reveals the doubt.

### A column that matches nothing

Scoring below the floor with no lexical foothold anywhere in the schema means the
agent is not uncertain — it is confident there is **no** match. `ctc_annual` has no
home in an employee master. Asking a human to confirm that is noise, so unmapped
columns are reported, never queued. **Confident absence is not ambiguity.**

### A date column with no anchor

A single value tells you nothing, but a column is written by one system in one
convention, so one value with a day above 12 settles the whole column. The agent
requires at least 3 such anchors agreeing at 90% before it applies a convention —
and then flags what it inferred and how many rows it affected.

When every value in the column has both components at 12 or below, nothing settles
it. There is no clever way out, so it asks — **once for the column, not once per row**.

### An enum value in the grey band

`"engineering  "` → `Engineering` is normalisation. `"Human Resource"` →
`"Human Resources"` is a near-certain typo at 96% similarity. `"Engg"` scores in the
70s: close enough to suspect, too loose to assume. Above 90 the agent acts; between
70 and 90 it asks; below 70 it asks differently ("this value means nothing to me").

Standard abbreviations — `M`/`F`, `FTE`, `Contractor` — are handled by a
deterministic alias table. That is domain knowledge, not inference, and it does not
deserve a model call or a human's attention.

### A rehire that looks like a duplicate

The asymmetry is severe. A surviving duplicate is visible and someone deletes it. A
wrong merge is invisible: two people become one, and the record that vanished took
its salary, leave balance and reporting line with it.

So the agent merges only on identifiers that are unique by construction — work email,
PAN — and asks about everything softer.

The case worth dwelling on: one PAN under two employee codes is *exactly* what a
rehire looks like and *exactly* what a duplicate looks like. Generic dedup merges
them and destroys the earlier spell of service that gratuity is computed from. The
agent cannot tell these apart from the data, and neither can a consultant without
asking HR — so it surfaces the pair and explains what is at stake.

### A record that fails validation twice

One deterministic repair attempt, then ask. The second failure is the signal: the
first tells you the value was messy, the second tells you the mess is not mechanical.
Retrying further only burns time on data that needs a decision.

### A target system that says no

5xx and timeouts are the network's problem and are retried with backoff. A 4xx is the
target stating a business fact — "this employee code already exists" — which retrying
cannot fix and only a human can adjudicate.

One rejection is a question about one record. When at least five records and half
the batch come back with the *same* message, that is one question about the batch —
almost always "the target already holds these people" after a re-run or a partial
earlier load — and the agent asks it once: leave them all out, or review each one.
Forty identical cards would be the flood this whole policy exists to prevent.

### Two files that are the same people

Merging on anything softer than a unique identifier is a judgment call, and it
stays one per pair. But when most of one file near-matches the other on the same
basis — full name and date of birth, different ID systems — that is one fact
about the two files, and it is asked once: merge each pair, keep all, or review
each. The per-pair questions remain available; they are simply not the default
when there are two hundred of them.

### Too much escalating at once

Per-record judgment cannot catch a wrong premise. If more than a quarter of records
need a decision, or more than forty questions accumulate, the likely truth is not
"this data is hard" but "this is the wrong export". The agent raises **one**
batch-level question instead.

The wrong-file check needs two signals, not one: few columns mapping *and* the
schema's required fields missing. A real HRIS export can be two-thirds analytics
columns and still carry every name, date and code the target needs.

An agent that floods the queue has failed just as surely as one that guesses. It has
simply moved the work rather than doing it.

## Where the numbers came from

`scripts/sweep_thresholds.py` re-runs the sample migration across a range of values
and reports what each choice costs — how many columns map automatically, how many
escalate, and how many map *wrongly*. The defaults sit where wrong mappings reach
zero and escalations stop falling.

The thresholds are not sacred; they are a starting position that a real deployment
would tune per client. What matters is that they are explicit, measured, and in one
file rather than scattered through the code as magic numbers.

## Deliberately not escalated

Worth stating plainly, because a boundary is defined as much by what sits inside it:

- whitespace, casing and punctuation normalisation
- exact duplicates sharing a unique identifier
- date conventions with sufficient anchors in the same column
- enum values matching a known alias or scoring above 90
- columns that clearly belong to no target field
- schema defaults for absent optional values

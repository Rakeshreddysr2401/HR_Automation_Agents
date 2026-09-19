# What it does, and how it works

Every number below was measured on the two bundled sample exports, not estimated.

---

## In one paragraph

Point it at a folder of messy HR exports. It reads them, works out which source
column means which target field, cleans and validates the values, decides which rows
describe the same human, pushes the result to the target system, and keeps a record
of every change and why it was made. Where the data genuinely supports more than one
answer it stops and asks — and where it doesn't, it just gets on with it.

On the sample data that is **35 columns and 54 rows across two files, reconciled into
41 people, with 10 questions asked and 40 records loaded.**

---

## What it can do

### 1. Ingest several files describing the same thing

CSV and Excel, with no shared schema between them. The bundled pair is a legacy HRIS
dump (16 columns, full names in one field, `DD/MM/YYYY` dates) and a payroll
spreadsheet (19 columns, split names, ISO dates, statutory IDs). Nothing tells it how
they correspond.

Everything is read as text. A migration must not let a spreadsheet library silently
turn employee code `00123` into the number `123`, or guess at a date format — those
are decisions, and decisions belong to agents that can explain and escalate them.

### 2. Work out the mapping itself

Three independent signals, because each fails differently:

| Signal | What it catches | Where it fails |
|---|---|---|
| **Semantic** — embedding the column against the target field's description | `worker_category` → `employment_type`, where the strings share nothing | abbreviations; everything in one schema scores similarly |
| **Lexical** — fuzzy match of names and declared aliases | `DOB`, `PAN No`, `joining_dt` | coincidental substrings — `Office` looks like `office email` |
| **Structural** — does the column's content fit the field's type | a column of dates is not an email address | says little when both are free text |

Then the crucial step: **columns compete.** A target field can be filled from only one
column per file, so the strongest claim is settled first and losing columns
re-evaluate against what's left. This is what separates *genuinely ambiguous* from
*merely contested* — when one file carries both `Official Email` and `Mail ID`, each
looks like the work address alone, and only the comparison reveals the doubt.

**Result: 33 of 35 columns mapped with no human involvement.**

### 3. Clean what it can defend cleaning

- **Whitespace and casing** — always, reported per column, never queued.
- **Dates** — reads the *column*, not the value. `03/04/2021` is unreadable alone, but
  one row with a day above 12 settles the whole column. It requires at least three
  agreeing anchors, then says what it inferred and how many rows it touched.
- **Known vocabularies** — `engineering  ` → `Engineering` is normalisation;
  `Human Resource` → `Human Resources` is a near-certain typo at 96%. `M`/`F`, `FTE`,
  `Contractor` come from a deterministic alias table: domain knowledge, not inference,
  and not worth a model call or a human's attention.
- **Names** — splits `Aarav Sharma` into two fields, and title-cases only tokens that
  need it, so `McDonald` and `O'Brien` survive.

### 4. Decide who is the same person

Merges only on identifiers that are unique by construction — work email, PAN. The
asymmetry is severe: a surviving duplicate is visible and someone deletes it, while a
wrong merge is invisible, and the record that vanished took its salary, leave balance
and reporting line with it.

So near-matches get asked about, and **the rehire case always does**: one PAN, two
employee codes, non-overlapping service is exactly what a duplicate looks like *and*
exactly what a rehire looks like. Merging destroys the service history gratuity is
computed from.

### 5. Validate, repair once, then ask

Required fields, formats (PAN `[A-Z]{5}[0-9]{4}[A-Z]`, UAN, IFSC, email), enums, and
business rules — joining after birth, plausible age, exit after joining, inactive
needing an exit date.

On failure it makes **one** deterministic repair pass and revalidates. The second
failure is the signal: the first says the value was messy, the second says the mess
isn't mechanical.

It also checks what column-level validation can't see: **every `manager_email` must
resolve to somebody in the dataset**, and the reporting chain must not loop. Both
failures are invisible per-record — each address is perfectly valid — and both break
the org tree on arrival.

### 6. Push, retry what deserves it, roll back

Per-record, with an idempotency key derived from the run and employee code so a retry
after an ambiguous timeout can't create the same person twice.

- **5xx and timeouts** → retried with backoff, unattended.
- **4xx** → escalated with the target's own words. "This employee code already exists"
  doesn't become false on the third attempt.
- **Rollback** → compensating deletes, and it refuses to run without a reason, because
  the reason goes in the audit trail.

Measured: **40 loaded, 2 recovered on retry, 1 escalated.**

### 7. Keep a record

Every change carries actor, before, after, and a reason in plain English. A full run
produces around **120 entries**. PII is masked throughout — including values a
consultant types while resolving a card, which was a real leak found and fixed.

### 8. Learn from the answers

A resolved mapping becomes a reusable rule keyed by column name, so the same column is
never asked about twice — in this migration or the next client's. Run the same files
again and the queue is shorter. That's the difference between review as a recurring
cost and review as something that compounds.

Only *column identification* is remembered. Whether two particular employees are the
same person is a fact about those two people, and remembering it would be wrong.

### 9. Know when to stop

If more than a quarter of records need a human, or barely anything maps to the schema,
it raises **one** batch-level question instead of flooding the queue. Given an asset
inventory instead of employee data, it says so once rather than asking seven times.

An agent that floods the queue has failed as surely as one that guesses — it has moved
the work rather than done it.

---

## How a run actually works

```
ingest → profile → map columns → clean → resolve identity → validate → hierarchy
       → gate ──(questions?)──► stop and ask ──► answers ──► start again from the top
            │
            └──(none)──► push → done
```

**1. Profile.** Each column is described: name, inferred type, null rate, distinct
count, five sample values. This — never the rows — is what reaches a model.

**2. Decide.** Each agent looks at profiles and returns a decision about a *column*.
Deterministic Python then applies that decision to every row.

> **This is the design.** A run costs ~20 model calls whether the file holds 50 rows or
> 50,000. Every transformation is replayable. Each decision carries a numeric basis, so
> "why did it do that?" has a real answer. And PAN and bank details never reach a model,
> because only redacted profiles do.

**3. Sort into three tiers.** *Applied* (deterministic, or the evidence leaves one
answer standing) · *applied and flagged* (a defensible inference, surfaced but not
blocking) · *blocked* (the evidence genuinely supports more than one answer).

Two tiers would force a choice between an agent that hides its reasoning and one that
interrupts constantly. The middle tier is what keeps the queue short and the agent
honest.

**4. Ask once, for everything.** The graph suspends with the whole queue. Not one
interruption per finding — a consultant should see everything that needs them, triage
in whatever order suits, and hand it all back.

**5. Re-run with the answers.** Answers are **inputs to the pipeline, not patches on
its output**, so the whole thing runs again with them folded in.

> This matters more than it sounds. Confirming which column holds the work email let
> the identity resolver match the two files against each other: **52 records became 41**,
> and two validation failures fixed themselves because the merge supplied the fields
> they were missing. A patch would have left every one of those downstream effects stale.

**6. Push and record.**

Because the run is checkpointed, a queue can sit unanswered across a server restart
and pick up where it stopped.

---

## The agents

Separated by **kind of judgment**, not pipeline stage — each carries its own confidence
policy, its own evidence, and its own way of explaining itself.

| Agent | Its question | When it refuses to answer |
|---|---|---|
| **Profiler** | What is in this column? | never — it observes |
| **Mapper** | Which target field is this? | two candidates too close; two columns claiming one field |
| **Cleanser** | Can I safely rewrite this? | a date column with no anchor; an enum in the grey band |
| **Identity** | Are these the same human? | a near-match; a shared PAN that might be a rehire |
| **Validator** | Is this record loadable? | it still fails after one repair |
| **Loader** | Is this failure retryable? | the target refused on business grounds |
| **Supervisor** | Is this run worth continuing? | too much escalating, or the file barely maps |

They communicate through **shared typed state, not chat messages**. The sequence is
known in advance, so routing between them through an LLM would add latency, cost and
non-determinism for nothing — and passing 52 employee records through chat messages
would be worse still. Data flows through state; only decisions and rationales pass
through a model.

---

## What it deliberately does not do

- **Guess a date format** with no evidence in the column.
- **Merge two people** on resemblance alone.
- **Queue columns it confidently doesn't recognise** — confident absence is not ambiguity.
- **Ask twice.** A supervisor links each question to the records it already covers, so
  the validator never re-asks in a different shape what the queue already holds.
- **Let a model apply anything.** Model output appears as a recommendation on a card,
  labelled as such. A suggestion a human accepts is auditable; one a model applies
  silently is not.
- **Stop when the models are down.** With no model server it falls back to lexical
  matching, asks more, and completes. Failing toward asking is the correct direction.

---

## Verified behaviour

**70 tests, 50 seconds.** With no model server: 54 pass, 16 skip — semantic scoring
can't be faked meaningfully, so those tests decline to assert something weaker.

The golden test pins the *exact* set of ten questions the sample data should produce.
Every defect in those files was planted to exercise one branch of the policy, so if a
threshold drifts, it fails and names what changed.

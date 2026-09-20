# What real data taught us

The bundled sample exports are deliberately defective, but their defects are the
ones *we thought of*. So the agent was pointed at real public HR datasets to find
out what it got wrong on files nobody designed for it.

## The files

| Dataset | Shape | Why it is a useful test |
|---|---|---|
| [Human Resources Data Set](https://www.kaggle.com/datasets/rhuebner/human-resources-data-set) v14 | 311 rows, 36 columns | Real names, DOBs, hire dates, manager names, US postcodes |
| The same dataset, v9 | 310 rows, 28 columns | The *same entity* with different column names — the reconciliation case, not synthesised |
| [IBM HR Analytics attrition](https://raw.githubusercontent.com/IBM/employee-attrition-aif360/master/data/emp_attrition.csv) | 1,470 rows, 35 columns | Anonymised analytics data with no names, dates or emails at all — should be rejected, not migrated |

They are not committed to this repo. The shapes they exposed are pinned instead as
unit tests in [`tests/test_real_world_shapes.py`](../tests/test_real_world_shapes.py),
so the suite stays hermetic and the repo stays small.

---

## Three things were silently wrong

Every one of these produced *plausible* output. Nothing crashed, no validation
failed, and a consultant reviewing the queue would have seen no sign of them —
which is precisely the failure mode `app/policy.py` is written to avoid.

### 1. Every name in the file was inverted

`"Adinolfi, Wilson  K"` is how essentially every payroll and HRIS export writes a
name. The splitter produced:

```
first_name = "Adinolfi,"      last_name = "Wilson K"
```

Comma included. Both fields non-empty, so every format check passed. A second bug
sat behind it: `"Mary Jane Watson"` gave `last_name = "Jane Watson"`, putting middle
names into the surname.

**Fixed** in `_split_name`. A comma now means surname-first, which is reliable — no
HR system writes "First, Last". Particles stay with the surname (`"van der Berg,
Jan"`), and suffixes stay with the given names (`"Smith, John Jr."`).

The convention is recorded per column, not per row: surname-first as `AUTO`
(the comma settles it) and given-name-first as `FLAGGED`, because that reading is
wrong for a compound surname or a family-name-first culture and nothing in a name
string alone can tell you which applies.

### 2. Race data was auto-mapped into `gender`, and the agent blamed the data

`RaceDesc` scored **0.85** against `gender` and was applied without asking. Then it
did something worse than fail:

```
· Unrecognised gender value 'White' - asking
· Unrecognised gender value 'Asian' - asking
· Unrecognised gender value 'Black or African American' - asking
... four more
```

Seven questions, each asking a human what a race category means as a gender —
blaming the data for a mistake the agent had made itself, and pointing the
consultant at a question nobody can answer.

**Fixed** with a new rule: when a column maps to a field with a fixed vocabulary
and most of its *distinct* values fall outside that vocabulary, the mapping is in
question rather than the values. One column-level question replaces all of them:

> **'RaceDesc' holds 6 value(s) that are not gender values**
> Either the column is not gender at all, or it is and this schema's list of
> accepted gender values does not cover this client.

Both causes are common and look identical from inside the agent, so the question
reports the evidence rather than presupposing which one it is — a consultant can
tell them apart instantly. Threshold: `ENUM_VOCABULARY_MISMATCH` in `app/policy.py`.

This also caught something real about the schema rather than the data: this US
company's departments are `Production`, `IT/IS`, `Admin Offices`, `Executive
Office`. Four of six are outside our enum. That is worth one question saying so.

### 3. One missing field became 300 identical questions

Neither dataset has an email column anywhere, and `work_email` is required. Result:

```
escalations: 300
  record:E0   "Mia Brown cannot be loaded"   work_email is required but empty
  record:E1   "Mia Brown cannot be loaded"   work_email is required but empty
  ... 298 more
```

Three hundred questions, each asking a human to type one person's email address.
This breaks the rule stated as non-negotiable in `CLAUDE.md` — *ask once per column
or per distinct value, never once per row* — in the one place the rule matters most.

The circuit breaker did catch the flood. But a breaker firing is not the same as
asking the right question: the file was fine, the schema field simply had no source
in it, and "abort or continue" is not a useful thing to be asked about that.

**Fixed.** A required field empty on ≥90% of records is treated as structural, and
asked once:

> **Nothing in these files provides work_email**
> The target schema requires it, but it is empty on 300 of 300 records — so no
> column in the source files feeds it.
>
> · Load without it · Skip every record missing it · It is in an unmapped column

A few records missing an email is still per-record dirt and still asks per record.
Threshold: `REQUIRED_FIELD_MISSING_RATE`.

Two follow-on bugs surfaced from this fix and were fixed with it:

- **Answering did nothing.** The mapping is re-derived on every pass, so
  "load without it" flipped straight back to 300 per-record questions on the next
  round. Each of the three answers now has an effect, recorded in the audit trail.
- **The breaker false-positived.** One question naming 300 records read as "100% of
  records need a human". It needed its own escalation type — `FIELD_UNSOURCED` —
  so the supervisor counts it as field-level, the way it already counts date and
  enum questions. Without that, a perfectly answerable question was hidden behind
  "abort or continue".

---

## Four things were already right

Kept as regression tests, because all four fail silently and are cheap to break.

- **A UTF-8 BOM** on the first header. Both datasets ship with one; otherwise the
  first column is named `"﻿Employee_Name"` and matches nothing.
- **Leading-zero postcodes.** `01960` stays a string. Read as a number it becomes
  `1960` — a silent corruption of every postcode in the north-east United States.
- **Two-digit years.** `07/10/83`, `05/05/75`, `09/19/88` — the column's own
  unambiguous rows settle it as month-first, 22 anchors at 100% agreement.
- **Heavy trailing whitespace.** `"Production       "`, `"M "` — normalised.

## The wrong-file check earned its keep

Pointed at the IBM attrition set alone — 1,470 rows of `EnvironmentSatisfaction`,
`PerfScoreID`, `DailyRate`, `Absences` — the agent maps 3 of 35 columns (9%) and
stops with **one** question:

> **These files do not look like employee data**
> Only 3 of 35 columns (9%) resemble anything in the employee schema. Rather than
> raise a question per column, it is worth checking whether this is the right
> export — the shape suggests a different entity altogether.

That is the correct answer, and it is the behaviour `MIN_MAPPING_COVERAGE` exists
for. It also scales: 1,470 rows cost the same ~20 model calls as 52, because the
model sees column profiles and never a record.

---

## The second pass: both files together

Once names were right, v9 and v14 were run **together** — the reconciliation case
the brief describes, on real files. Three more things were wrong, and every one
of them was the same shape: a rule that was correct per item and became a flood
across the file.

### 4. The wrong-file check fired on the right file

35 of 64 columns escalated, and the breaker then declared genuine employee data
"not employee data" (23% coverage, below `MIN_MAPPING_COVERAGE`).

The cause was upstream: the structural signal was not using what the schema
already declares. `MarriedID` (values `0`/`1`) scored 0.67 against `pan`;
`Zip` scored 0.75 against `phone`; `Employee Number` scored **0.97** against
`phone` because both descriptions contain "number"; `Salary` scored 0.81 against
`bank_account`. Every one of those fields has a declared format the values could
never satisfy, and the mapper was not checking.

**Fixed** with three deterministic rules, all in-process, none needing a model:

- A field with a declared format (`pan`, `uan`, `ifsc`, `email`, `phone`,
  `bank_account`) is ruled out when *none* of a column's sampled values fit it.
- A field the schema marks `unique` is ruled out for a column with a handful of
  distinct values — a 0/1 flag is a category, not an employee code.
- A vocabulary of words is ruled out for a numeric column, and a column whose
  values already sit in the vocabulary (`Sex` = `M`/`F`) gets the structural bonus.

35 escalated columns became 13, 33 were correctly ignored, and `Sex`,
`EmpID` and `Employee Number` mapped on their own. Threshold:
`FORMAT_MISMATCH_PENALTY`, `UNIQUE_FIELD_MIN_DISTINCT_RATIO`.

The breaker itself was also measuring the wrong thing. A wide HRIS export is
*mostly* analytics columns; low column coverage does not make it a wrong file.
What does is the required fields being absent: this export has 8 of 10, the IBM
extract has 2, a brokerage statement has none. It now needs both signals low
(`MIN_REQUIRED_FIELDS_FOUND`).

### 5. 275 "are these the same person?" questions

With mapping right, the identity resolver found what the section below used to
call unhandled: every person appears in both files, matched on full name and
date of birth, under two different ID systems. It asked 275 times.

Each question was correct. Together they were the flood. **Fixed** by recognising
the pattern as one fact about the two files rather than 275 facts about people:

> **HRDataset_v14.csv and HRDataset_v9.csv look like two exports of the same people**
> 275 pairs of records — one from each file — share a full name and date of birth,
> but carry different employee codes and no shared unique identifier … That is not
> 275 coincidences; it is two systems describing the same staff.
>
> · Same people — merge each pair · Different people — keep all · Review each pair

"Review each pair" keeps the per-pair questions for anyone who wants them. Below
ten pairs, or under half the smaller file, pairs are still asked individually.
Threshold: `IDENTITY_FLOOD_MIN`, `IDENTITY_FLOOD_RATE`.

### 6. The same column asked about twice

`State`, `MaritalDesc` and `Department` exist in both files and were asked about
once per file. One column name is one question; an answer to either file now
applies to both in the same pass, not just via memory on the next run.

### Measured, both files together

64 columns, 621 rows. **15 questions** on the first pass, 6 vocabulary questions
on the second, then **346 people, 346 loaded**, 274 of them merged across the
files, 963 audit entries, under a minute end to end. Before this pass the same
files produced 290 questions and a false "wrong file" stop.

## What is still not handled

Named rather than half-built, because these are real and a reviewer will spot them.

- **Manager by name, not email.** Both datasets identify managers as
  `"Michael Albert"`, and the schema's `manager_email` expects an address. The
  mapper escalates it rather than guessing, which is correct — but the useful
  behaviour would be to resolve the name against the employee set and propose the
  matching email, which is a real inference it could make and does not.
- **Conflicting values after a merge.** When both files carry a field and
  disagree, the more complete record's value wins and the conflict is noted in
  the audit entry. A per-field source precedence would be the proper answer.
- **A vocabulary that does not fit the client.** The `department` enum is eight
  Indian-startup departments. Against a US manufacturer it reports four mismatches
  per file. The agent now asks about it once, which is right, but the productisable
  answer is a per-client vocabulary learned from the first migration and carried in
  the recipe.

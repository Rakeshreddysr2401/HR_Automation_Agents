# Testing it yourself

Everything you need to drive this by hand: what to give it, what comes back, and
a kit of files that each provoke exactly one behaviour.

```bash
.venv/bin/uvicorn app.main:app --port 8000     # then open http://localhost:8000
python scripts/make_testkit.py                 # writes data/testkit/
```

---

## 1. What you have to give it

### The source files — the only thing that is truly required

One or more **CSV or Excel** files describing employees. That is the whole
contract. Specifically, they may:

- use any column names at all (`emp_cd`, `Employee Code`, `staff_no`)
- write dates any way (`03/04/2021`, `2021-04-03`, `07/10/83`)
- disagree with each other about both
- contain the same person more than once
- omit fields entirely

The agent works the rest out, and asks when it genuinely cannot.

**It does not need:** a mapping file, matching headers between files, a
particular date format, sorted or deduplicated rows, or a header row that has
been cleaned up. A UTF-8 BOM, trailing whitespace and leading-zero postcodes are
all handled.

### The target schema — already provided

`schema/target_employee.yaml`, 21 fields. You only touch this if you want to
migrate into a *different* shape. `data/testkit/00_target_template.csv` is the
same thing as a spreadsheet you can look at.

| Field | Type | Required | Notes |
|---|---|---|---|
| `employee_code` | string | **yes** | unique, strong identity |
| `first_name` | string | **yes** | |
| `last_name` | string | **yes** | |
| `work_email` | string | **yes** | unique, strong identity, email format |
| `personal_email` | string | | email format |
| `phone` | string | | 8–18 digits, optional country code |
| `date_of_birth` | date | **yes** | |
| `date_of_joining` | date | **yes** | |
| `date_of_exit` | date | | |
| `department` | enum | **yes** | Engineering, Sales, Marketing, Human Resources, Finance, Operations, Customer Success, Legal |
| `designation` | string | **yes** | |
| `employment_type` | enum | **yes** | Permanent, Contract, Intern, Consultant |
| `grade` | string | | L3, M2, Band 4 |
| `location` | string | | |
| `gender` | enum | | Male, Female, Other, Undisclosed |
| `manager_email` | string | | must resolve to another employee's `work_email` |
| `pan` | string | | PII, `ABCDE1234F` |
| `uan` | string | | PII, 12 digits |
| `bank_account` | string | | PII |
| `ifsc` | string | | `HDFC0001234` |
| `status` | enum | **yes** | Active, Inactive |

Six business rules are enforced on top: joining after birth, a plausible age at
joining, exit after joining, managers that resolve, no reporting cycles, and an
exit date whenever status is Inactive.

### Optional

- **A model server.** Local Ollama or llama.cpp, configured in `.env`. Without
  one it falls back to lexical matching, asks somewhat more, and still finishes.
  Check the header of the UI — it says which models are reachable.
- **A recipe** from a previous run, pasted into *Start from a recipe* on the Run
  tab. Pre-answers anything already settled.

---

## 2. What you get back

| Where | What |
|---|---|
| **Run** | A live log of its reasoning, line by line |
| **Review** | The questions. Each card carries the evidence to decide at a glance |
| **Mapping** | Every source column, the field it reached, its score and its rivals |
| **Dry run** | The exact payload per record, plus every edit made without asking |
| **Records** | Per-record push results, retry, rollback |
| **Decisions** | Everything it settled alone, grouped, with reasons |
| **Audit** | Every change, actor, before → after, rationale. PII masked |
| **Boundary** | The thresholds, read live from `app/policy.py` |

---

## 3. The test kit

Twelve files, each provoking one behaviour. The bundled sample exports exercise
everything at once — right for a demo, unhelpful when you want to know *which*
input caused which question.

Run `python scripts/make_testkit.py`, then drag a file onto the Run tab.

**The numbers below are measured, not estimated.** Start each one from a fresh
database (`rm migration.db checkpoints.db*`) — answers are remembered across
runs, so a second run of the same file legitimately asks less.

| File | People | Questions | What it proves |
|---|---|---|---|
| `01_clean.csv` | 15 | **0** | The control. Clean data is not interrogated |
| `02_renamed_columns.csv` | 15 | **0** | `emp_cd`, `fname`, `division`, `doj`… all understood with no help |
| `03_ambiguous_dates.csv` | 15 | **1** | One date question covering all 15 rows — not 15 |
| `04_unknown_values.csv` | 15 | **1** | `Engg` is asked. `"  finance  "`, `FTE` and `M` are fixed silently |
| `05_identity.csv` | 14 | **1** | An exact duplicate merges silently; the rehire is asked about |
| `06_broken_records.csv` | 12 | **4** | Four genuinely broken records; a messy phone number is repaired |
| `07_hierarchy.csv` | 12 | **2** | One orphan question covering 3 reports, plus one reporting loop |
| `08` + `09` together | 18 | **3** | **30 rows reconcile into 18 people, 12 merged** |
| `10_wrong_file.csv` | 20 | **1** | An asset inventory is refused once, not mapped column by column |
| `11_no_email_column.csv` | 20 | **1** | A required field with no source is one question, not 20 |
| `12_surname_first.csv` | 15 | **1** | `"Sharma, Aarav"` splits correctly; it confirms the column once |

### The three worth actually watching

**`08` + `09` together** — select both files. This is the assignment's central
scenario: two exports of the same people, different column names, different
identifier coverage. One half carries emails and dates, the other PAN and UAN.
Watch the log say *"Reconciled 30 rows into 18 people (12 merged from multiple
sources)"*, then open **Dry run** and look at a merged record — it holds fields
neither file had alone.

**`05_identity.csv`** — the best single moment. It contains a true duplicate and
a rehire, which look *identical* to any generic dedup routine. The duplicate is
merged without asking. The rehire is not, because merging it would destroy the
service history gratuity is calculated from — and neither the agent nor you can
tell from the data alone. Read the card; it says what is at stake.

**`11_no_email_column.csv`** — a required field that no column provides. One
question about the field, with three real options, rather than twenty asking you
to type an address. Answer *"Load without it"* and all twenty records go through.

### Deliberately not in the kit

`10_wrong_file.csv` trips the circuit breaker on **coverage** (9% of columns
match). To see it trip on **rate** instead you need a file where a quarter of
records are blocked *and* at least 12 questions come out — a short queue never
stops a run, however bad the ratio, because 4 questions is not a flood.

---

## 4. A full pass in five minutes

1. `rm -f migration.db checkpoints.db*` and start the server.
2. **Run tab** → *Run the sample migration* (no file selected). Watch the log.
3. It stops with **8 questions** on 35 columns and 42 people.
4. **Review tab.** Work it from the keyboard: `1`–`9` picks an option and
   advances, `u` undoes, `⌘↵` applies. Answer the rehire card *"keep both"*.
5. It comes back twice more: first with a second mapping question and a
   reporting loop, then with an orphaned manager. The hierarchy checks were
   deferred on purpose — resolving managers before the email columns are known
   would report false orphans. Answer them.
6. **Dry run tab.** The exact payloads, and every edit made without asking.
   Export the recipe.
7. It pushes. Two records fail transiently and are retried; one is rejected by
   the target and escalated rather than retried forever.
8. **Records tab.** Select two loaded records → *Roll back*. It demands a reason.
9. **Audit tab**, filtered to `human` — everything you decided, and why.
10. **Run tab** → paste the recipe into *Start from a recipe* → run again. It
    asks **nothing at all** and runs straight through to the push. That is the
    productisation claim, made checkable: the second migration of a similar
    export costs a fraction of the first.

---

## 5. Making your own test file

Take `data/testkit/00_target_template.csv`, rename the columns to whatever your
client actually uses, and break something on purpose:

| To provoke | Do this |
|---|---|
| A mapping question | Two columns that could both be the work address |
| A date question | Make every date have day ≤ 12 **and** month ≤ 12 |
| A value question | A department like `Engg` — close to a real value, not close enough |
| A duplicate merge | Repeat a row with a different `employee_code`, same `work_email` |
| A rehire question | Same `pan`, two codes, non-overlapping joining/exit dates |
| An orphan | A `manager_email` belonging to nobody in the file |
| A cycle | Two people whose `manager_email` point at each other |
| The wrong-file breaker | Replace the columns with something that is not an employee |
| A structural gap | Delete the `work_email` column entirely |

---

## 6. Running the tests

```bash
.venv/bin/python -m pytest        # 155 backend tests
cd web && npm test                # 22 frontend tests
```

Some backend tests skip rather than pass when no embedding model is reachable —
semantic scoring cannot be faked meaningfully, so they decline to assert
something weaker instead of going quietly green.

`tests/test_golden_run.py` pins the **exact** set of questions the sample data
should produce. Every defect in those files was planted to exercise one branch of
the policy, so if a threshold drifts it fails and names what changed. If you
change the sample data or a threshold on purpose, update that test on
purpose — do not adjust it until it passes.

## 7. If something looks wrong

| Symptom | Likely cause |
|---|---|
| Far more questions than the table says | Stale `migration.db` — or no embedding model, so it fell back to lexical matching |
| Far fewer | Memory. A previous run already answered them; delete `migration.db` |
| *"These files do not look like employee data"* | Under 35% of columns matched the schema. Usually correct |
| *"Too much of this run needs a human"* | A quarter of records blocked **and** 12+ questions. Answer the mapping questions first — they cascade |
| The UI is blank | `cd web && npm run build`; the API serves `web/dist` |
| Questions reappear after answering | Expected for `remap` answers, which deliberately leave the question open |

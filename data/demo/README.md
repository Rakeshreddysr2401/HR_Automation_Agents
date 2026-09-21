# Demo pair — 9 + 7 people, one story per row

Regenerate with `python scripts/make_demo_data.py`. For a clean run, stop the
server and delete `migration.db` and `checkpoints.db` first — the agent remembers
column answers between runs, so a second run asks fewer questions.

Upload **both** files together in the Run tab.

| File | What it looks like |
|---|---|
| `old_hr_system.csv` | Legacy HR: full names in one column, `DD/MM/YYYY` dates, two email columns, messy spacing |
| `payroll_export.xlsx` | Payroll: split names, ISO birth dates, statutory IDs (PAN, UAN, bank), different column names |

## Who is in it, and why

| Code | Person | The one thing they demonstrate |
|---|---|---|
| E1001 | Aarav Sharma | `"  aarav  SHARMA "` → fixed silently. Open him in **Preview** to see the before → after |
| E1002 / E1003 | Priya Nair, Rohan Mehta | Report to each other — a reporting loop (appears in round 2) |
| E1004 | Diya Patel | Department `Engg` — 77% like Engineering, close enough to suspect, too far to assume |
| E1005 | Vikram Rao | Inactive with no exit date — fails validation twice, needs a value from you |
| E1006 | Meera Joshi | PAN `MEERA123` — malformed, needs a value from you |
| E1007 / P100 | Sana Qureshi / Sana Q. | Same birthday and first name, different codes — duplicate or two people? |
| E0910 / E1031 | Rakesh Reddy | Same PAN, left 2019, back 2023 — rehire or duplicate? Merging would destroy his first stint |
| E1021 | Arjun Iyer | Reports to someone who has left (round 2); then the HRMS refuses his code on push |
| E1015 | Nikhil Agarwal | The HRMS times out once on push, then accepts on retry |

## What you will see

**Round 1 — 7 questions** out of 29 columns and 16 rows:

1. Which column is `work_email`? — `Official Email` vs `Mail ID` → **Official Email**
2. Is `joining_dt` day-first or month-first? → **Day first**
3. What does `Engg` mean? → **Engineering**
4. Is Rakesh Reddy a rehire or a duplicate? → **Keep both — this is a rehire**
5. Are these the same person? Sana → **Same person — keep E1007**
6. Vikram Rao cannot be loaded → type a `date_of_exit`, e.g. `2024-03-31`
7. Meera Joshi cannot be loaded → type a `pan`, e.g. `MEERA1234J`

Press **Confirm & Apply**. Watch the log: 16 rows become 11 people.

**Round 2 — 3 questions** that could not be asked before (the banner says why):

1. Which field is `Mail ID`? → **personal_email**
2. Who does Arjun Iyer report to? → **Clear the reporting line**
3. Priya and Rohan report to each other → **Clear Rohan's manager**

**Push** happens on its own: E1015 and E1031 hit a transient error and succeed on
retry; **E1021 is refused** by the HRMS and comes back as one more card →
**Leave it out**.

Result: **10 loaded, 1 skipped, 11 questions in all** — everything else the agent
settled itself, and every one of those decisions is in Preview, Auto decisions and
the Audit log.

## Tabs worth opening while it runs

- **Preview** → click Aarav: the final record on the left, the fixes on the right.
- **Mapping** → filter *Left behind*: `ctc_annual` has no home in the schema, so it
  was dropped and reported rather than asked about.
- **Records** → tick a loaded row → *Roll back* (a reason is required and goes in
  the audit) → tick it again → *Push again*.
- **Audit log** → filter *You*: the two values you typed, PAN masked even though you
  typed it.
- **Preview → Recipe → Export**, then start a new run with the recipe pasted in:
  it asks nothing.

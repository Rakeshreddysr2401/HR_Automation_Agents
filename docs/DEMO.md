# Demo script

Ninety seconds, and it must show at least one escalation being resolved through the
UI — that is an explicit requirement of the brief.

**Before recording:** `rm -f migration.db checkpoints.db` (a previous run's learned
mappings would suppress the very question the demo depends on), start the server, open
http://localhost:8000, and check the header badges show a reachable model.

---

### 0:00 — Frame the problem (10s)

> "A client is moving onto a new HRMS. Their data arrives as a legacy HRIS export and a
> payroll spreadsheet that disagree with each other about column names, date formats and
> who is who. Normally an implementation consultant maps this by hand."

### 0:10 — Start the run (15s)

Press **Run the sample migration**. Let the live log scroll — it narrates itself. Point at
one line:

> "It worked out that this column is day-month-year because 18 rows have a day above 12.
> It applied that to all 33 and told me, rather than asking."

### 0:25 — The queue (15s)

> "Thirty-five columns, fifty-two people, and it needs me for **ten** things. That ratio is
> the whole point — it didn't ask me to confirm every field, and it didn't guess at the
> things it couldn't know."

### 0:40 — Resolve the rehire (25s) — *the important bit*

Open **"Is Rakesh Reddy a rehire or a duplicate?"**

> "Same PAN, two employee codes, service that doesn't overlap. That is exactly what a
> duplicate looks like — and exactly what a rehire looks like. Generic dedup merges them,
> and that destroys the earlier service history that gratuity is calculated from. Nothing
> in the data can settle it, so it asks, and it tells me why it matters."

Choose **Keep both — this is a rehire**. Answer the rest quickly, then **Apply decisions**.

### 1:05 — The cascade (15s)

Watch the second pass:

> "One answer changed more than one field. Confirming which column holds the work email
> let it match the two files against each other — fifty-two records just became forty-one,
> and two validation failures fixed themselves because the merge supplied what was missing."

### 1:20 — Push, and the trail (10s)

> "Forty records loaded. Two hit transient errors and succeeded on retry. One was rejected
> by the target on business grounds — retrying wouldn't change that answer, so it came back
> to me."

Open **Audit**, filter to **human**:

> "Every change, who made it, and why. The PAN is masked even though I typed it myself."

---

## If something goes wrong on camera

- **No questions appear** — a previous run's memory suppressed them. Delete the two `.db`
  files and start again.
- **More than ten questions** — no embedding model reachable, so mapping is running on
  column names alone. Check the header badges.
- **A long pause on a card** — the reasoning model is writing the recommendation. It is not
  in the critical path; the question is already fully formed without it.

# What is left to do

Status as of 2026-09-18. Submission deadline: **Monday 21 September 2026, 12:00 IST**.

The system works end to end today: it ingests two mismatched exports, maps and cleans
them autonomously, raises ten genuine questions, takes answers through a web UI,
re-runs consistently, and pushes to a mock target with retry, rollback and a full
audit trail. What follows is what would make it a stronger submission.

Ordered by what actually moves the needle with the panel.

---

## 1. Must do before submitting

### 1.1 Look at the UI in a browser `[ ]`  — *highest priority*
Never opened in a browser. The build compiles, every API path resolves, and every
field each card reads exists in the real payloads — but layout, spacing, dark mode
and the keyboard triage are all unverified visually.

```bash
uvicorn app.main:app --reload     # then open http://localhost:8000
```

Walk all five tabs, resolve one card of each type, and note anything that reads wrong.

### 1.2 The one-page write-up `[ ]` — *explicitly graded*
`docs/WRITEUP.md`, one page maximum. Three things, in this order:
- the approach in a paragraph;
- **how the line was drawn between acting and asking** — this is the question they
  said they will press on, so it gets the most space;
- what would come next.

Most of the raw material is already in `docs/ESCALATION-POLICY.md`; the work is
compressing it to a page without losing the argument.

### 1.3 Demo recording `[ ]` — *explicitly required*
"The recording should show at least one escalation getting resolved through the UI."
Ninety seconds is plenty. Script to write into `docs/DEMO.md`:

1. Start the run; let the live log scroll — it narrates itself.
2. Land on the queue: **ten questions out of thirty-five columns and fifty-two people.**
   Say why that ratio is the point.
3. Open the rehire card. This is the strongest single moment in the demo: one PAN,
   two employee codes, and merging it would destroy the service history that gratuity
   is calculated from. Answer "keep both".
4. Answer the rest, apply, and watch the second pass: **fifty-two records become
   forty-one** as the files reconcile, and two validation failures disappear on their
   own because the merge supplied what was missing.
5. Push. Two transient failures retry and succeed; one business rejection escalates
   instead of retrying forever.
6. Finish on the audit trail, filtered to `human`.

### 1.4 Tests `[ ]`
`pytest` suite. The valuable ones, in order:
- **golden run** — asserts the exact escalation set from the sample data. This is the
  regression net for the whole policy; if a threshold drifts, it fails.
- **policy boundaries** — each threshold branch in `app/policy.py`, both sides.
- **date inference** — anchors present, anchors absent, conflicting anchors, ISO.
- **interrupt/resume** — the graph stops, takes decisions, and drains.
- **retry and rollback** — against the mock target's deterministic failures.
- **PII** — no unmasked identifier ever reaches the audit trail (this one caught a
  real bug already).

### 1.5 README polish `[~]`
- [x] Quickstart verified against a fresh clone end to end: install, UI build, boot,
      and a full run stopping at ten questions. Written up in `docs/RUNNING.md`.
- [ ] Add a screenshot of the review queue, once the UI has been looked at.

---

## 2. Worth doing if time allows

### 2.1 Threshold sweep `[ ]`
`scripts/sweep_thresholds.py` — re-run the sample migration across a range of
`MAPPING_AUTO_MIN` and `MAPPING_MARGIN_MIN` values and print, for each, how many
columns map automatically, how many escalate, and **how many map wrongly**.

Turns "why 0.82?" from an opinion into a measurement, and it is the single best
answer to the question they promised to ask. Roughly an hour.

### 2.2 Dry-run diff `[ ]`
Show exactly what will change per record before anything is sent. Real migration
tooling always has this, and it is a natural extra gate before the push.

### 2.3 Migration recipe export `[ ]`
`app/recipe.py` — export the whole decision set (mappings, transforms, canonical
enum values) as reviewable YAML that can be version-controlled and replayed against
the next client's files. The productisation story: build once, deploy to many.

The groundwork is already there, since every decision is keyed by a stable `subject`.

### 2.4 Dockerfile `[ ]`
`docker compose up` as the one-command path for an evaluator who does not want to
install Python and Node.

---

## 3. Deliberately not building — for the write-up's "what next"

These are the honest next steps, and naming them is worth more than half-building them.

- **Effective-dated history.** HR records are temporal: promotions and transfers are
  changes over time, not overwrites. A real migration carries that history rather than
  flattening it to a current state.
- **Multi-entity dependency ordering.** Org units before employees before payroll,
  because each references the one before it.
- **Active learning on thresholds.** Every resolved escalation is a labelled example.
  The thresholds could be fitted to a client's own resolution history instead of set
  by hand.
- **Connector-based ingestion.** File drops are the demo; real clients want SAP,
  PeopleSoft and Zoho pulled directly, with the same escalation boundary on top.
- **Parallel chunked processing** for 100k+ rows. The decision/execution split already
  makes this straightforward: rules are decided once, then applied to shards
  independently.

---

## 4. Known rough edges

- `MAX_ROUNDS` (6) caps the analyse→review loop. A run that somehow keeps generating
  new questions stops rather than looping forever, but the UI does not explain that
  state well.
- Uploaded files are trusted as CSV/Excel by extension. Fine for a take-home, not for
  anything public.
- The mock target holds state in memory, so restarting the server empties it while
  SQLite still records what was pushed. Deliberate — it keeps the demo reproducible —
  but worth saying out loud rather than being caught by it.
- `hierarchy_orphan` and `hierarchy_cycle` only surface once the email columns are
  confirmed, because resolving managers against an incomplete set would report false
  orphans. Correct, but it means they appear in the second review round, not the first.

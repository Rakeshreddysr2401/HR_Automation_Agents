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

### 1.2 The one-page write-up `[x]` — *explicitly graded*
Written: [`docs/WRITEUP.md`](WRITEUP.md), 795 words. Leads with the
decision/execution split, spends the most space on where the line was drawn, and
closes with two things stated honestly — that the thresholds are not what is keeping
the sample correct (the assignment step is), and why a multi-agent chat framework was
deliberately not used.

### 1.3 Demo recording `[~]` — *explicitly required*
Script written: [`docs/DEMO.md`](DEMO.md) — ninety seconds, with the wording to say
at each beat and what to do if something misbehaves on camera. **Still to do: record
it.** The beats are:

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

### 1.4 Tests `[x]`
**70 tests, 50s** (`.venv/bin/python -m pytest`). With no model server reachable:
54 pass, 16 skip — the suite refuses to assert a weaker claim rather than passing
quietly.

- `test_golden_run.py` — the exact escalation set, the cascade one answer triggers,
  the wrong-file circuit breaker, and the degraded no-model path.
- `test_policy.py` — both sides of every threshold in `app/policy.py`.
- `test_dates.py` — anchors present, absent, contradicting, ISO, two-digit years.
- `test_graph.py` — the gate stops once for the whole queue, resumes, handles a
  partial answer, and remembers.
- `test_loader.py` — transient retried, business rejection escalated, idempotency
  preventing a duplicate, rollback recording its reason.
- `test_pii.py` — nothing unmasked reaches a model or the audit trail.

### 1.5 README polish `[~]`
- [x] Quickstart verified against a fresh clone end to end: install, UI build, boot,
      and a full run stopping at ten questions. Written up in `docs/RUNNING.md`.
- [ ] Add a screenshot of the review queue, once the UI has been looked at.

---

## 2. Worth doing if time allows

### 2.1 Threshold sweep `[x]`
Built: `scripts/sweep_thresholds.py`, a 63-cell grid over confidence and margin.

The result is more interesting than expected and is written up in the write-up: **no
setting in the grid produces a wrong mapping**, including the most permissive. The
thresholds are not what keeps this sample correct — the assignment step is, because
columns compete for a target field and ambiguity resolves structurally. The tight
defaults cost two extra questions here, which is the premium paid for inputs the
sample does not represent.

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

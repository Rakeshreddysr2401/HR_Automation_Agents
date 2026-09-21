# What is left to do

Status as of 2026-09-19. Submission deadline: **Monday 21 September 2026, 12:00 IST**.

The system works end to end: it ingests two mismatched exports, maps and cleans them
autonomously, raises ten genuine questions, takes answers through a web UI, re-runs
consistently, pushes to a mock target with retry, rollback and a full audit trail,
previews exactly what it will send, and exports its decisions as a replayable recipe.

**163 tests pass** — 141 backend (`.venv/bin/python -m pytest`) and 22 frontend
(`cd web && npm test`).

It has also been run against real public HR datasets, which found three silent
bugs — all fixed. See [REAL-DATA.md](REAL-DATA.md).

---

## 1. Must do before submitting

### 1.1 Look at the UI in a browser `[ ]` — *the one real gap*
Still never opened in a browser. What *has* been verified without one:

- `tsc -b` clean, `npm run build` clean, 22 frontend tests pass.
- The compiled CSS contains all three appearance axes (`data-theme=dark`,
  `data-accent=*`, `data-density=compact`) and Tailwind utilities resolve through
  the token variables, so theme switching works at runtime.
- Every API path the UI calls was driven end to end over real HTTP: a full
  migration, three rounds of review, the push with its retries and one rejection,
  retry, rollback (refused without a reason), the dry run, and a recipe replay.

What has *not* been verified: layout, spacing, whether the dark palette reads well,
and whether the keyboard triage feels right under the hand.

```bash
.venv/bin/uvicorn app.main:app --port 8000     # then open http://localhost:8000
```

Walk the eight tabs, resolve one card of each type, flip the theme and the density,
and note anything that reads wrong.

### 1.2 Build the Docker image once `[ ]`
`Dockerfile` and `docker-compose.yml` are written but were never built — no Docker
daemon was running in this session. The env-var contract they depend on
(`DB_PATH`, `CHECKPOINT_PATH`, `UPLOAD_DIR`) is verified against `Settings`.

```bash
docker compose up --build        # then open http://localhost:8000
```

### 1.3 Demo recording `[~]` — *explicitly required*
Script written: [`docs/DEMO.md`](DEMO.md). **Still to record.** The beats, updated
for the views that now exist:

1. Start the run; let the live log scroll — it narrates itself.
2. Land on the queue: **eight questions out of thirty-five columns and fifty-four
   rows.** Say why that ratio is the point.
3. Open the rehire card. The strongest single moment: one PAN, two employee codes,
   and merging would destroy the service history gratuity is calculated from.
   Answer "keep both".
4. Answer the rest from the keyboard — `1`–`9` picks and advances — then `⌘↵`.
   Watch the second pass: **54 rows become 41 people** as the files reconcile, and
   three new questions appear that could not be asked before — which field the
   second email column feeds, a reporting loop, and a manager nobody in the files
   has. Say why they were deferred.
5. **Preview tab.** This is the new beat and worth the time: the exact payload per
   record, and the 35 field edits the agent made without asking, each with its
   reason. Then export the recipe.
6. Push. Two transient failures retry and succeed; one business rejection escalates
   instead of retrying forever.
7. **Rules tab** for ten seconds — the thresholds, read live from `policy.py`.
8. Finish on the audit trail, filtered to `human`.

Optional closer, if the recording has room: paste the exported recipe into *Start
from a recipe* on a fresh run and show it asking **one** question instead of ten.

### 1.4 README screenshot `[ ]`
Add one of the review queue and one of the dry run, once the UI has been looked at.

---

## 2. Worth doing if time allows

- **Effective-dated history.** The largest honest gap. HR records are temporal:
  promotions and transfers are changes over time, not overwrites. Named in the
  write-up as the first thing to build next.
- **Recipe-driven bulk mode.** The recipe already replays answers; the next step is
  running it headlessly over a directory of client files with no UI at all.
- **Frontend tests for the panels.** The parser, the appearance store and the
  escalation card are covered; the eight panels are not.
- **Resolve managers given by name rather than email.** Both real datasets
  identify managers as `"Michael Albert"`. The mapper escalates rather than
  guessing, which is correct, but matching the name against the employee set and
  proposing the address is an inference it could make and does not.
- **A per-client value vocabulary.** The `department` enum is eight
  Indian-startup departments; against a US manufacturer four of six values
  mismatch. Asking once about it is right; learning the client's vocabulary on
  the first migration and carrying it in the recipe is the product answer.

---

## 3. Deliberately not building — for the write-up's "what next"

Naming these is worth more than half-building them.

- **Multi-entity dependency ordering.** Org units before employees before payroll,
  because each references the one before it.
- **Active learning on thresholds.** Every resolved escalation is a labelled
  example. The thresholds could be fitted to a client's own resolution history
  instead of set by hand.
- **Connector-based ingestion.** File drops are the demo; real clients want SAP,
  PeopleSoft and Zoho pulled directly, with the same escalation boundary on top.
- **Parallel chunked processing** for 100k+ rows. The decision/execution split
  already makes this straightforward: rules are decided once, then applied to
  shards independently.

---

## 4. Known rough edges

- `MAX_ROUNDS` (6) caps the analyse→review loop. A run that somehow keeps generating
  new questions stops rather than looping forever, but the UI does not explain that
  state well.
- Uploaded files are trusted as CSV/Excel by extension. Fine for a take-home, not
  for anything public.
- The mock target holds state in memory, so restarting the server empties it while
  SQLite still records what was pushed. Deliberate — it keeps the demo reproducible
  — but worth saying out loud rather than being caught by it.
- `hierarchy_orphan` and `hierarchy_cycle` only surface once the email columns are
  confirmed, because resolving managers against an incomplete set would report false
  orphans. Correct, but it means they appear in the second review round, not the
  first. The queue now says so in a banner on every round after the first.
- Which of two conflicting values the merge keeps depends on row completeness, and
  completeness shifts as columns get mapped — Sanjay Kapoor's manager flips from the
  payroll value to the HRIS value once `Mail ID` is confirmed, which is why the
  orphan question arrives a round later than the loop. The conflict is in the audit
  entry either way; a per-field source precedence is the proper fix.
- Escalation counts depend on whether the database is fresh. Mapping memory means
  the second run of the same files asks fewer questions. That is the feature working,
  but it surprises you the first time.

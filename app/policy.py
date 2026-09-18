"""The escalation boundary, in one file.

Every number that decides "act" versus "ask" lives here, so the boundary can be
reviewed, tuned and argued about without reading the pipeline. `scripts/
sweep_thresholds.py` re-runs the sample migration across a range of these values
and prints what each choice costs, which is how these defaults were picked.

The governing principle
-----------------------
    Escalate when being wrong is silent and irreversible.
    Auto-fix when being wrong would be loud and cheap to undo.

Trimming a trailing space is safe: if it were somehow wrong, a human sees it
immediately and fixes it in seconds. Picking the wrong reading of 03/04/2021 is
not: nothing downstream looks wrong, and the error quietly distorts tenure,
leave accrual and gratuity for years. Same "small" data fix, opposite blast
radius - so they sit on opposite sides of the line.

Three tiers, not two
--------------------
AUTO      applied silently - deterministic, or evidence leaves one answer standing
FLAGGED   applied but surfaced - a defensible inference the human should be able
          to audit in seconds without being asked to approve it
ESCALATED blocked - the evidence genuinely supports more than one answer

Most implementations only have AUTO and ESCALATE, which forces a choice between
an agent that hides its reasoning and one that interrupts constantly. FLAGGED is
what lets the queue stay short while the agent stays transparent.
"""

from __future__ import annotations

from app.models import Disposition

# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------
# Score blends semantic similarity (the column name and its sample values,
# embedded against the target field's description) with literal string
# similarity of the names. Embeddings catch "worker_category" -> employment_type
# where string matching fails; string matching catches abbreviations like
# "DOB" where embeddings are weak. Neither alone is good enough.
EMBEDDING_WEIGHT = 0.6
FUZZY_WEIGHT = 0.4

# Raw cosine over a single-domain schema has a high floor (~0.45) and a narrow
# ceiling (~0.78), so it is standardised within each column's own candidate set
# before use. A field this many standard deviations above its set's mean counts
# as a full-strength semantic match. Measured, not guessed: the correct field
# sits 2-4 sigma above the mean across the sample columns.
SEMANTIC_Z_FULL_SCALE = 2.5

# Semantic similarity ranks candidates well but cannot tell "the best of these"
# from "any of these". Lexical overlap is what separates a real match from none:
# "mobile" genuinely echoes the phone field's aliases, "ctc_annual" echoes
# nothing in the schema. A column with no lexical foothold anywhere and no
# strong overall score is dropped rather than queued.
LEXICAL_EVIDENCE_FLOOR = 0.45

# A mapping is applied only if it is both confident AND unrivalled. The margin
# test is the important half: a column scoring 0.91 against work_email and 0.89
# against personal_email is not a confident mapping, it is a coin flip wearing a
# high score. Confidence alone would auto-apply it and silently corrupt the
# field that half the HRMS keys off.
MAPPING_AUTO_MIN = 0.82
MAPPING_MARGIN_MIN = 0.12

# Below this, the agent is not uncertain - it is confident there is no match.
# "ctc_annual" has no home in the target schema, and asking a human to confirm
# that would be noise. Dropped columns are reported, never queued.
MAPPING_IGNORE_MAX = 0.50

# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
# 03/04/2021 is unreadable on its own. But a column is written by one system in
# one convention, so a single unambiguous sibling value (day > 12) settles the
# whole column. Requiring several anchors that agree guards against a column
# that is itself internally inconsistent.
DATE_MIN_ANCHORS = 3
DATE_ANCHOR_AGREEMENT = 0.9

# ---------------------------------------------------------------------------
# Enum canonicalisation
# ---------------------------------------------------------------------------
# "engineering  " -> Engineering is normalisation, not a guess. "Human Resource"
# -> "Human Resources" is a near-certain typo. "Engg" -> "Engineering" looks
# obvious to a human but scores like a coin flip, and the failure is silent, so
# it gets asked. The grey band is where the agent stops trusting itself.
ENUM_AUTO_MIN = 90.0
ENUM_ESCALATE_MIN = 70.0

# Deterministic alias tables. This is domain knowledge, not inference: no model
# needs to be consulted to know that "M" means Male in an HR export. Encoding it
# here keeps it out of the escalation queue and out of a prompt.
SAFE_ALIASES: dict[str, dict[str, str]] = {
    "gender": {
        "m": "Male", "male": "Male", "man": "Male",
        "f": "Female", "female": "Female", "woman": "Female",
        "o": "Other", "other": "Other", "non-binary": "Other",
        "u": "Undisclosed", "na": "Undisclosed", "n/a": "Undisclosed",
        "not disclosed": "Undisclosed", "prefer not to say": "Undisclosed",
    },
    "employment_type": {
        "fte": "Permanent", "full time": "Permanent", "full-time": "Permanent",
        "permanent": "Permanent", "perm": "Permanent", "regular": "Permanent",
        "contractor": "Contract", "contract": "Contract", "temp": "Contract",
        "temporary": "Contract", "fixed term": "Contract",
        "intern": "Intern", "internship": "Intern", "trainee": "Intern",
        "consultant": "Consultant", "advisor": "Consultant",
    },
    "status": {
        "a": "Active", "active": "Active", "current": "Active", "working": "Active",
        "y": "Active", "yes": "Active", "employed": "Active",
        "i": "Inactive", "inactive": "Inactive", "left": "Inactive",
        "exited": "Inactive", "resigned": "Inactive", "terminated": "Inactive",
        "n": "Inactive", "no": "Inactive", "separated": "Inactive",
    },
}

# ---------------------------------------------------------------------------
# Identity resolution
# ---------------------------------------------------------------------------
# Two rows are the same person without argument when a nationally unique
# identifier matches (PAN) or the work email matches. Everything softer is a
# judgment call, because merging two people is unrecoverable once payroll runs
# against it, while leaving a duplicate is visible and fixable.
IDENTITY_NAME_SIMILARITY = 92.0

# A rehire looks exactly like a duplicate to any generic dedup routine: same
# human, two employee codes. Merging destroys the service history that gratuity
# and tenure are computed from, so the agent never decides this one itself.
REHIRE_GAP_DAYS = 30

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
# One deterministic repair attempt, then ask. The second failure is the signal:
# the first tells you the value was messy, the second tells you the mess is not
# mechanical. Retrying further just burns time on data that needs a decision.
MAX_REPAIR_ATTEMPTS = 1

# ---------------------------------------------------------------------------
# Batch-level judgment (the circuit breaker)
# ---------------------------------------------------------------------------
# Per-record judgment cannot catch a wrong premise. If a third of the file is
# escalating, the likely truth is not "this data is hard" but "this is the wrong
# export, or the target entity is wrong" - and the right response is one
# question, not two hundred tickets. An agent that floods the queue has failed
# just as surely as one that guesses.
CIRCUIT_BREAKER_RATE = 0.25
CIRCUIT_BREAKER_MIN_RECORDS = 8      # below this, rates are meaningless noise
CIRCUIT_BREAKER_ABSOLUTE = 40        # no human triages more than this in one sitting

# Mapping coverage is the other premise check: if almost nothing in the file
# maps to the target schema, the file is about something else entirely.
MIN_MAPPING_COVERAGE = 0.35

# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------
# 5xx and timeouts are the network's problem - retry them. 4xx is the target
# system stating a business fact ("this employee code already exists"), which
# retrying cannot fix and only a human can adjudicate.
PUSH_MAX_ATTEMPTS = 3
PUSH_BACKOFF_SECONDS = [0.5, 1.5, 3.0]
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def classify_mapping(
    top_score: float,
    runner_up_score: float,
    lexical_best: float = 1.0,
) -> Disposition:
    """Apply the confidence-and-margin rule to one column.

    Two different questions get asked in order, because they need different
    evidence. First: is this column in the schema at all? That is an absolute
    question, and lexical overlap answers it. Second: which field is it? That is
    a relative question among candidates, and the standardised semantic score
    answers it.
    """
    if lexical_best < LEXICAL_EVIDENCE_FLOOR and top_score < 0.70:
        return Disposition.IGNORED
    if top_score < MAPPING_IGNORE_MAX:
        return Disposition.IGNORED
    margin = top_score - runner_up_score
    if top_score >= MAPPING_AUTO_MIN and margin >= MAPPING_MARGIN_MIN:
        return Disposition.AUTO
    return Disposition.ESCALATED


def classify_enum_match(score: float) -> Disposition:
    if score >= ENUM_AUTO_MIN:
        return Disposition.AUTO
    if score >= ENUM_ESCALATE_MIN:
        return Disposition.ESCALATED
    return Disposition.ESCALATED


def date_convention_is_safe(anchor_count: int, agreement: float) -> bool:
    """True when unambiguous rows settle the convention for the whole column."""
    return anchor_count >= DATE_MIN_ANCHORS and agreement >= DATE_ANCHOR_AGREEMENT


def should_trip_breaker(
    escalated_records: int,
    total_records: int,
    total_escalations: int,
) -> tuple[bool, str]:
    """Batch-level go/no-go. Returns (tripped, human-readable reason)."""
    if total_escalations >= CIRCUIT_BREAKER_ABSOLUTE:
        return True, (
            f"{total_escalations} separate questions came out of this run. That is past "
            f"the point where reviewing them one by one is sensible - the inputs are "
            f"more likely wrong than the data."
        )
    if total_records < CIRCUIT_BREAKER_MIN_RECORDS:
        return False, ""
    rate = escalated_records / total_records
    if rate >= CIRCUIT_BREAKER_RATE:
        return True, (
            f"{escalated_records} of {total_records} records ({rate:.0%}) need a human "
            f"decision. Above {CIRCUIT_BREAKER_RATE:.0%} the usual cause is a wrong file "
            f"or a wrong target entity rather than messy data."
        )
    return False, ""


def is_retryable(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS

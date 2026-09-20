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

# One exception to the margin test, and only one: the column is *named* the
# field. A client whose column header is literally `work_email` has told us what
# it is more plainly than any score can, and no amount of semantic similarity
# from a rival field outweighs that.
#
# This was found by testing a deliberately clean file. `work_email` scored a
# perfect 1.00 literal match against the work_email field - and was escalated
# anyway, because `manager_email` scored 0.915. The reason is almost funny: the
# manager_email field's own description says "must match the work_email of
# another employee", so it embeds as nearly the same concept. The schema's
# cross-reference was sabotaging the mapping it referred to.
#
# The margin test still guards everything else. It is there to catch a column
# that resembles two fields; it was never meant to catch a column that *is* one.
EXACT_NAME_MATCH_IS_CONCLUSIVE = True

# Below this, the agent is not uncertain - it is confident there is no match.
# "ctc_annual" has no home in the target schema, and asking a human to confirm
# that would be noise. Dropped columns are reported, never queued.
MAPPING_IGNORE_MAX = 0.50

# A field with a declared format (PAN, UAN, IFSC, email, phone, bank account)
# can only be fed by a column whose values have that shape. When none of the
# sampled values match, the field is not a candidate at all, whatever the
# names or descriptions suggest - "Employee Number" reads like a phone number
# to an embedding model, but its values are three-digit integers and no phone
# has three digits. The penalty is large enough to push such a candidate below
# MAPPING_IGNORE_MAX on its own, because the alternative was a queue of thirty
# questions asking whether a marital-status flag is a PAN.
#
# Found on a real 311-row HRIS export: 35 of 64 columns were escalated, almost
# all of them analytics columns scoring 0.5-0.8 against a statutory ID field
# their values could never satisfy, and the batch breaker then declared genuine
# employee data "not employee data".
FORMAT_MISMATCH_PENALTY = 0.45

# The same reasoning for the two other things a column's *content* settles
# outright. A field the schema marks unique (employee_code, work_email) is one
# value per person, so a column with two distinct values across three hundred
# rows cannot be it - MarriedID is 0/1, not an employee code. And a vocabulary
# of words (gender, status) cannot be fed by a column of numbers, however
# closely "GenderID" resembles "gender" by name. Both use the format penalty:
# they are the same kind of certainty. The ratio is deliberately low - the
# sample data's employee-code column has real duplicates in it and still sits
# above 0.9 - so only a genuinely categorical column falls under it.
UNIQUE_FIELD_MIN_DISTINCT_RATIO = 0.5

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

# When a column maps to a field with a fixed vocabulary and *most of its values
# do not fit that vocabulary*, the likely fault is the mapping, not the values.
#
# This was found by running the agent against a real HR export, where a column
# of race categories scored 0.85 against `gender` and was applied. The system
# then did something worse than fail: it asked seven separate questions - "what
# does 'White' mean as a gender?" - blaming the data for a mistake it had made
# itself, and pointing the consultant at the wrong problem entirely.
#
# One column-level question ("is this really the gender column?") replaces all
# of them, and is the question that can actually be answered. Above this share
# of unrecognised values the mapping is contested rather than the values.
ENUM_VOCABULARY_MISMATCH = 0.5

# Below a handful of values a mismatch rate means nothing - a column with two
# distinct values, one of which is unrecognised, is at 50% by arithmetic rather
# than by evidence.
ENUM_MISMATCH_MIN_VALUES = 4

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

# One near-match is a question about two people. Two hundred near-matches, all
# between the same two files and all on the same basis, are one fact: the files
# are two exports of the same staff, keyed by different ID systems. Asking per
# pair would be the flood; deciding to merge on the agent's own authority would
# be the invisible error. So it is asked once, about the batch, with "review
# each pair" still on offer. Found on two versions of a real 311-row HRIS
# export, which produced 275 pair questions.
IDENTITY_FLOOD_MIN = 10
IDENTITY_FLOOD_RATE = 0.5           # of the rows in the smaller of the two files

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

# A required field that is empty on *almost every* record is not a per-record
# defect - it means no source column feeds that field at all. The two cases need
# opposite responses:
#
#   a handful of records missing an email  ->  per-record questions, correctly
#   every record missing an email          ->  one question about the field
#
# Found by running the agent against a real HR export with no email column
# anywhere: it produced 300 identical escalations, each asking a human to type
# one person's address. That is the "ask once per column, never once per row"
# rule broken in the one place the rule matters most. The circuit breaker caught
# the flood, but a breaker firing is not the same as asking the right question -
# the file was fine, the schema field simply had no source.
REQUIRED_FIELD_MISSING_RATE = 0.9
REQUIRED_FIELD_MISSING_MIN_RECORDS = 10   # below this, per-record is fine


def required_field_has_no_source(missing: int, total: int) -> bool:
    """True when a required field is absent structurally rather than by accident."""
    if total < REQUIRED_FIELD_MISSING_MIN_RECORDS:
        return False
    return (missing / total) >= REQUIRED_FIELD_MISSING_RATE

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

# The rate alone is not enough to stop a run. On a twenty-row file, four
# questions is 25% and also just four questions - trivially triageable, and
# "abort or continue" is a worse thing to be asked than the four real questions
# it hides. The breaker exists because *an agent that floods the queue has
# failed*; below this many questions there is no flood, whatever the ratio says.
#
# Found by testing small files: a 15-row file with four blocked records tripped
# the breaker and buried a duplicate, a rehire and two validation failures.
CIRCUIT_BREAKER_MIN_QUESTIONS = 12

# Mapping coverage is the other premise check: if almost nothing in the file
# maps to the target schema, the file is about something else entirely.
#
# Two measures, and the run stops only when *both* are low. Column coverage
# alone was wrong on a real 64-column HRIS export: 49 columns were engagement
# scores, survey results and demographic flags with no home in the schema, so
# only 23% "mapped" - and the breaker declared genuine employee data the wrong
# file. What actually separates a wrong file from a wide one is whether the
# fields the schema *requires* are there: that export had 8 of 10 (codes,
# names, dates, department, title, status); an anonymised analytics extract
# has 2; a brokerage statement has none.
MIN_MAPPING_COVERAGE = 0.35
MIN_REQUIRED_FIELDS_FOUND = 0.5

# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------
# 5xx and timeouts are the network's problem - retry them. 4xx is the target
# system stating a business fact ("this employee code already exists"), which
# retrying cannot fix and only a human can adjudicate.
PUSH_MAX_ATTEMPTS = 3
PUSH_BACKOFF_SECONDS = [0.5, 1.5, 3.0]
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

# One rejection is a question about one record. Forty rejections with the same
# message are one question about the batch - almost always "the target already
# holds these people" after a re-run or a partial earlier load - and raising a
# card per record is the flood the whole design exists to prevent. Below the
# minimum, a handful of individual cards is more useful than an abstract one.
PUSH_REJECTION_FLOOD_MIN = 5
PUSH_REJECTION_FLOOD_RATE = 0.5      # of the records attempted in this pass


def classify_mapping(
    top_score: float,
    runner_up_score: float,
    lexical_best: float = 1.0,
    exact_name_match: bool = False,
) -> Disposition:
    """Apply the confidence-and-margin rule to one column.

    Two different questions get asked in order, because they need different
    evidence. First: is this column in the schema at all? That is an absolute
    question, and lexical overlap answers it. Second: which field is it? That is
    a relative question among candidates, and the standardised semantic score
    answers it.

    `exact_name_match` short-circuits the second question. If the column is
    named exactly what the field is named, there is no second question to ask.
    """
    if lexical_best < LEXICAL_EVIDENCE_FLOOR and top_score < 0.70:
        return Disposition.IGNORED
    if top_score < MAPPING_IGNORE_MAX:
        return Disposition.IGNORED
    if exact_name_match and EXACT_NAME_MATCH_IS_CONCLUSIVE:
        return Disposition.AUTO
    margin = top_score - runner_up_score
    if top_score >= MAPPING_AUTO_MIN and margin >= MAPPING_MARGIN_MIN:
        return Disposition.AUTO
    return Disposition.ESCALATED


def names_match_exactly(column: str, field_name: str) -> bool:
    """Is this column named the field, allowing only cosmetic differences?

    Underscores, spaces, hyphens and case vary between systems and carry no
    meaning; anything beyond that is a different word and gets scored normally.
    """
    def flatten(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())

    return bool(column) and flatten(column) == flatten(field_name)


def mapping_is_contradicted_by_values(
    unmatched_values: int, total_values: int
) -> bool:
    """True when a column's values argue against the field it was mapped to.

    Deliberately about *distinct* values rather than rows: a single bad value
    repeated four hundred times is one unrecognised value, not four hundred
    pieces of evidence that the mapping is wrong.
    """
    if total_values < ENUM_MISMATCH_MIN_VALUES:
        return False
    return (unmatched_values / total_values) >= ENUM_VOCABULARY_MISMATCH


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
    # A high ratio over a short queue is not a flood - it is a short queue.
    if total_escalations < CIRCUIT_BREAKER_MIN_QUESTIONS:
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


def duplicates_are_a_flood(pairs: int, smaller_file_rows: int) -> bool:
    """True when cross-file near-matches should become one batch question."""
    if pairs < IDENTITY_FLOOD_MIN or smaller_file_rows == 0:
        return False
    return (pairs / smaller_file_rows) >= IDENTITY_FLOOD_RATE


def rejections_are_a_flood(rejected: int, attempted: int) -> bool:
    """True when identical rejections should become one batch question."""
    if rejected < PUSH_REJECTION_FLOOD_MIN or attempted == 0:
        return False
    return (rejected / attempted) >= PUSH_REJECTION_FLOOD_RATE


# ---------------------------------------------------------------------------
# Self-description
# ---------------------------------------------------------------------------
# The supervision UI renders the escalation boundary on screen, and it reads it
# from here rather than restating it in TypeScript. The point of keeping every
# threshold in one file is lost the moment a second copy exists that can drift
# from this one - a reviewer would then have to check which is true. So the
# numbers below are the module's own constants, not literals, and changing a
# threshold changes what the UI says about it in the same edit.


def describe() -> dict:
    """The boundary as data, for the UI and for anyone asking 'why 0.82?'."""
    return {
        "principle": (
            "Escalate when being wrong is silent and irreversible. "
            "Auto-fix when being wrong would be loud and cheap to undo."
        ),
        "tiers": [
            {
                "id": "auto",
                "label": "Applied",
                "meaning": "Deterministic, or the evidence leaves exactly one answer standing.",
            },
            {
                "id": "flagged",
                "label": "Applied and flagged",
                "meaning": (
                    "A defensible inference. Surfaced so it can be audited in seconds, "
                    "but not worth blocking a migration over."
                ),
            },
            {
                "id": "escalated",
                "label": "Blocked",
                "meaning": "The evidence genuinely supports more than one answer.",
            },
        ],
        "groups": [
            {
                "id": "mapping",
                "title": "Column mapping",
                "summary": (
                    "A mapping is applied only if it is both confident and unrivalled. "
                    "The margin test is the important half: 0.91 against work_email and "
                    "0.89 against personal_email is not a confident mapping, it is a coin "
                    "flip wearing a high score."
                ),
                "thresholds": [
                    {
                        "name": "Auto-apply above",
                        "key": "MAPPING_AUTO_MIN",
                        "value": MAPPING_AUTO_MIN,
                        "note": "Blended semantic and lexical score for the winning field.",
                    },
                    {
                        "name": "Required margin over runner-up",
                        "key": "MAPPING_MARGIN_MIN",
                        "value": MAPPING_MARGIN_MIN,
                        "note": (
                            "Below this the top two candidates are treated as a tie "
                            "and asked - unless the column is named exactly what the "
                            "field is named, which settles it outright."
                        ),
                    },
                    {
                        "name": "Drop below",
                        "key": "MAPPING_IGNORE_MAX",
                        "value": MAPPING_IGNORE_MAX,
                        "note": (
                            "Not uncertainty - confidence that there is no match. "
                            "'ctc_annual' has no home in an employee master, and asking "
                            "a human to confirm that would be noise."
                        ),
                    },
                    {
                        "name": "Content rules out a field",
                        "key": "FORMAT_MISMATCH_PENALTY",
                        "value": FORMAT_MISMATCH_PENALTY,
                        "note": (
                            "A column whose values never fit a field's declared format, "
                            "a categorical column offered as a unique identifier, or "
                            "numbers offered as a vocabulary of words: the name may "
                            "resemble the field, the content settles that it is not."
                        ),
                    },
                    {
                        "name": "Lexical evidence floor",
                        "key": "LEXICAL_EVIDENCE_FLOOR",
                        "value": LEXICAL_EVIDENCE_FLOOR,
                        "note": (
                            "Semantic similarity ranks candidates but cannot tell "
                            "'the best of these' from 'any of these'. A column with no "
                            "lexical foothold anywhere is dropped, not queued."
                        ),
                    },
                    {
                        "name": "Semantic / lexical blend",
                        "key": "EMBEDDING_WEIGHT",
                        "value": EMBEDDING_WEIGHT,
                        "note": (
                            f"{EMBEDDING_WEIGHT:.0%} embedding, {FUZZY_WEIGHT:.0%} string "
                            "similarity. Embeddings catch worker_category -> "
                            "employment_type; string matching catches 'DOB'."
                        ),
                    },
                ],
            },
            {
                "id": "dates",
                "title": "Date conventions",
                "summary": (
                    "03/04/2021 is unreadable alone, but a column is written by one "
                    "system in one convention, so unambiguous siblings settle the whole "
                    "column. Reading it wrongly is the archetypal silent error: nothing "
                    "downstream complains, and tenure and gratuity are quietly wrong for years."
                ),
                "thresholds": [
                    {
                        "name": "Unambiguous rows required",
                        "key": "DATE_MIN_ANCHORS",
                        "value": DATE_MIN_ANCHORS,
                        "note": "Values with a day above 12, which can only be read one way.",
                    },
                    {
                        "name": "Agreement between them",
                        "key": "DATE_ANCHOR_AGREEMENT",
                        "value": DATE_ANCHOR_AGREEMENT,
                        "note": "Guards against a column that is itself internally inconsistent.",
                    },
                ],
            },
            {
                "id": "values",
                "title": "Value vocabulary",
                "summary": (
                    "'engineering  ' to Engineering is normalisation. 'Human Resource' "
                    "to 'Human Resources' is a near-certain typo. 'Engg' looks obvious "
                    "to a human and scores like a coin flip - so it gets asked."
                ),
                "thresholds": [
                    {
                        "name": "Accept a match above",
                        "key": "ENUM_AUTO_MIN",
                        "value": ENUM_AUTO_MIN,
                        "note": "Similarity against the schema's permitted values, as a percentage.",
                    },
                    {
                        "name": "Ask between",
                        "key": "ENUM_ESCALATE_MIN",
                        "value": ENUM_ESCALATE_MIN,
                        "note": (
                            f"{ENUM_ESCALATE_MIN:.0f}-{ENUM_AUTO_MIN:.0f}% is the grey band "
                            "where the agent stops trusting itself."
                        ),
                    },
                    {
                        "name": "Values contradicting the mapping",
                        "key": "ENUM_VOCABULARY_MISMATCH",
                        "value": ENUM_VOCABULARY_MISMATCH,
                        "note": (
                            "If most of a column's distinct values are not in the "
                            "field's vocabulary, the mapping is contested rather "
                            "than the values. Found against a real export where a "
                            "race column scored 0.85 against gender: the agent "
                            "asked seven questions about the values instead of one "
                            "about the mapping it had got wrong."
                        ),
                    },
                    {
                        "name": "Known aliases encoded, not inferred",
                        "key": "SAFE_ALIASES",
                        "value": sum(len(v) for v in SAFE_ALIASES.values()),
                        "note": (
                            "Domain knowledge across "
                            f"{len(SAFE_ALIASES)} fields. No model needs to be asked "
                            "whether 'M' means Male in an HR export."
                        ),
                    },
                ],
            },
            {
                "id": "identity",
                "title": "Identity",
                "summary": (
                    "Merging two people is unrecoverable once payroll runs against it; "
                    "leaving a duplicate is visible and fixable. A rehire looks exactly "
                    "like a duplicate to any generic dedup routine, and merging one "
                    "destroys the service history gratuity is computed from - so the "
                    "agent never decides that case itself."
                ),
                "thresholds": [
                    {
                        "name": "Name similarity for a soft match",
                        "key": "IDENTITY_NAME_SIMILARITY",
                        "value": IDENTITY_NAME_SIMILARITY,
                        "note": "Still only a candidate; a unique identifier is what merges alone.",
                    },
                    {
                        "name": "Rehire gap",
                        "key": "REHIRE_GAP_DAYS",
                        "value": REHIRE_GAP_DAYS,
                        "note": "Non-overlapping service beyond this gap reads as a possible rehire.",
                    },
                ],
            },
            {
                "id": "validation",
                "title": "Validation",
                "summary": (
                    "One deterministic repair attempt, then ask. The first failure says "
                    "the value was messy; the second says the mess is not mechanical."
                ),
                "thresholds": [
                    {
                        "name": "Repair attempts before asking",
                        "key": "MAX_REPAIR_ATTEMPTS",
                        "value": MAX_REPAIR_ATTEMPTS,
                        "note": "Retrying further burns time on data that needs a decision.",
                    },
                    {
                        "name": "Required field absent this often",
                        "key": "REQUIRED_FIELD_MISSING_RATE",
                        "value": REQUIRED_FIELD_MISSING_RATE,
                        "note": (
                            "Above this, no source column feeds the field at all, so "
                            "it is one question about the field rather than one per "
                            "record. A real export with no email column produced 300 "
                            "identical questions before this existed."
                        ),
                    },
                ],
            },
            {
                "id": "batch",
                "title": "The circuit breaker",
                "summary": (
                    "Per-record judgment cannot catch a wrong premise. If a third of the "
                    "file is escalating, the likely truth is not 'this data is hard' but "
                    "'this is the wrong export' - and the right response is one question, "
                    "not two hundred tickets. An agent that floods the queue has failed "
                    "as surely as one that guesses."
                ),
                "thresholds": [
                    {
                        "name": "Trip above this escalation rate",
                        "key": "CIRCUIT_BREAKER_RATE",
                        "value": CIRCUIT_BREAKER_RATE,
                        "note": "Share of records needing a human decision.",
                    },
                    {
                        "name": "Or this many questions",
                        "key": "CIRCUIT_BREAKER_ABSOLUTE",
                        "value": CIRCUIT_BREAKER_ABSOLUTE,
                        "note": "No one triages more than this in one sitting.",
                    },
                    {
                        "name": "Minimum records for a rate to mean anything",
                        "key": "CIRCUIT_BREAKER_MIN_RECORDS",
                        "value": CIRCUIT_BREAKER_MIN_RECORDS,
                        "note": "Below this, a percentage is noise.",
                    },
                    {
                        "name": "Minimum questions before a rate can stop a run",
                        "key": "CIRCUIT_BREAKER_MIN_QUESTIONS",
                        "value": CIRCUIT_BREAKER_MIN_QUESTIONS,
                        "note": (
                            "A high ratio over a short queue is not a flood, it is a "
                            "short queue - and stopping hides answerable questions "
                            "behind 'abort or continue'."
                        ),
                    },
                    {
                        "name": "Minimum schema coverage",
                        "key": "MIN_MAPPING_COVERAGE",
                        "value": MIN_MAPPING_COVERAGE,
                        "note": "If almost nothing maps, the file is about something else entirely.",
                    },
                    {
                        "name": "Required fields found",
                        "key": "MIN_REQUIRED_FIELDS_FOUND",
                        "value": MIN_REQUIRED_FIELDS_FOUND,
                        "note": (
                            "Low column coverage alone is not a wrong file - a wide HRIS "
                            "export is mostly analytics columns. It stops only when the "
                            "schema's required fields are missing too."
                        ),
                    },
                ],
            },
            {
                "id": "integration",
                "title": "Pushing to the target",
                "summary": (
                    "5xx and timeouts are the network's problem, so they are retried. "
                    "4xx is the target system stating a business fact, which retrying "
                    "cannot fix and only a human can adjudicate."
                ),
                "thresholds": [
                    {
                        "name": "Attempts per record",
                        "key": "PUSH_MAX_ATTEMPTS",
                        "value": PUSH_MAX_ATTEMPTS,
                        "note": f"Backing off {', '.join(f'{s}s' for s in PUSH_BACKOFF_SECONDS)}.",
                    },
                    {
                        "name": "Retried status codes",
                        "key": "RETRYABLE_STATUS",
                        "value": len(RETRYABLE_STATUS),
                        "note": ", ".join(str(c) for c in sorted(RETRYABLE_STATUS)),
                    },
                    {
                        "name": "Rejections that become one question",
                        "key": "PUSH_REJECTION_FLOOD_MIN",
                        "value": PUSH_REJECTION_FLOOD_MIN,
                        "note": (
                            f"At least this many, and {PUSH_REJECTION_FLOOD_RATE:.0%} of the "
                            f"batch, refused with one message - usually a re-run into a "
                            f"target that already holds them - is asked once, not per record."
                        ),
                    },
                ],
            },
        ],
    }

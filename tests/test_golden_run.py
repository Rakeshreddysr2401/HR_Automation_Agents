"""The regression net for the whole escalation policy.

This asserts the *exact* set of questions the agent raises on the sample data.
Every defect in those files was planted to exercise one specific branch, so if a
threshold drifts or an agent changes its mind, this fails loudly and names what
changed.

If you change the sample data or a threshold deliberately, update this test on
purpose - do not adjust it until it passes.
"""

import pytest

from app.pipeline import run
from app.settings import ROOT
from tests.conftest import needs_embeddings

FILES = [
    str(ROOT / "data" / "legacy_hris_export.csv"),
    str(ROOT / "data" / "payroll_system.xlsx"),
]

# Each of these exists because a specific defect was planted for it.
EXPECTED_FIRST_PASS = {
    # two columns in one file both look like the work address
    "contest:legacy_hris_export.csv:work_email",
    # every value is day<=12 and month<=12, so nothing settles the column
    "date:payroll_system.xlsx:joining_dt",
    # resembles "Engineering" enough to suspect, too loosely to assume
    "enum:department:engg",
    # one PAN, two employee codes: rehire or duplicate, unknowable from the data
    "rehire:E0910|E1031",
    # same birthday and first name, related surnames, nothing unique tying them
    "identity:E1032|P2201",
    # malformed PAN that survives an automatic repair pass
    "record:E1010",
    # inactive with no exit date, in a file that has no exit-date column
    "record:E0910",
    # inactive with no exit date
    "record:E1034",
    # required fields the merge cannot supply while work_email is contested
    "record:E1023",
    "record:E1025",
}


@needs_embeddings
class TestFirstPass:
    @pytest.fixture(scope="class")
    def result(self):
        return run(FILES, "golden")

    def test_raises_exactly_the_planted_questions(self, result):
        assert {e.subject for e in result.escalations} == EXPECTED_FIRST_PASS

    def test_maps_almost_everything_without_asking(self, result):
        """The ratio is the point: it must not ask about everything."""
        asked = sum(1 for m in result.mappings if m.disposition.value == "escalated")
        assert len(result.mappings) == 35
        assert asked == 2, "only the two contested email columns should be queried"

    def test_drops_columns_that_belong_to_no_field_rather_than_queueing_them(self, result):
        ignored = {m.column for m in result.mappings if m.disposition.value == "ignored"}
        assert "ctc_annual" in ignored
        assert not any(e.subject.endswith("ctc_annual") for e in result.escalations)

    def test_infers_date_conventions_where_the_column_proves_it(self, result):
        inferred = [
            entry for entry in result.audit if entry.action == "infer_date_convention"
        ]
        assert len(inferred) == 2, "both legacy date columns have anchors"
        assert all(entry.disposition.value == "flagged" for entry in inferred), (
            "an inference should be surfaced, not applied silently"
        )

    def test_merges_only_exact_duplicates_on_its_own(self, result):
        merges = [e for e in result.audit if e.action == "merge_duplicate"]
        assert merges, "the copy-pasted rows should merge without asking"

    def test_does_not_trip_the_circuit_breaker_on_good_data(self, result):
        assert result.breaker is None

    def test_defers_hierarchy_checks_while_emails_are_unresolved(self, result):
        """Resolving managers against an incomplete set would invent orphans."""
        deferred = [e for e in result.audit if e.action == "defer_hierarchy_check"]
        assert deferred
        assert not any(e.type.value.startswith("hierarchy") for e in result.escalations)


@needs_embeddings
class TestAnswersCascade:
    def test_one_answer_reconciles_the_files(self):
        """Confirming the work email column is not a one-field change.

        It lets the identity resolver match the two files against each other,
        which merges records and resolves validation failures whose missing
        fields the merge supplies. This is why answers are re-run through the
        pipeline rather than patched into its output.
        """
        before = run(FILES, "cascade_before")
        after = run(
            FILES,
            "cascade_after",
            decisions={"contest:legacy_hris_export.csv:work_email": "Official Email"},
        )

        assert len(after.records) < len(before.records), "the two files should reconcile"
        assert len(after.records) == 42

        resolved_by_merge = {"record:E1023", "record:E1025"}
        still_open = {e.subject for e in after.escalations}
        assert not (resolved_by_merge & still_open), (
            "these failed only because the merge had not yet supplied their fields"
        )

    def test_hierarchy_problems_surface_once_emails_are_known(self):
        after = run(
            FILES,
            "cascade_hierarchy",
            decisions={
                "contest:legacy_hris_export.csv:work_email": "Official Email",
                "map:legacy_hris_export.csv:Mail ID": "personal_email",
            },
        )
        subjects = {e.subject for e in after.escalations}
        assert "manager:former.manager@novatech.in" in subjects, "orphan manager"
        assert "cycle:E1005|E1013" in subjects, "reporting loop"

    def test_answering_everything_drains_the_queue(self):
        decisions = {
            "contest:legacy_hris_export.csv:work_email": "Official Email",
            "map:legacy_hris_export.csv:Mail ID": "personal_email",
            "date:payroll_system.xlsx:joining_dt": "DMY",
            "enum:department:engg": "Engineering",
            "rehire:E0910|E1031": "separate",
            "identity:E1032|P2201": "merge:E1032",
            "manager:former.manager@novatech.in": "clear",
            "cycle:E1005|E1013": "cycle-clear:E1013",
            "cycle-clear:E1013": True,
            "record:E1010": {"action": "edit", "fields": {"pan": "ABCDE1234F"}},
            "record:E0910": {"action": "edit", "fields": {"date_of_exit": "2019-06-30"}},
            "record:E1034": {"action": "edit", "fields": {"date_of_exit": "2024-03-31"}},
        }
        result = run(FILES, "drained", decisions=decisions)
        assert result.escalations == []
        assert len(result.records) == 41
        assert all(record.ready for record in result.records)


@needs_embeddings
class TestWrongFile:
    def test_one_question_rather_than_a_flood(self):
        """An asset inventory is not employee data, and saying so once is the
        useful response - not a question per column."""
        result = run([str(ROOT / "data" / "broken_export.csv")], "wrong_file")
        assert result.breaker is not None
        assert len(result.escalations) == 1
        assert result.escalations[0].type.value == "batch_anomaly"


class TestDegradedWithoutModels:
    def test_it_still_completes_and_errs_toward_asking(self, no_models):
        """With no embeddings, scores spread less and more columns fall below the
        bar. The run must still finish - failing toward asking is correct."""
        result = run(FILES, "degraded")
        asked = sum(1 for m in result.mappings if m.disposition.value == "escalated")
        assert result.records, "a migration must still produce records"
        assert asked >= 2, "without semantic scoring it should ask at least as much"

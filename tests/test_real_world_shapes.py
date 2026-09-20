"""Shapes found by running the agent against real public HR exports.

The bundled sample data is deliberately defective, but its defects are the ones
we thought of. These are the ones real files actually contain, found by pointing
the agent at two public datasets (the Kaggle "Human Resources Data Set", v9 and
v14, 311 and 310 rows of names, DOBs, hire dates and manager names) and at the
IBM HR attrition set.

Each test below corresponds to something that was silently wrong. They are kept
as unit tests over the *shapes* rather than as fixtures of those files, so the
suite stays hermetic and the repo stays small — but the shapes are verbatim.
"""

from __future__ import annotations

import pytest

from app import policy
from app.agents import cleanser
from app.agents.cleanser import _name_order_audit, _split_name
from app.models import Disposition


class TestSurnameFirstNames:
    """`"Adinolfi, Wilson  K"` — the convention every payroll export uses.

    This was silently inverting every name in the file: `first_name` came out as
    `"Adinolfi,"` (comma included) and `last_name` as `"Wilson K"`. Both fields
    are non-empty strings, so every format check passed and nothing downstream
    complained. Exactly the class of error the escalation policy exists to
    catch — except it needed fixing, not asking about, because a comma settles
    the convention outright.
    """

    @pytest.mark.parametrize(
        "raw,first,last",
        [
            # Verbatim from HRDataset_v14, including the double space.
            ("Adinolfi, Wilson  K", "Wilson K", "Adinolfi"),
            ("Brown, Mia", "Mia", "Brown"),
            ("LeBlanc, Brandon  R", "Brandon R", "LeBlanc"),
            # A particle-bearing surname must stay whole.
            ("van der Berg, Jan", "Jan", "van der Berg"),
            # A suffix belongs with the given names when the comma has spoken.
            ("Smith, John Jr.", "John Jr.", "Smith"),
        ],
    )
    def test_comma_means_surname_first(self, raw, first, last):
        assert _split_name(raw) == (first, last)

    @pytest.mark.parametrize(
        "raw,first,last",
        [
            ("Wilson Adinolfi", "Wilson", "Adinolfi"),
            # A middle name belongs with the given names, not the surname. This
            # was the second silent bug: "Jane Watson" as a surname.
            ("Mary Jane Watson", "Mary Jane", "Watson"),
            ("Gabriel Garcia Marquez", "Gabriel Garcia", "Marquez"),
            ("Jan van der Berg", "Jan", "van der Berg"),
            ("John Smith Jr", "John", "Smith Jr"),
        ],
    )
    def test_without_a_comma_the_surname_is_last(self, raw, first, last):
        assert _split_name(raw) == (first, last)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("", ("", "")),
            ("   ", ("", "")),
            # A mononym is a given name: last_name is required, and inventing a
            # surname would be worse than leaving it empty for the validator.
            ("Madonna", ("Madonna", "")),
            # A trailing comma and nothing after it is just a surname.
            ("Adinolfi,", ("", "Adinolfi")),
        ],
    )
    def test_degenerate_values_do_not_fabricate(self, raw, expected):
        assert _split_name(raw) == expected

    def test_a_comma_column_is_recorded_as_settled(self):
        entry = _name_order_audit(
            "run", "hr.csv", "Employee_Name", ["Brown, Mia", "Adinolfi, Wilson  K"]
        )
        assert entry is not None
        assert entry.after == "surname first"
        # AUTO, because the comma is unambiguous — no HR system writes
        # "First, Last".
        assert entry.disposition is Disposition.AUTO

    def test_a_comma_free_column_is_recorded_as_an_assumption(self):
        entry = _name_order_audit(
            "run", "hr.csv", "full_name", ["Wilson Adinolfi", "Mary Jane Watson"]
        )
        assert entry is not None
        assert entry.after == "given name first"
        # FLAGGED, not AUTO: right for the overwhelming majority of exports, but
        # wrong for a compound surname or a family-name-first culture, and
        # nothing in a name string alone can settle which applies.
        assert entry.disposition is Disposition.FLAGGED

    def test_an_empty_column_records_nothing(self):
        assert _name_order_audit("run", "hr.csv", "full_name", ["", "   "]) is None


class TestValuesContradictingTheMapping:
    """A column of race categories scored 0.85 against `gender` and was applied.

    The system then did something worse than fail: it asked seven separate
    questions — *"what does 'White' mean as a gender?"* — blaming the data for
    a mistake it had made itself, and pointing the consultant at a question
    nobody can answer.
    """

    def test_the_threshold_needs_enough_distinct_values_to_mean_anything(self):
        # A column with three values, all unrecognised, is at 100% by
        # arithmetic rather than by evidence.
        assert not policy.mapping_is_contradicted_by_values(3, 3)
        assert policy.mapping_is_contradicted_by_values(4, 4)

    def test_both_sides_of_the_mismatch_threshold(self):
        assert policy.mapping_is_contradicted_by_values(2, 4)       # 50%, at it
        assert not policy.mapping_is_contradicted_by_values(1, 4)   # 25%, under
        assert policy.mapping_is_contradicted_by_values(7, 8)

    def test_one_mapping_question_replaces_the_value_questions(self, monkeypatch):
        from app.models import ColumnMapping
        from app.schema import get_schema

        schema = get_schema()
        frame = _frame(
            "RaceDesc",
            [
                "White",
                "Black or African American",
                "Asian",
                "Two or more races",
                "Hispanic",
                "American Indian or Alaska Native",
            ],
        )
        mapping = ColumnMapping(
            "hr.csv", "RaceDesc", "gender", Disposition.AUTO, 0.85, 0.15, "scored"
        )
        result = cleanser.clean({"hr.csv": frame}, [mapping], schema, "run", {}, lambda _: None)

        assert len(result.escalations) == 1
        escalation = result.escalations[0]
        assert escalation.type.value == "column_mapping"
        assert "RaceDesc" in escalation.title
        # Keyed on the mapping so the answer replays like any other mapping
        # decision, and is remembered.
        assert escalation.subject == "map:hr.csv:RaceDesc"
        assert escalation.evidence["vocabulary_mismatch"] is True
        assert escalation.evidence["unmatched_count"] == 6

    def test_the_field_is_held_pending_rather_than_reported_empty(self):
        from app.models import ColumnMapping
        from app.schema import get_schema

        frame = _frame("RaceDesc", ["White", "Asian", "Hispanic", "Two or more races"])
        mapping = ColumnMapping(
            "hr.csv", "RaceDesc", "gender", Disposition.AUTO, 0.85, 0.15, "scored"
        )
        result = cleanser.clean(
            {"hr.csv": frame}, [mapping], get_schema(), "run", {}, lambda _: None
        )
        # Otherwise the validator would report a missing required field on every
        # record, which is the same question in a different shape.
        assert "gender" in result.blocked_fields.get("hr.csv", set())

    def test_a_human_confirmation_is_not_re_asked(self):
        """The loop this would otherwise cause.

        The mapping is re-derived on every pass, so if the check ignored the
        consultant's answer it would raise the identical question every round
        until the round limit — the precise failure the supervisor exists to
        prevent, reintroduced one layer down.
        """
        from app.models import ColumnMapping
        from app.schema import get_schema

        frame = _frame("RaceDesc", ["White", "Asian", "Hispanic", "Two or more races"])
        mapping = ColumnMapping(
            "hr.csv", "RaceDesc", "gender", Disposition.AUTO, 1.0, 1.0, "x",
            provenance="human",
        )
        result = cleanser.clean(
            {"hr.csv": frame},
            [mapping],
            get_schema(),
            "run",
            {"map:hr.csv:RaceDesc": "gender"},
            lambda _: None,
        )
        kinds = {e.type.value for e in result.escalations}
        assert "column_mapping" not in kinds
        # The values become the question instead, which is what the option the
        # consultant chose promised them.
        assert kinds == {"enum_value"}

    def test_a_legitimate_enum_column_is_untouched(self):
        """The check must not fire on a column that simply needs aliasing."""
        from app.models import ColumnMapping
        from app.schema import get_schema

        # Verbatim from HRDataset_v14: a trailing space, and abbreviations the
        # safe-alias table already knows.
        frame = _frame("Sex", ["M ", "F", "M", "F"])
        mapping = ColumnMapping(
            "hr.csv", "Sex", "gender", Disposition.AUTO, 0.95, 0.3, "scored"
        )
        result = cleanser.clean(
            {"hr.csv": frame}, [mapping], get_schema(), "run", {}, lambda _: None
        )
        assert result.escalations == []
        assert {row["gender"] for row in result.rows} == {"Male", "Female"}


class TestRequiredFieldWithNoSource:
    """Neither public dataset has an email column, and `work_email` is required.

    That produced **300 identical escalations** - one per employee, each asking a
    human to type one address - which is the "ask once per column or per distinct
    value, never once per row" rule broken in the one place it matters most. The
    circuit breaker caught the flood, but a breaker firing is not the same as
    asking the right question: the file was fine, the schema field simply had no
    source in it.
    """

    def test_both_sides_of_the_threshold(self):
        assert policy.required_field_has_no_source(300, 300)
        assert policy.required_field_has_no_source(270, 300)      # 90%, at it
        assert not policy.required_field_has_no_source(269, 300)  # just under
        assert not policy.required_field_has_no_source(5, 300)
        # Below the record floor, per-record questions are the right shape.
        assert not policy.required_field_has_no_source(9, 9)

    def test_one_field_question_replaces_one_per_record(self):
        records = _records(300)
        escalations, _ = _validate(records, {})
        assert len(escalations) == 1
        escalation = escalations[0]
        assert escalation.subject == "field:work_email"
        assert escalation.evidence["structural_gap"] is True
        assert escalation.evidence["missing_records"] == 300
        # It names every record it stands for, so one question blocks them all.
        assert escalation.affected_count == 300

    def test_it_is_field_level_so_the_breaker_does_not_count_it_per_record(self):
        """The false positive this type exists to prevent.

        Typed as a record-level failure, one question naming 300 records read as
        "100% of records need a human" and tripped the circuit breaker - hiding
        a perfectly answerable question behind "abort or continue".
        """
        from app import supervisor
        from app.models import EscalationType

        escalations, _ = _validate(_records(300), {})
        assert escalations[0].type is EscalationType.FIELD_UNSOURCED
        assert EscalationType.FIELD_UNSOURCED in supervisor.COLUMN_LEVEL

        records = _records(300)
        assert supervisor.evaluate_batch(escalations, records, [], "run") is None

    def test_a_few_records_missing_it_still_ask_per_record(self):
        """The opposite case must keep working.

        Three people with no email is per-record dirt and belongs in three
        per-record questions; three hundred is a structural gap.
        """
        records = _records(300, missing=3)
        escalations, _ = _validate(records, {})
        assert len(escalations) == 3
        assert all(e.subject.startswith("record:") for e in escalations)

    def test_answering_not_required_loads_the_records(self):
        records = _records(300)
        escalations, audit = _validate(records, {"field:work_email": "not_required"})
        assert escalations == []
        assert all(not r.errors for r in records)
        assert any(a.action == "relax_required_field" for a in audit)

    def test_answering_skip_marks_them_skipped(self):
        records = _records(300)
        escalations, audit = _validate(records, {"field:work_email": "skip_records"})
        assert escalations == []
        assert all(r.push_status == "skipped" for r in records)
        assert any(a.action == "skip_records_missing_field" for a in audit)

    def test_answering_remap_deliberately_leaves_it_open(self):
        """"It is in a column you did not recognise" is not an answer to this
        question - it is a decision to answer a different one, so this stays."""
        escalations, _ = _validate(_records(300), {"field:work_email": "remap"})
        assert len(escalations) == 1
        assert escalations[0].subject == "field:work_email"

    def test_a_field_pending_a_mapping_question_is_not_asked_about_twice(self):
        """The queue already holds this in another shape."""
        escalations, _ = _validate(_records(300), {}, pending={"work_email"})
        assert escalations == []


def _records(count: int, missing: int | None = None):
    """Records complete except for `work_email`, which `missing` of them lack."""
    from app.models import TargetRecord

    absent = count if missing is None else missing
    return [
        TargetRecord(
            key=f"E{i}",
            fields={
                "employee_code": f"E{i}",
                "first_name": "Mia",
                "last_name": "Brown",
                "date_of_birth": "1987-11-24",
                "date_of_joining": "2008-10-27",
                "department": "Engineering",
                "designation": "Analyst",
                "employment_type": "Permanent",
                "status": "Active",
                **({} if i < absent else {"work_email": f"m{i}@example.com"}),
            },
            sources=[f"hr.csv#{i}"],
        )
        for i in range(count)
    ]


def _validate(records, decisions, pending=None):
    from app.agents import validator
    from app.schema import get_schema

    return validator.validate(
        records,
        get_schema(),
        "run",
        pending_fields=pending or set(),
        pending_per_record={},
        decisions=decisions,
        emit=lambda _: None,
    )


class TestReconcilingFilesWithDifferentIdentifiers:
    """Two files, two identifier schemes, one set of people.

    Found while building the test kit: a legacy export keyed by work email and a
    payroll export keyed by employee code produced **thirty people from thirty
    rows** — zero merges — even though twelve employee codes matched exactly.

    The resolver grouped each row under a single preferred identifier (email if
    present, otherwise code), so a row carrying only a code could never meet a
    row carrying an email. It is the central scenario of the whole exercise, and
    it silently did nothing.
    """

    def test_rows_join_across_different_identifiers(self):
        rows = [
            # Same person: one half has the email, the other the code.
            {"_source": "hris.csv#2", "employee_code": "E1", "work_email": "a@x.com",
             "first_name": "Mia", "last_name": "Brown"},
            {"_source": "pay.csv#2", "employee_code": "E1", "pan": "ABCDE1234F"},
        ]
        records = _resolve(rows)
        assert len(records) == 1
        assert len(records[0].sources) == 2
        # The merge takes the union of what each half knew.
        assert records[0].fields["work_email"] == "a@x.com"
        assert records[0].fields["pan"] == "ABCDE1234F"

    def test_the_join_is_transitive(self):
        """Only a row carrying both identifiers can prove A and B are one person."""
        rows = [
            {"_source": "a.csv#2", "work_email": "a@x.com", "first_name": "Mia"},
            {"_source": "b.csv#2", "employee_code": "E1", "last_name": "Brown"},
            {"_source": "c.csv#2", "work_email": "a@x.com", "employee_code": "E1"},
        ]
        records = _resolve(rows)
        assert len(records) == 1
        assert len(records[0].sources) == 3

    def test_pan_never_joins_rows(self):
        """The rehire, and the worst thing this module could do.

        PAN is `identity: strong` and identifies a human nationally — but one
        human can hold two employment records, which is exactly what a rehire
        is. Merging on it would silently combine the 2016-2019 stint with the
        2022 one and destroy the service history gratuity is computed from.
        """
        rows = [
            {"_source": "a.csv#2", "employee_code": "E1", "pan": "ABCDE1234F",
             "first_name": "Rakesh", "last_name": "Reddy",
             "date_of_joining": "2016-04-01", "date_of_exit": "2019-03-31"},
            {"_source": "a.csv#9", "employee_code": "E2", "pan": "ABCDE1234F",
             "first_name": "Rakesh", "last_name": "Reddy",
             "date_of_joining": "2022-07-01"},
        ]
        records = _resolve(rows)
        assert len(records) == 2, "a shared PAN must not merge two employment records"

    def test_a_shared_pan_is_asked_about_instead(self):
        rows = [
            {"_source": "a.csv#2", "employee_code": "E1", "pan": "ABCDE1234F",
             "first_name": "Rakesh", "last_name": "Reddy",
             "date_of_joining": "2016-04-01", "date_of_exit": "2019-03-31"},
            {"_source": "a.csv#9", "employee_code": "E2", "pan": "ABCDE1234F",
             "first_name": "Rakesh", "last_name": "Reddy",
             "date_of_joining": "2022-07-01"},
        ]
        _, escalations, _ = _resolve_full(rows)
        assert any(e.type.value == "rehire_suspected" for e in escalations)

    def test_unrelated_rows_stay_separate(self):
        rows = [
            {"_source": "a.csv#2", "employee_code": "E1", "work_email": "a@x.com"},
            {"_source": "a.csv#3", "employee_code": "E2", "work_email": "b@x.com"},
        ]
        assert len(_resolve(rows)) == 2

    def test_a_row_with_no_identifier_stands_alone(self):
        rows = [
            {"_source": "a.csv#2", "first_name": "Mia"},
            {"_source": "a.csv#3", "first_name": "Wilson"},
        ]
        assert len(_resolve(rows)) == 2

    def test_only_employment_record_identifiers_are_used(self):
        from app.agents.identity import _record_identifiers
        from app.schema import get_schema

        assert _record_identifiers(get_schema()) == ["employee_code", "work_email"]


def _resolve(rows):
    return _resolve_full(rows)[0]


def _resolve_full(rows):
    from app.agents import identity
    from app.schema import get_schema

    return identity.resolve(rows, get_schema(), "run", {}, lambda _: None)


class TestExactColumnNames:
    """A column named exactly what the field is named must not be a question.

    Found by testing a deliberately clean file: `work_email` scored a perfect
    1.00 literal match and was escalated anyway, because `manager_email` scored
    0.915 — its schema description says "must match the work_email of another
    employee", so it embeds as nearly the same concept. The schema's own
    cross-reference was sabotaging the mapping it referred to.
    """

    def test_cosmetic_differences_still_count_as_exact(self):
        for column in ("work_email", "Work Email", "WORK-EMAIL", "workemail"):
            assert policy.names_match_exactly(column, "work_email"), column

    def test_a_different_word_does_not(self):
        for column in ("work_emails", "personal_email", "email", ""):
            assert not policy.names_match_exactly(column, "work_email"), column

    def test_an_exact_match_beats_a_failing_margin(self):
        # 1.00 against 0.915 is a margin of 0.085, well under MAPPING_MARGIN_MIN.
        assert policy.classify_mapping(1.0, 0.915, 1.0) is Disposition.ESCALATED
        assert (
            policy.classify_mapping(1.0, 0.915, 1.0, exact_name_match=True)
            is Disposition.AUTO
        )

    def test_it_does_not_rescue_a_column_with_no_business_being_mapped(self):
        """The floor still applies: exactness settles *which* field, not whether."""
        assert (
            policy.classify_mapping(0.2, 0.1, 0.1, exact_name_match=True)
            is Disposition.IGNORED
        )


class TestBreakerNeedsARealQueue:
    """A high ratio over a short queue is a short queue, not a flood.

    A fifteen-row file with four blocked records is 27% and also just four
    questions. Stopping there buried a duplicate, a rehire and two validation
    failures behind "abort or continue".
    """

    def test_a_short_queue_does_not_stop_the_run(self):
        tripped, _ = policy.should_trip_breaker(4, 15, 4)
        assert not tripped

    def test_a_long_queue_at_the_same_ratio_does(self):
        tripped, _ = policy.should_trip_breaker(4, 15, 14)
        assert tripped

    def test_the_absolute_cap_still_applies_regardless_of_ratio(self):
        tripped, _ = policy.should_trip_breaker(1, 1000, policy.CIRCUIT_BREAKER_ABSOLUTE)
        assert tripped


class TestOtherRealWorldShapes:
    """Things real files do that turned out to be handled already.

    Kept as regression tests: each one is cheap to break and expensive to
    notice, because all four fail silently rather than loudly.
    """

    def test_a_utf8_bom_does_not_become_part_of_the_first_column_name(self, tmp_path):
        # Both public datasets ship with a BOM, so the first column would
        # otherwise be named "﻿Employee_Name" and match nothing.
        path = tmp_path / "bom.csv"
        path.write_bytes(b"\xef\xbb\xbfEmployee_Name,EmpID\n\"Brown, Mia\",10026\n")
        from app.agents import profiler

        frame = next(iter(profiler.load_sources([str(path)]).values()))
        assert list(frame.columns) == ["Employee_Name", "EmpID"]

    def test_a_leading_zero_postcode_survives_loading(self, tmp_path):
        # Read as a number, "01960" becomes 1960 — a silent corruption of every
        # postcode in the north-east United States.
        path = tmp_path / "zip.csv"
        path.write_text("EmpID,Zip\n10026,01960\n10084,02148\n")
        from app.agents import profiler

        frame = next(iter(profiler.load_sources([str(path)]).values()))
        assert list(frame["Zip"]) == ["01960", "02148"]

    def test_a_two_digit_year_column_is_read_from_its_own_anchors(self):
        from app import dates

        # Verbatim DOB values from HRDataset_v14.
        plan = dates.analyse_column(
            ["07/10/83", "05/05/75", "09/19/88", "09/27/88", "01/16/84", "11/24/87"]
        )
        assert plan.convention == dates.MDY
        assert plan.anchors >= policy.DATE_MIN_ANCHORS
        assert plan.agreement >= policy.DATE_ANCHOR_AGREEMENT

    def test_heavy_trailing_whitespace_is_normalised(self):
        from app.schema import get_schema

        department = get_schema().field("department")
        assert cleanser.normalise("Production       ", department) == "Production"


def _frame(column: str, values: list[str]):
    """A one-column frame of strings, loaded the way the profiler loads files."""
    import pandas as pd

    return pd.DataFrame({column: values}, dtype=str)


# ---------------------------------------------------------------------------
# Found on the second pass over the same two exports, once names were right.
# ---------------------------------------------------------------------------


def _profile(column, samples, **kw):
    from app.models import ColumnProfile

    base = dict(
        source_file="hr.csv", column=column, row_count=len(samples), non_null=len(samples),
        cardinality=len(set(samples)), inferred_type="string", samples=samples[:5],
        raw_samples=samples[:8],
    )
    base.update(kw)
    return ColumnProfile(**base)


class TestContentRulesOutAField:
    """35 of 64 columns were escalated, almost all of them analytics columns
    scoring 0.5-0.8 against a field their values could never satisfy - and the
    batch breaker then declared genuine employee data "not employee data"."""

    def setup_method(self):
        from app.agents.mapper import _structural_adjustment
        from app.schema import get_schema

        self.adjust = _structural_adjustment
        self.schema = get_schema()

    def test_three_digit_integers_are_not_a_phone_number(self):
        # "Employee Number" embeds close to "phone number"; its values decide.
        p = _profile("EmpID", ["10026", "10084", "10196"], inferred_type="number")
        assert self.adjust(p, self.schema.field("phone")) == -policy.FORMAT_MISMATCH_PENALTY

    def test_a_flag_column_is_not_an_employee_code(self):
        # MarriedID: two distinct values across three hundred rows.
        p = _profile("MarriedID", ["0", "1"] * 150, inferred_type="number", cardinality=2, non_null=300)
        assert self.adjust(p, self.schema.field("employee_code")) == -policy.FORMAT_MISMATCH_PENALTY

    def test_a_real_code_column_with_a_few_duplicates_still_qualifies(self):
        p = _profile("EmpID", [f"E{i}" for i in range(30)] + ["E1", "E2"], inferred_type="id", cardinality=30, non_null=32)
        assert self.adjust(p, self.schema.field("employee_code")) >= 0

    def test_numbers_are_not_a_vocabulary_of_words(self):
        p = _profile("GenderID", ["0", "1", "1"], inferred_type="number")
        assert self.adjust(p, self.schema.field("gender")) == -policy.FORMAT_MISMATCH_PENALTY

    def test_values_already_in_the_vocabulary_agree_with_the_field(self):
        # Verbatim from HRDataset_v14, trailing space included.
        p = _profile("Sex", ["M ", "F", "M "])
        assert self.adjust(p, self.schema.field("gender")) > 0

    def test_a_salary_is_not_a_bank_account(self):
        p = _profile("Salary", ["62506", "104437", "64955"], inferred_type="number")
        assert self.adjust(p, self.schema.field("bank_account")) == -policy.FORMAT_MISMATCH_PENALTY


class TestWrongFileNeedsBothSignalsLow:
    """A 64-column HRIS export is mostly analytics columns. Low column coverage
    alone is not a wrong file; missing the required fields as well is."""

    def _mappings(self, auto_fields, ignored):
        from app.models import ColumnMapping

        out = [
            ColumnMapping("hr.csv", f"c_{f}", f, Disposition.AUTO, 0.9, 0.3, "")
            for f in auto_fields
        ]
        out += [
            ColumnMapping("hr.csv", f"x{i}", None, Disposition.IGNORED, 0.3, 0.1, "")
            for i in range(ignored)
        ]
        return out

    def test_a_wide_export_with_the_required_fields_is_not_a_wrong_file(self):
        from app import supervisor

        mappings = self._mappings(
            ["employee_code", "first_name", "last_name", "date_of_birth", "date_of_joining",
             "department", "designation", "status"],
            ignored=50,
        )
        assert supervisor.evaluate_batch([], [], mappings, "run") is None

    def test_an_analytics_extract_with_no_names_or_dates_is(self):
        from app import supervisor

        mappings = self._mappings(["department", "gender"], ignored=33)
        breaker = supervisor.evaluate_batch([], [], mappings, "run")
        assert breaker is not None and breaker.subject == "batch:coverage"
        assert breaker.evidence["required_fields_found"] == 1


class TestTwoExportsOfTheSamePeople:
    """v9 and v14 describe the same 300 staff under different ID systems. Every
    pair matched on full name and date of birth, and the resolver asked 275
    times. That is one fact about the two files, not 275 questions."""

    def _rows(self, n, file, code_prefix):
        return [
            {
                "employee_code": f"{code_prefix}{i}", "first_name": f"Name{i}", "last_name": "Surname",
                "date_of_birth": f"198{i % 10}-01-0{1 + i % 9}", "_source": f"{file}#{i + 2}",
            }
            for i in range(n)
        ]

    def test_it_asks_once_about_the_files(self):
        from app.agents import identity
        from app.schema import get_schema

        rows = self._rows(20, "a.csv", "A") + self._rows(20, "b.csv", "B")
        records, escalations, _ = identity.resolve(rows, get_schema(), "run", {})
        assert len(records) == 40
        assert [e.type.value for e in escalations] == ["batch_anomaly"]
        assert escalations[0].evidence["pair_count"] == 20
        assert escalations[0].subject == "identity-batch:a.csv|b.csv"

    def test_merge_all_carries_out_every_merge(self):
        from app.agents import identity
        from app.schema import get_schema

        rows = self._rows(20, "a.csv", "A") + self._rows(20, "b.csv", "B")
        records, escalations, audit = identity.resolve(
            rows, get_schema(), "run", {"identity-batch:a.csv|b.csv": "merge_all"}
        )
        assert escalations == []
        assert len(records) == 20 and all(len(r.sources) == 2 for r in records)
        assert any(a.action == "resolve_duplicate_batch" for a in audit)

    def test_review_keeps_the_individual_questions(self):
        from app.agents import identity
        from app.schema import get_schema

        rows = self._rows(20, "a.csv", "A") + self._rows(20, "b.csv", "B")
        _, escalations, _ = identity.resolve(
            rows, get_schema(), "run", {"identity-batch:a.csv|b.csv": "review"}
        )
        assert len(escalations) == 20

    def test_a_few_pairs_stay_individual(self):
        from app.agents import identity
        from app.schema import get_schema

        rows = self._rows(3, "a.csv", "A") + self._rows(3, "b.csv", "B") + self._rows(30, "c.csv", "C")[3:]
        _, escalations, _ = identity.resolve(rows, get_schema(), "run", {})
        assert {e.type.value for e in escalations} == {"duplicate_suspected"}


class TestOneCardPerColumnName:
    def test_the_same_column_in_two_files_is_one_question(self):
        from app import supervisor
        from app.models import Escalation, EscalationType

        def card(file):
            return Escalation(
                run_id="run", type=EscalationType.COLUMN_MAPPING, subject=f"map:{file}:State",
                title="Which field is 'State'?", question="...", evidence={"source_file": file, "column": "State"},
                options=[], affected_records=[],
            )

        kept = supervisor.one_card_per_column_name([card("a.csv"), card("b.csv")])
        assert len(kept) == 1
        assert kept[0].evidence["also_in"] == ["b.csv"]

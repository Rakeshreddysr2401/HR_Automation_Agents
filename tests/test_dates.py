"""Reading the column, not the value."""

from datetime import date

from app import dates


class TestSingleValues:
    def test_a_day_above_twelve_settles_itself(self):
        reading = dates.read_value("15/03/2021")
        assert reading.parsed == date(2021, 3, 15) and reading.implies == dates.DMY

    def test_a_middle_component_above_twelve_settles_the_other_way(self):
        reading = dates.read_value("03/15/2021")
        assert reading.parsed == date(2021, 3, 15) and reading.implies == dates.MDY

    def test_both_components_under_twelve_is_unreadable_alone(self):
        reading = dates.read_value("03/04/2021")
        assert reading.ambiguous and reading.parsed is None

    def test_iso_is_never_ambiguous(self):
        assert dates.read_value("2021-03-15").parsed == date(2021, 3, 15)

    def test_a_month_name_removes_all_doubt(self):
        assert dates.read_value("15 Mar 2021").parsed == date(2021, 3, 15)
        assert dates.read_value("Mar 15, 2021").parsed == date(2021, 3, 15)

    def test_two_digit_years_resolve_to_the_sensible_century(self):
        """HR dates are births and joinings, never futures."""
        assert dates.read_value("23/07/95").parsed == date(1995, 7, 23)
        assert dates.read_value("23/07/05").parsed == date(2005, 7, 23)

    def test_impossible_dates_are_reported_not_guessed(self):
        assert dates.read_value("31/02/2021").parsed is None
        assert dates.read_value("45/99/2021").error

    def test_nonsense_is_reported(self):
        assert dates.read_value("not a date").error
        assert dates.read_value("").error


class TestColumnInference:
    def test_one_clear_row_settles_the_whole_column(self):
        plan = dates.analyse_column(["15/03/2021", "03/04/2021", "05/06/2020", "22/11/2019"])
        assert plan.convention == dates.DMY
        assert plan.anchors == 2 and plan.agreement == 1.0

    def test_a_column_with_no_anchor_stays_unsettled(self):
        """This is the case that must escalate: a genuine coin flip."""
        plan = dates.analyse_column(["03/04/2021", "05/06/2020", "07/08/2019"])
        assert plan.convention is None
        assert len(plan.ambiguous_values) == 3

    def test_contradicting_anchors_lower_the_agreement(self):
        plan = dates.analyse_column(["15/03/2021", "03/15/2021", "22/01/2020"])
        assert plan.agreement < 1.0

    def test_all_iso_needs_no_inference(self):
        plan = dates.analyse_column(["2021-03-15", "2020-06-05"])
        assert plan.convention == dates.ISO and not plan.inferred

    def test_blank_values_are_not_counted(self):
        plan = dates.analyse_column(["", "  ", "15/03/2021"])
        assert plan.total == 1


class TestApplyingAConvention:
    def test_an_ambiguous_value_reads_correctly_under_each_convention(self):
        assert dates.apply_convention("03/04/2021", dates.DMY)[0] == date(2021, 4, 3)
        assert dates.apply_convention("03/04/2021", dates.MDY)[0] == date(2021, 3, 4)

    def test_without_a_convention_it_refuses_rather_than_guesses(self):
        parsed, error = dates.apply_convention("03/04/2021", None)
        assert parsed is None and "no convention" in error

    def test_an_unambiguous_value_ignores_the_convention(self):
        """A day above 12 means what it says regardless of the column's habit."""
        assert dates.apply_convention("15/03/2021", dates.MDY)[0] == date(2021, 3, 15)

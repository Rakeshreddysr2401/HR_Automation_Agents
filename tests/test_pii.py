"""PII must not reach a model, a log, or the audit trail."""

from app import pii
from app.agents.profiler import load_sources, profile_all
from app.schema import get_schema
from app.settings import ROOT


class TestDetection:
    def test_a_pan_is_recognised_by_shape_even_in_an_odd_column(self):
        assert pii.detect_pii_kind("tax_ref", ["ABCDE1234F", "ZXCVB9876K"]) == "pan"

    def test_recognised_by_name_even_without_values(self):
        assert pii.detect_pii_kind("PAN No", []) == "pan"
        assert pii.detect_pii_kind("uan_number", []) == "uan"
        assert pii.detect_pii_kind("Salary Account", []) == "bank_account"

    def test_ordinary_columns_are_left_alone(self):
        assert pii.detect_pii_kind("designation", ["Engineer", "Manager"]) is None
        assert pii.detect_pii_kind("first_name", ["Aarav", "Diya"]) is None


class TestMasking:
    def test_the_last_four_survive_so_a_human_can_still_match_a_document(self):
        assert pii.mask("ABCDE1234F") == "******234F"

    def test_short_values_are_fully_hidden(self):
        assert pii.mask("123") == "***"

    def test_empty_stays_empty(self):
        assert pii.mask("") == "" and pii.mask(None) == ""

    def test_only_fields_the_schema_marks_sensitive_are_masked(self):
        fields = get_schema().pii_fields
        assert pii.redact_value("pan", "ABCDE1234F", fields) == "******234F"
        assert pii.redact_value("first_name", "Aarav", fields) == "Aarav"


class TestProfilesNeverCarryRawIdentifiers:
    def test_what_reaches_the_model_is_redacted(self):
        """The profile is the only thing an agent sends to a model."""
        frames = load_sources([str(ROOT / "data" / "payroll_system.xlsx")])
        profiles = profile_all(frames)
        pan_column = next(p for p in profiles if p.column == "pan_number")

        assert pan_column.is_pii and pan_column.pii_kind == "pan"
        for sample in pan_column.for_llm()["sample_values"]:
            assert "*" in sample, f"{sample} would have been sent to a model in clear"

    def test_raw_values_stay_available_in_process_for_deterministic_work(self):
        """Masking is for what leaves the process, not for the pipeline itself."""
        frames = load_sources([str(ROOT / "data" / "payroll_system.xlsx")])
        profiles = profile_all(frames)
        pan_column = next(p for p in profiles if p.column == "pan_number")
        assert any("*" not in value for value in pan_column.raw_samples)

"""The escalation boundary itself. Both sides of every threshold."""

from app import policy
from app.models import Disposition


class TestMappingBoundary:
    def test_confident_and_unrivalled_is_applied(self):
        assert policy.classify_mapping(0.90, 0.60) is Disposition.AUTO

    def test_confident_but_contested_is_asked(self):
        """The margin test is the important half.

        0.91 against one field and 0.89 against another is not a confident
        mapping; it is a coin flip wearing a high score. Confidence alone would
        apply it and silently corrupt the field the HRMS keys off.
        """
        assert policy.classify_mapping(0.91, 0.89) is Disposition.ESCALATED

    def test_unrivalled_but_unconfident_is_asked(self):
        assert policy.classify_mapping(0.70, 0.20) is Disposition.ESCALATED

    def test_exactly_on_both_thresholds_is_applied(self):
        top = policy.MAPPING_AUTO_MIN
        assert policy.classify_mapping(top, top - policy.MAPPING_MARGIN_MIN) is Disposition.AUTO

    def test_a_hair_under_the_margin_is_asked(self):
        top = policy.MAPPING_AUTO_MIN
        runner_up = top - policy.MAPPING_MARGIN_MIN + 0.001
        assert policy.classify_mapping(top, runner_up) is Disposition.ESCALATED

    def test_no_lexical_foothold_is_dropped_not_queried(self):
        """Confident absence is not ambiguity.

        A column resembling nothing in the schema should be reported and left
        behind. Queueing it would be asking a human to confirm a non-event.
        """
        assert policy.classify_mapping(0.65, 0.40, lexical_best=0.1) is Disposition.IGNORED

    def test_weak_score_but_strong_name_match_is_still_considered(self):
        assert policy.classify_mapping(0.65, 0.40, lexical_best=0.9) is not Disposition.IGNORED


class TestDateBoundary:
    def test_enough_agreeing_anchors_settles_the_column(self):
        assert policy.date_convention_is_safe(anchor_count=18, agreement=1.0)

    def test_too_few_anchors_does_not(self):
        assert not policy.date_convention_is_safe(anchor_count=2, agreement=1.0)

    def test_anchors_that_disagree_do_not(self):
        """A column contradicting itself is not evidence, however many rows."""
        assert not policy.date_convention_is_safe(anchor_count=30, agreement=0.6)

    def test_exactly_at_the_limits_is_safe(self):
        assert policy.date_convention_is_safe(
            policy.DATE_MIN_ANCHORS, policy.DATE_ANCHOR_AGREEMENT
        )


class TestEnumBoundary:
    def test_near_certain_typo_is_corrected(self):
        assert policy.classify_enum_match(96.0) is Disposition.AUTO

    def test_grey_band_is_asked(self):
        """'Engg' resembles 'Engineering' enough to suspect, too loosely to assume."""
        assert policy.classify_enum_match(72.0) is Disposition.ESCALATED

    def test_no_resemblance_is_asked_too(self):
        assert policy.classify_enum_match(30.0) is Disposition.ESCALATED


class TestRetryBoundary:
    def test_transport_failures_are_retried(self):
        for status in (408, 429, 500, 502, 503, 504):
            assert policy.is_retryable(status)

    def test_business_rejections_are_not(self):
        """A 409 does not become false on the third attempt."""
        for status in (400, 401, 403, 404, 409, 422):
            assert not policy.is_retryable(status)


class TestCircuitBreaker:
    def test_a_healthy_run_passes(self):
        tripped, _ = policy.should_trip_breaker(5, 100, 8)
        assert not tripped

    def test_too_many_blocked_records_trips_it(self):
        """The rate trigger, kept below the absolute one so it is what fires."""
        tripped, reason = policy.should_trip_breaker(40, 100, 30)
        assert tripped and "%" in reason

    def test_sheer_volume_trips_it_regardless_of_rate(self):
        tripped, _ = policy.should_trip_breaker(45, 10_000, 60)
        assert tripped

    def test_tiny_datasets_do_not_trip_on_rate(self):
        """Two of three records is 67%, and means nothing at that size."""
        tripped, _ = policy.should_trip_breaker(2, 3, 2)
        assert not tripped


class TestSafeAliases:
    def test_standard_abbreviations_need_no_model(self):
        assert policy.SAFE_ALIASES["gender"]["m"] == "Male"
        assert policy.SAFE_ALIASES["employment_type"]["fte"] == "Permanent"
        assert policy.SAFE_ALIASES["status"]["left"] == "Inactive"

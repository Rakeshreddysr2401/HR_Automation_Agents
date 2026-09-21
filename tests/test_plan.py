"""The dry run.

What matters about this module is not that it renders — it is that it cannot
disagree with the push. It is built from the same persisted records the loader
reads, so the test that earns its keep is the one asserting the payload shown
is the payload sent, and that nothing ready is quietly omitted from the preview.
"""

from __future__ import annotations

import pytest

from app import pipeline, plan
from app.schema import get_schema
from app.store import Store


@pytest.fixture
def analysed(isolated_store: Store):
    files = ["data/legacy_hris_export.csv", "data/payroll_system.xlsx"]
    run_id = "run_plan"
    isolated_store.create_run(run_id, files)
    result = pipeline.run(files=files, run_id=run_id, decisions={}, memory={})
    isolated_store.replace_mappings(run_id, result.mappings)
    isolated_store.replace_records(run_id, result.records)
    isolated_store.replace_audit(run_id, result.audit)
    isolated_store.set_run_status(run_id, "awaiting_review", result.summary())
    return run_id, result, isolated_store


class TestCompleteness:
    def test_every_record_appears_exactly_once(self, analysed):
        """Nothing may be dropped between the store and the preview.

        This is the assertion that caught a real bug: records were keyed on
        (run_id, key) alone, and two un-merged halves of the same person
        overwrote each other, so the preview silently showed fewer people than
        the pipeline produced.
        """
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        stored = store.list_records(run_id)
        assert len(built["will_send"]) + len(built["held_back"]) == len(stored)

    def test_the_pipeline_and_the_store_agree_on_the_count(self, analysed):
        run_id, result, store = analysed
        assert len(store.list_records(run_id)) == len(result.records)

    def test_totals_match_the_lists_they_summarise(self, analysed):
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        assert built["totals"]["will_send"] == len(built["will_send"])
        assert built["totals"]["held_back"] == len(built["held_back"])
        assert built["totals"]["fields_changed"] == sum(
            len(r["changes"]) for r in built["will_send"]
        )


class TestWhatWillBeSent:
    def test_only_ready_records_are_queued_to_send(self, analysed):
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        for record in built["will_send"]:
            assert not record["errors"]
            assert not record["blocked_by"]

    def test_everything_held_back_says_why(self, analysed):
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        for record in built["held_back"]:
            assert record["reason_held"], f"{record['key']} is held with no reason given"

    def test_the_payload_contains_only_schema_fields(self, analysed):
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        allowed = {field.name for field in get_schema().fields}
        for record in built["will_send"] + built["held_back"]:
            assert set(record["payload"]) <= allowed

    def test_internal_bookkeeping_never_reaches_the_payload(self, analysed):
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        for record in built["will_send"] + built["held_back"]:
            assert not [key for key in record["payload"] if key.startswith("_")]

    def test_empty_values_are_omitted_rather_than_sent_as_blanks(self, analysed):
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        for record in built["will_send"]:
            assert all(value not in (None, "") for value in record["payload"].values())


class TestProvenance:
    def test_pii_fields_are_named_so_the_screen_can_mask_them(self, analysed):
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        pii = get_schema().pii_fields
        for record in built["will_send"]:
            assert set(record["pii_fields"]) <= pii
            # Whatever is flagged must actually be in this record's payload.
            assert set(record["pii_fields"]) <= set(record["payload"])

    def test_a_merged_record_is_marked_and_lists_its_sources(self, analysed):
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        for record in built["will_send"] + built["held_back"]:
            assert record["merged"] == (len(record["sources"]) > 1)

    def test_changes_carry_a_before_after_and_a_reason(self, analysed):
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        changes = [c for r in built["will_send"] for c in r["changes"]]
        assert changes, "the sample data must produce some autonomous edits"
        for change in changes:
            assert change["what"]
            assert change["why"]
            assert change["disposition"] in ("auto", "flagged", None)

    def test_column_level_rules_are_not_attributed_to_records(self, analysed):
        """A rule shown against all fifty records it applied to is noise.

        Column-level audit entries belong in the Decisions view; only value-level
        edits are attributed per record here.
        """
        run_id, _, store = analysed
        built = plan.build(run_id, store)
        for record in built["will_send"] + built["held_back"]:
            for change in record["changes"]:
                assert change["action"] != "infer_date_convention"


class TestAfterPush:
    def test_a_loaded_record_moves_out_of_will_send(self, analysed):
        run_id, _, store = analysed
        before = plan.build(run_id, store)
        assert before["will_send"], "need something ready to push for this test"

        key = before["will_send"][0]["key"]
        store.update_push_status(run_id, key, "success", "created")

        after = plan.build(run_id, store)
        assert key not in [r["key"] for r in after["will_send"]]
        assert after["totals"]["already_loaded"] >= 1
        # Loaded is not "held back": a consultant reading "held" expects a
        # problem. It has its own list.
        assert key not in [r["key"] for r in after["held_back"]]
        sent = next(r for r in after["already_sent"] if r["key"] == key)
        assert sent["reason_held"] == "loaded into the HRMS"

    def test_a_transient_failure_stays_retryable(self, analysed):
        run_id, _, store = analysed
        before = plan.build(run_id, store)
        key = before["will_send"][0]["key"]
        store.update_push_status(run_id, key, "failed", "503 from the target")

        after = plan.build(run_id, store)
        # Still in the send list: a 5xx is the network's problem, not a decision.
        assert key in [r["key"] for r in after["will_send"]]


class TestEmptyRun:
    def test_an_unanalysed_run_produces_an_empty_plan(self, isolated_store: Store):
        isolated_store.create_run("run_empty", [])
        built = plan.build("run_empty", isolated_store)
        assert built["will_send"] == []
        assert built["held_back"] == []
        assert built["totals"]["will_send"] == 0

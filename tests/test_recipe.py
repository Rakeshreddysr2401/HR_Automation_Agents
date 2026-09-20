"""The migration recipe: export, replay, and the safety properties it claims.

Three claims are worth testing, because each one is load-bearing for the
productisation argument and each one would fail silently:

1. A recipe contains **no record data**. If it did, it could not be committed to
   a repository, and the claim that it is safe to version-control would be false.
2. Replaying it reproduces the human's answers, keyed by stable subjects.
3. It round-trips through YAML, because the file is the interchange format and a
   recipe that only works in memory is not one.
"""

from __future__ import annotations

import pytest
import yaml

from app import pipeline, recipe
from app.store import Store


@pytest.fixture
def analysed(isolated_store: Store):
    """One pass over the sample exports, persisted as a run would be."""
    files = ["data/legacy_hris_export.csv", "data/payroll_system.xlsx"]
    run_id = "run_recipe"
    isolated_store.create_run(run_id, files)
    result = pipeline.run(files=files, run_id=run_id, decisions={}, memory={})
    isolated_store.replace_mappings(run_id, result.mappings)
    isolated_store.replace_records(run_id, result.records)
    isolated_store.replace_audit(run_id, result.audit)
    isolated_store.replace_escalations(run_id, result.escalations)
    isolated_store.set_run_status(run_id, "awaiting_review", result.summary())
    return run_id, result, isolated_store


class TestStructure:
    def test_every_section_is_present(self, analysed):
        run_id, _, store = analysed
        built = recipe.build(run_id, store)
        for section in (
            "field_mappings",
            "ignored_columns",
            "date_conventions",
            "value_mappings",
            "identity_rules",
            "answers",
            "notes",
        ):
            assert section in built, f"{section} missing"
        assert built["recipe_version"] == 1
        assert built["source_run"] == run_id

    def test_mappings_are_labelled_by_how_they_were_reached(self, analysed):
        run_id, _, store = analysed
        built = recipe.build(run_id, store)
        assert built["field_mappings"], "the sample must produce some mappings"
        for entry in built["field_mappings"]:
            assert entry["how"] in ("confirmed", "inferred", "automatic")
            assert entry["target_field"]

    def test_dropped_columns_are_recorded_with_a_reason(self, analysed):
        run_id, _, store = analysed
        built = recipe.build(run_id, store)
        # These are the judgments most likely to be wrong once the schema grows
        # a field, so they are exported rather than thrown away.
        for entry in built["ignored_columns"]:
            assert entry["source_column"]
            assert entry["reason"]

    def test_value_mappings_are_collapsed_to_distinct_pairs(self, analysed):
        run_id, _, store = analysed
        built = recipe.build(run_id, store)
        pairs = [(v["from"].lower(), v["to"]) for v in built["value_mappings"]]
        # The audit has one row per rewritten value; the *rule* is the pair, and
        # repeating it forty times would make the file unreadable and no truer.
        assert len(pairs) == len(set(pairs))


class TestNoRecordData:
    """The property that makes a recipe safe to commit."""

    def test_no_pii_value_appears_anywhere_in_the_export(self, analysed):
        run_id, result, store = analysed
        text = recipe.to_yaml(recipe.build(run_id, store))

        # Collect the real PAN, UAN, account and email values from the records
        # the pipeline built, then assert none of them survived into the file.
        leaked = []
        for record in result.records:
            for field in ("pan", "uan", "bank_account", "work_email", "personal_email"):
                value = str(record.fields.get(field) or "").strip()
                if len(value) > 6 and value in text:
                    leaked.append((record.key, field, value))
        assert not leaked, f"record data leaked into the recipe: {leaked[:5]}"

    def test_no_employee_names_appear(self, analysed):
        run_id, result, store = analysed
        text = recipe.to_yaml(recipe.build(run_id, store))
        leaked = [
            record.fields.get("last_name")
            for record in result.records
            if (record.fields.get("last_name") or "")
            and len(str(record.fields["last_name"])) > 4
            and str(record.fields["last_name"]) in text
        ]
        assert not leaked, f"names leaked into the recipe: {sorted(set(leaked))[:5]}"


class TestIdentityRules:
    def test_rehire_and_identity_decisions_exported_with_meaning(self):
        decisions = {
            "identity:E1032|P2201": "merge:E1032",
            "rehire:E0910|E1031": "separate",
        }
        rules = recipe._identity_rules(decisions)
        assert len(rules) == 2
        assert rules[0] == {
            "pair": "E1032|P2201",
            "decision": "merge:E1032",
            "meaning": "one person, two rows - combine them",
        }
        assert rules[1] == {
            "pair": "E0910|E1031",
            "decision": "separate",
            "meaning": "two distinct employment records - keep both",
        }


class TestReplay:
    def test_answers_round_trip_through_yaml(self, analysed):
        run_id, result, store = analysed
        answers = {
            escalation.subject: escalation.options[0]["value"]
            for escalation in result.escalations
            if escalation.options
        }
        for subject, answer in answers.items():
            store.save_decision(run_id, subject, answer)

        text = recipe.to_yaml(recipe.build(run_id, store))
        replayed = recipe.apply(recipe.parse(text))
        assert replayed == answers

    def test_only_the_answers_block_is_replayed(self):
        """Mappings are a record of what happened, not instructions.

        Re-deriving them against the new file is what catches the case where the
        next export genuinely differs — so `apply` must ignore them.
        """
        replayed = recipe.apply(
            {
                "recipe_version": 1,
                "field_mappings": [{"source_column": "emp_cd", "target_field": "employee_code"}],
                "answers": {"enum:department:engg": "Engineering"},
            }
        )
        assert replayed == {"enum:department:engg": "Engineering"}

    def test_a_missing_answers_block_replays_nothing(self):
        assert recipe.apply({"recipe_version": 1}) == {}

    def test_an_unknown_version_is_refused(self):
        with pytest.raises(ValueError, match="unsupported recipe_version"):
            recipe.apply({"recipe_version": 99, "answers": {}})

    def test_a_non_mapping_is_refused(self):
        with pytest.raises(ValueError):
            recipe.apply(["not", "a", "recipe"])
        with pytest.raises(ValueError):
            recipe.parse("- just\n- a\n- list\n")

    def test_answers_must_be_a_mapping(self):
        with pytest.raises(ValueError, match="must be a mapping"):
            recipe.apply({"answers": ["DMY"]})


class TestRendering:
    def test_the_yaml_is_loadable_and_carries_its_header(self, analysed):
        run_id, _, store = analysed
        text = recipe.to_yaml(recipe.build(run_id, store))
        assert text.lstrip().startswith("#"), "the file should explain itself first"
        assert "Safe to commit" in text
        assert isinstance(yaml.safe_load(text), dict)

    def test_authored_key_order_is_preserved(self, analysed):
        """Order carries meaning: mappings, then conventions, then answers."""
        run_id, _, store = analysed
        text = recipe.to_yaml(recipe.build(run_id, store))
        assert text.index("field_mappings") < text.index("date_conventions")
        assert text.index("date_conventions") < text.index("answers")

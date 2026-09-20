"""The human gate: the graph stops, takes answers, and carries on.

Mirrors the interrupt/resume pattern this project borrows from the author's
SubAgents repo - the same thread config must be used to resume, which is what
lets a review sit unanswered across a restart.
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.graph import build_graph
from app.settings import ROOT
from tests.conftest import needs_embeddings

FILES = [
    str(ROOT / "data" / "legacy_hris_export.csv"),
    str(ROOT / "data" / "payroll_system.xlsx"),
]

ANSWERS = {
    "contest:legacy_hris_export.csv:work_email": "Official Email",
    "map:legacy_hris_export.csv:Mail ID": "personal_email",
    "date:payroll_system.xlsx:joining_dt": "DMY",
    "enum:department:engg": "Engineering",
    "rehire:E0910|E1031": "separate",
    "identity:E1032|P2201": "merge:E1032",
    "manager:former.manager@novatech.in": "clear",
    "cycle:E1005|E1013": "cycle-clear:E1013",
    "record:E1010": {"action": "edit", "fields": {"pan": "ABCDE1234F"}},
    "record:E0910": {"action": "edit", "fields": {"date_of_exit": "2019-06-30"}},
    "record:E1034": {"action": "edit", "fields": {"date_of_exit": "2024-03-31"}},
}


@pytest.fixture(autouse=True)
def _no_recommendations(quiet_reasoning):
    """The reasoning model only writes the wording on a card.

    It has no bearing on which questions are raised or how they resolve, and a
    remote model would otherwise add several seconds per escalation to every test
    in this module. Embeddings stay live, since those drive the scoring.
    """


@pytest.fixture(autouse=True)
def _dont_really_push(monkeypatch):
    """Stub the final push.

    These tests are about the human gate - that the graph stops, accepts answers
    and carries on. Once the queue drains the graph proceeds to load 41 records
    into a target system that is not running here, and the loader correctly
    treats a refused connection as transient and retries each one with backoff.
    That is right behaviour and it is covered by test_loader.py; here it is three
    minutes of deliberate sleeping that proves nothing.
    """
    from app.agents import loader

    monkeypatch.setattr(
        loader,
        "push_records",
        lambda run_id, records, **kwargs: {
            "pushed": len(records), "push_failed": 0, "push_rejected": 0,
            "failed_keys": [], "rejected_keys": [],
        },
    )


def drain(graph, payload, config):
    """Run the graph, collecting interrupts and progress lines."""
    interrupts, progress = [], []
    for mode, chunk in graph.stream(payload, config, stream_mode=["updates", "custom"]):
        if mode == "custom" and isinstance(chunk, dict) and "progress" in chunk:
            progress.append(chunk["progress"])
        elif mode == "updates" and isinstance(chunk, dict) and "__interrupt__" in chunk:
            interrupts.append(chunk["__interrupt__"][0].value)
    return interrupts, progress


@needs_embeddings
class TestTheGate:
    @pytest.fixture
    def graph(self):
        return build_graph(MemorySaver())

    def test_it_stops_and_hands_over_the_whole_queue_at_once(self, graph, isolated_store):
        """One gate for everything, not one interruption per finding."""
        isolated_store.create_run("g1", FILES)
        config = {"configurable": {"thread_id": "g1"}}

        interrupts, progress = drain(graph, {"run_id": "g1", "files": FILES, "decisions": {}}, config)

        assert len(interrupts) == 1, "the human should be interrupted once, not ten times"
        assert len(interrupts[0]["escalations"]) == 8
        assert progress, "the run should narrate itself for the live view"

    def test_resuming_applies_the_answers_and_finishes(self, graph, isolated_store):
        isolated_store.create_run("g2", FILES)
        config = {"configurable": {"thread_id": "g2"}}
        drain(graph, {"run_id": "g2", "files": FILES, "decisions": {}}, config)

        # The same config is what reconnects to the suspended run.
        more, _ = drain(graph, Command(resume={"decisions": ANSWERS}), config)

        assert more == [], "everything was answered, so it should not stop again"
        state = graph.get_state(config)
        assert state.next == (), "the graph should have run to completion"
        assert state.values["summary"]["escalations"] == 0

    def test_a_partial_answer_stops_again_with_what_is_left(self, graph, isolated_store):
        """Answering some questions is allowed; it comes back for the rest."""
        isolated_store.create_run("g3", FILES)
        config = {"configurable": {"thread_id": "g3"}}
        drain(graph, {"run_id": "g3", "files": FILES, "decisions": {}}, config)

        partial = {"contest:legacy_hris_export.csv:work_email": "Official Email"}
        more, _ = drain(graph, Command(resume={"decisions": partial}), config)

        assert len(more) == 1, "it should pause again rather than proceed half-resolved"
        assert more[0]["round"] == 2

    def test_answers_are_remembered_for_later_runs(self, graph, isolated_store):
        """A column a consultant identifies once is not asked about again."""
        isolated_store.create_run("g4", FILES)
        config = {"configurable": {"thread_id": "g4"}}
        drain(graph, {"run_id": "g4", "files": FILES, "decisions": {}}, config)
        drain(graph, Command(resume={"decisions": ANSWERS}), config)

        remembered = isolated_store.remembered_mappings()
        assert remembered.get("official email") == "work_email"
        assert remembered.get("mail id") == "personal_email"

    def test_the_second_run_does_not_re_ask_what_it_was_told(self, graph, isolated_store):
        """What memory actually promises.

        Not "a shorter queue" - that was the old assertion and it is the wrong
        measure. Recalling the email mapping resolves it at round one, which
        lets the hierarchy checks run immediately instead of being deferred to
        round two; those two questions move *forward* into the first interrupt,
        so the round-one count can rise while strictly less work is being asked
        of the human overall.

        The promise is narrower and testable: a column a consultant has already
        identified is never queued again.
        """
        isolated_store.create_run("g5", FILES)
        first = {"configurable": {"thread_id": "g5"}}
        opening, _ = drain(graph, {"run_id": "g5", "files": FILES, "decisions": {}}, first)
        drain(graph, Command(resume={"decisions": ANSWERS}), first)

        asked_first = {e["subject"] for e in opening[0]["escalations"]}
        assert "contest:legacy_hris_export.csv:work_email" in asked_first

        isolated_store.create_run("g6", FILES)
        second = {"configurable": {"thread_id": "g6"}}
        again, _ = drain(graph, {"run_id": "g6", "files": FILES, "decisions": {}}, second)
        asked_again = {e["subject"] for e in again[0]["escalations"]} if again else set()

        remembered = set(isolated_store.remembered_mappings())
        assert remembered, "answers should have been remembered"
        assert "contest:legacy_hris_export.csv:work_email" not in asked_again, (
            "a mapping confirmed once must not be asked about again"
        )
        # And the questions it does raise are ones it could not have known.
        assert asked_again - asked_first, (
            "the deferred hierarchy checks should now surface at round one"
        )

    def test_push_rejection_escalates_to_gate_and_completes_on_resolution(
        self, graph, isolated_store, monkeypatch
    ):
        """A business rejection by the target system must pause at the human gate."""
        from app.agents import loader
        from app.models import Escalation, EscalationType

        pushed_attempts = 0

        def mock_push(run_id, records, **kwargs):
            nonlocal pushed_attempts
            pushed_attempts += 1
            if pushed_attempts == 1:
                rejected_key = records[0]["key"] if records else "E1001"
                esc = Escalation(
                    run_id=run_id,
                    type=EscalationType.PUSH_REJECTED,
                    subject=f"push:{rejected_key}",
                    title=f"The target system refused {rejected_key}",
                    question="Duplicate code in target HRMS",
                    evidence={
                        "record_key": rejected_key,
                        "employee_code": rejected_key,
                        "editable_fields": ["employee_code"],
                    },
                    options=[
                        {"value": "skip", "label": "Leave it out"},
                        {"value": "edit", "label": "Change code"},
                    ],
                    affected_records=[rejected_key],
                )
                isolated_store.replace_escalations(run_id, [esc])
                return {
                    "pushed": max(0, len(records) - 1),
                    "push_failed": 0,
                    "push_rejected": 1,
                    "failed_keys": [],
                    "rejected_keys": [rejected_key],
                }
            return {
                "pushed": len(records),
                "push_failed": 0,
                "push_rejected": 0,
                "failed_keys": [],
                "rejected_keys": [],
            }

        monkeypatch.setattr(loader, "push_records", mock_push)

        isolated_store.create_run("g_push", FILES)
        config = {"configurable": {"thread_id": "g_push"}}
        drain(graph, {"run_id": "g_push", "files": FILES, "decisions": {}}, config)

        more, _ = drain(graph, Command(resume={"decisions": ANSWERS}), config)
        assert len(more) == 1, "push rejection should interrupt the gate"
        push_esc = more[0]["escalations"]
        assert len(push_esc) == 1
        assert push_esc[0]["type"] == "push_rejected"
        assert push_esc[0]["subject"].startswith("push:")

        final_drain, _ = drain(
            graph, Command(resume={"decisions": {push_esc[0]["subject"]: "skip"}}), config
        )
        assert final_drain == [], "resolving the push rejection should finish the run"
        state = graph.get_state(config)
        assert state.next == ()

    def test_a_rollback_survives_re_analysis(self, graph, isolated_store):
        """Answering a later question re-runs the whole analysis. A record a
        person rolled back must stay out of the target, not quietly re-push."""
        isolated_store.create_run("g6", FILES)
        config = {"configurable": {"thread_id": "g6"}}
        drain(graph, {"run_id": "g6", "files": FILES, "decisions": {}}, config)

        partial = {k: v for k, v in ANSWERS.items() if not k.startswith("record:")}
        drain(graph, Command(resume={"decisions": partial}), config)
        isolated_store.update_push_status("g6", "E1001", "success", "TGT-1")
        isolated_store.update_push_status("g6", "E1002", "rolled_back", "wrong entity")

        rest = {k: v for k, v in ANSWERS.items() if k.startswith("record:")}
        drain(graph, Command(resume={"decisions": rest}), config)

        by_key = {r["key"]: r["push_status"] for r in isolated_store.list_records("g6")}
        assert by_key["E1001"] == "success"
        assert by_key["E1002"] == "rolled_back"

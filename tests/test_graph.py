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
    "cycle-clear:E1013": True,
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
        assert len(interrupts[0]["escalations"]) == 10
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

    def test_the_second_run_of_the_same_files_asks_less(self, graph, isolated_store):
        isolated_store.create_run("g5", FILES)
        first = {"configurable": {"thread_id": "g5"}}
        opening, _ = drain(graph, {"run_id": "g5", "files": FILES, "decisions": {}}, first)
        drain(graph, Command(resume={"decisions": ANSWERS}), first)

        isolated_store.create_run("g6", FILES)
        second = {"configurable": {"thread_id": "g6"}}
        again, _ = drain(graph, {"run_id": "g6", "files": FILES, "decisions": {}}, second)

        asked_first = len(opening[0]["escalations"])
        asked_again = len(again[0]["escalations"]) if again else 0
        assert asked_again < asked_first, (
            f"memory should shrink the queue, got {asked_again} against {asked_first}"
        )

"""The LangGraph pipeline and its human gate.

The graph is small because `app/pipeline.run` is a pure function of (files,
decisions). That is the point of the design: rather than a long chain of nodes
each mutating shared state, there is one deterministic analysis step, one gate
that asks a human, and a loop back.

    analyse ──► gate ──(questions open)──► interrupt() ──► analyse
                  │
                  └──(none)──► push ──► END

Re-running the whole analysis after each answer is cheap - embeddings are cached
and the work is deterministic - and it is the only way to keep downstream results
consistent with an upstream answer. Confirming which column holds the work email
changes how records merge, which changes what validates; a patch applied to the
existing result would leave all of that stale.

`interrupt()` suspends the graph inside the checkpointer, so a run can sit waiting
for review across a server restart and pick up exactly where it stopped.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app import pipeline
from app.state import MigrationState
from app.store import get_store

log = logging.getLogger(__name__)

Emit = Callable[[str], None]


def _progress(text: str) -> None:
    """Push a line to the live view, when running inside a graph."""
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:  # noqa: BLE001 - outside a graph run there is nothing to write to
        return
    if writer is not None:
        writer({"progress": text})


def analyse(state: MigrationState) -> dict[str, Any]:
    """Run the whole migration against the answers gathered so far."""
    run_id = state["run_id"]
    store = get_store()
    decisions = dict(state.get("decisions") or {})
    round_number = int(state.get("round", 0)) + 1

    _progress(
        f"Analysis pass {round_number}"
        + (f" with {len(decisions)} decision(s) applied" if decisions else "")
    )

    memory = store.remembered_mappings()
    if memory:
        _progress(f"Recalled {len(memory)} column mapping(s) confirmed on previous runs")

    result = pipeline.run(
        files=state["files"],
        run_id=run_id,
        decisions=decisions,
        memory=memory,
        emit=_progress,
    )

    store.replace_escalations(run_id, result.escalations)
    store.replace_records(run_id, result.records)
    store.replace_audit(run_id, result.audit)
    store.note_memory_used(
        [m.column.strip().lower().replace("_", " ") for m in result.mappings if m.provenance == "memory"]
    )
    store.set_run_status(
        run_id,
        "awaiting_review" if result.escalations else "ready_to_push",
        result.summary(),
    )

    return {
        "round": round_number,
        "open_subjects": [e.subject for e in result.escalations],
        "summary": result.summary(),
    }


def gate(state: MigrationState) -> dict[str, Any]:
    """Hand the whole queue to a human at once, and wait.

    One gate for the entire queue rather than one per question: a consultant
    should see everything that needs them, triage it in whatever order they like,
    and hand it all back. Interrupting once per finding would turn a five-minute
    review into forty separate interruptions.
    """
    subjects = state.get("open_subjects") or []
    if not subjects:
        return {}

    store = get_store()
    run_id = state["run_id"]
    escalations = store.list_escalations(run_id, status="open")

    if int(state.get("round", 0)) >= pipeline.MAX_ROUNDS:
        log.warning("Run %s hit the round limit with %d open", run_id, len(subjects))
        return {"aborted": True}

    answers = interrupt(
        {
            "type": "review_required",
            "run_id": run_id,
            "round": state.get("round", 0),
            "summary": state.get("summary", {}),
            "escalations": escalations,
        }
    )

    decisions = (answers or {}).get("decisions", answers) or {}
    for subject, answer in decisions.items():
        store.save_decision(run_id, subject, answer)
        store.mark_resolved(run_id, subject, answer)
        store.remember(subject, answer)
    _progress(f"Received {len(decisions)} decision(s) from the consultant")
    return {"decisions": decisions}


def push(state: MigrationState) -> dict[str, Any]:
    """Send the ready records to the target system."""
    from app.agents import loader

    run_id = state["run_id"]
    store = get_store()
    records = store.list_records(run_id)
    ready = [r for r in records if r.get("ready") and r.get("push_status") == "pending"]

    _progress(f"Pushing {len(ready)} record(s) to the target system")
    outcome = loader.push_records(run_id, ready, emit=_progress)
    store.set_run_status(run_id, "complete", {**(state.get("summary") or {}), **outcome})
    return {"pushed": True, "summary": {**(state.get("summary") or {}), **outcome}}


def _after_gate(state: MigrationState) -> str:
    if state.get("aborted"):
        return END
    return "analyse" if state.get("open_subjects") else "push"


def build_graph(checkpointer=None):
    builder = StateGraph(MigrationState)
    builder.add_node("analyse", analyse)
    builder.add_node("gate", gate)
    builder.add_node("push", push)

    builder.add_edge(START, "analyse")
    builder.add_edge("analyse", "gate")
    builder.add_conditional_edges("gate", _after_gate, {"analyse": "analyse", "push": "push", END: END})
    builder.add_edge("push", END)

    return builder.compile(checkpointer=checkpointer)


def open_checkpointer(path: str) -> SqliteSaver:
    """Synchronous checkpointer, for CLI use and tests."""
    import sqlite3

    connection = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()
    return saver


async def open_async_checkpointer(path: str):
    """Async checkpointer, for the server.

    The API streams with `astream`, and the synchronous saver refuses async
    calls outright, so the server needs this variant. Graph nodes stay
    synchronous either way - LangGraph runs them in a worker thread.
    """
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    connection = await aiosqlite.connect(path)
    saver = AsyncSqliteSaver(connection)
    await saver.setup()
    return saver

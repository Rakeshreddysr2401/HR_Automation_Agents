"""Graph state.

Kept deliberately small. The dataset lives in SQLite (`app/store.py`); what
travels through the graph is a coordination token - which run this is, what it is
waiting on, and the answers gathered so far. Checkpoints are written on every
step, so putting records in here would write a copy of the dataset each time.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict


def merge_decisions(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Decisions accumulate across rounds; the newest answer for a subject wins."""
    return {**(left or {}), **(right or {})}


class MigrationState(TypedDict, total=False):
    run_id: str
    files: list[str]
    decisions: Annotated[dict[str, Any], merge_decisions]
    round: int
    open_subjects: list[str]
    summary: dict[str, Any]
    pushed: bool
    aborted: bool

"""HTTP surface: start a run, watch it work, answer its questions.

The streaming contract is one JSON object per SSE `data:` line, each carrying a
`type`. Unknown types are ignored by the client, so new event types are additive
and never break an older page.

    progress      a line for the live activity view
    escalations   the current queue, sent whenever it changes
    summary       counters for the header
    awaiting      the run has stopped and needs a human
    done          the run finished
    error         something failed; the message is displayed

Resuming is a separate connection rather than a long-lived socket: the client
POSTs its decisions, then reopens the stream. That keeps the whole thing working
over plain SSE, and means a dropped connection never loses a decision - the
answers are already persisted before the stream reopens.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from app import llm
from app.agents import loader
from app.settings import ROOT, get_settings
from app.store import get_store

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["migration"])

SAMPLE_FILES = ["legacy_hris_export.csv", "payroll_system.xlsx"]


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _thread_config(run_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": run_id}}


@router.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "models": llm.status()}


@router.post("/runs")
async def create_run(
    files: list[UploadFile] = File(default=[]),
    use_sample: bool = Body(default=False, embed=True),
) -> dict[str, Any]:
    """Register a run over uploaded files, or over the bundled sample exports."""
    settings = get_settings()
    store = get_store()
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    paths: list[str] = []
    if files:
        upload_dir = Path(settings.upload_dir) / run_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        for upload in files:
            if not upload.filename:
                continue
            if not upload.filename.lower().endswith((".csv", ".xlsx", ".xls")):
                raise HTTPException(400, f"{upload.filename} is not a CSV or Excel file")
            destination = upload_dir / Path(upload.filename).name
            destination.write_bytes(await upload.read())
            paths.append(str(destination))

    if not paths:
        paths = [str(ROOT / "data" / name) for name in SAMPLE_FILES]

    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        raise HTTPException(400, f"missing source files: {', '.join(missing)}")

    store.create_run(run_id, paths)
    return {"run_id": run_id, "files": [Path(p).name for p in paths]}


@router.get("/runs")
async def list_runs() -> dict[str, Any]:
    return {"runs": get_store().list_runs()}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request) -> StreamingResponse:
    """Start or resume the run, streaming what the agent is doing."""
    store = get_store()
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "no such run")

    graph = request.app.state.graph
    config = _thread_config(run_id)

    async def stream():
        try:
            snapshot = await asyncio.to_thread(graph.get_state, config)
            waiting = bool(snapshot.next) and snapshot.created_at is not None

            if waiting:
                decisions = store.get_decisions(run_id)
                yield _sse(
                    {
                        "type": "progress",
                        "text": f"Resuming with {len(decisions)} decision(s)",
                    }
                )
                graph_input: Any = Command(resume={"decisions": decisions})
            else:
                # Seeded rather than empty, so a run started from a recipe has
                # those answers in hand on the *first* pass. With no recipe this
                # is an empty dict and the run behaves exactly as before.
                seeded = store.get_decisions(run_id)
                if seeded:
                    yield _sse(
                        {
                            "type": "progress",
                            "text": (
                                f"Starting with {len(seeded)} answer(s) replayed from a recipe"
                            ),
                        }
                    )
                graph_input = {"run_id": run_id, "files": run["files"], "decisions": seeded}

            interrupted = False
            round_number = 0
            async for mode, chunk in graph.astream(
                graph_input, config, stream_mode=["updates", "custom"]
            ):
                if await request.is_disconnected():
                    break
                if mode == "custom" and isinstance(chunk, dict) and "progress" in chunk:
                    yield _sse({"type": "progress", "text": chunk["progress"]})
                elif mode == "updates" and isinstance(chunk, dict):
                    if "__interrupt__" in chunk:
                        interrupted = True
                        value = chunk["__interrupt__"][0].value
                        round_number = int(value.get("round", 0) or 0)
                        yield _sse(
                            {
                                "type": "escalations",
                                "escalations": value.get("escalations", []),
                                "summary": value.get("summary", {}),
                                "round": value.get("round", 0),
                            }
                        )
                    for node_state in chunk.values():
                        if isinstance(node_state, dict) and node_state.get("summary"):
                            yield _sse({"type": "summary", "summary": node_state["summary"]})

            run_now = store.get_run(run_id) or {}
            if interrupted:
                yield _sse(
                    {
                        "type": "awaiting",
                        "escalations": store.list_escalations(run_id, status="open"),
                        "summary": run_now.get("summary", {}),
                        "round": round_number,
                    }
                )
            else:
                yield _sse(
                    {
                        "type": "done",
                        "summary": run_now.get("summary", {}),
                        "records": store.list_records(run_id),
                    }
                )
        except Exception as exc:  # noqa: BLE001 - the stream must report, not vanish
            log.exception("run %s failed", run_id)
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/decisions")
async def submit_decisions(run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Persist answers. The client then reopens the stream to resume the run."""
    store = get_store()
    if not store.get_run(run_id):
        raise HTTPException(404, "no such run")
    decisions = payload.get("decisions") or {}
    if not isinstance(decisions, dict) or not decisions:
        raise HTTPException(400, "expected a non-empty 'decisions' object")
    for subject, answer in decisions.items():
        store.save_decision(run_id, subject, answer)
    return {"accepted": len(decisions)}


@router.get("/runs/{run_id}/escalations")
async def get_escalations(run_id: str, status: str | None = None) -> dict[str, Any]:
    return {"escalations": get_store().list_escalations(run_id, status=status)}


@router.get("/runs/{run_id}/records")
async def get_records(run_id: str) -> dict[str, Any]:
    return {"records": get_store().list_records(run_id)}


@router.get("/runs/{run_id}/audit")
async def get_audit(run_id: str) -> dict[str, Any]:
    return {"audit": get_store().list_audit(run_id)}


@router.get("/runs/{run_id}/push-log")
async def get_push_log(run_id: str) -> dict[str, Any]:
    return {"push_log": get_store().list_push_log(run_id)}


@router.get("/runs/{run_id}/summary")
async def get_summary(run_id: str) -> dict[str, Any]:
    run = get_store().get_run(run_id)
    if not run:
        raise HTTPException(404, "no such run")
    return run


@router.post("/runs/{run_id}/retry")
async def retry_push(run_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Re-attempt records whose failure was transient.

    With no keys, only transient failures are retried. Named keys may also
    include rolled-back records - that is a human explicitly asking for them
    to be pushed again, not the agent deciding to.
    """
    store = get_store()
    if not store.get_run(run_id):
        raise HTTPException(404, "no such run")
    keys = payload.get("keys")
    retryable = ("failed", "rolled_back") if keys else ("failed",)
    records = store.list_records(run_id)
    targets = [
        r
        for r in records
        if r.get("push_status") in retryable and (not keys or r["key"] in keys)
    ]
    if not targets:
        return {"retried": 0, "detail": "nothing is in a retryable state"}
    for record in targets:
        store.update_push_status(run_id, record["key"], "pending", "")
        record["push_status"] = "pending"
    outcome = await asyncio.to_thread(loader.push_records, run_id, targets)
    return {"retried": len(targets), **outcome}


@router.post("/runs/{run_id}/rollback")
async def rollback_push(run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Remove already-loaded records from the target system."""
    store = get_store()
    if not store.get_run(run_id):
        raise HTTPException(404, "no such run")
    keys = payload.get("keys") or []
    reason = str(payload.get("reason") or "").strip()
    if not keys:
        raise HTTPException(400, "expected 'keys'")
    if not reason:
        raise HTTPException(400, "a reason is required - it goes into the audit trail")
    return await asyncio.to_thread(loader.rollback, run_id, keys, reason)


@router.get("/memory")
async def get_memory() -> dict[str, Any]:
    """Column mappings confirmed by a human, reusable across runs and clients."""
    return {"memory": get_store().list_memory()}


# ---------------------------------------------------------------------------
# Inspection: the boundary, the schema, the mapping
# ---------------------------------------------------------------------------


@router.get("/policy")
async def get_policy() -> dict[str, Any]:
    """The escalation boundary, served from `app/policy.py` itself.

    The UI renders this rather than restating the thresholds in TypeScript. A
    second copy of the numbers could drift from the real ones, and then the
    screen explaining the agent's judgment would be the least trustworthy thing
    on it.
    """
    from app import policy

    return policy.describe()


@router.get("/schema")
async def get_target_schema() -> dict[str, Any]:
    """The target schema, for the mapping view and the correction dropdowns."""
    from app.schema import get_schema

    schema = get_schema()
    return {
        "entity": schema.entity,
        "version": schema.version,
        "fields": [
            {
                "name": f.name,
                "type": f.type,
                "description": f.description,
                "required": f.required,
                "unique": f.unique,
                "identity": f.identity,
                "format": f.format,
                "enum": f.enum,
                "pii": f.pii,
                "references": f.references,
            }
            for f in schema.fields
        ],
        "business_rules": schema.business_rules,
    }


@router.get("/runs/{run_id}/mappings")
async def get_mappings(run_id: str) -> dict[str, Any]:
    store = get_store()
    if not store.get_run(run_id):
        raise HTTPException(404, "no such run")
    return {"mappings": store.list_mappings(run_id)}


# ---------------------------------------------------------------------------
# The dry run and the recipe
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/plan")
async def get_plan(run_id: str) -> dict[str, Any]:
    """Exactly what will be sent, per record, before anything is sent."""
    from app import plan as plan_module

    store = get_store()
    if not store.get_run(run_id):
        raise HTTPException(404, "no such run")
    return plan_module.build(run_id, store)


@router.get("/runs/{run_id}/recipe")
async def get_recipe(run_id: str, format: str = "json") -> Any:
    """Export this run's decisions as a reusable migration recipe."""
    from app import recipe as recipe_module

    store = get_store()
    if not store.get_run(run_id):
        raise HTTPException(404, "no such run")
    built = recipe_module.build(run_id, store)
    if format == "yaml":
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(
            recipe_module.to_yaml(built),
            media_type="text/yaml",
            headers={
                "Content-Disposition": f'attachment; filename="recipe_{run_id}.yaml"'
            },
        )
    return built


@router.post("/runs/{run_id}/recipe")
async def apply_recipe(run_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Seed a run with the answers from a previous migration's recipe.

    Applied before the run starts, so those subjects never become questions.
    Only the `answers` block is replayed - the mappings are re-derived against
    the new files, which is what catches the case where the next export really
    does differ.
    """
    from app import recipe as recipe_module

    store = get_store()
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "no such run")
    # A run is registered as "running" the moment it is created, so status is
    # not the test. A summary only exists once an analysis pass has finished,
    # which is exactly the point after which seeding would be too late to stop
    # those subjects becoming questions.
    if run.get("summary"):
        raise HTTPException(
            409,
            "this run has already been analysed; apply a recipe to a fresh run so "
            "the answers are in hand on the first pass",
        )

    body = payload.get("recipe")
    try:
        parsed = recipe_module.parse(body) if isinstance(body, str) else body
        answers = recipe_module.apply(parsed)
    except (ValueError, yaml.YAMLError) as exc:
        raise HTTPException(400, f"that is not a readable recipe: {exc}") from exc

    for subject, answer in answers.items():
        store.save_decision(run_id, subject, answer)
    return {"seeded": len(answers), "subjects": sorted(answers)}

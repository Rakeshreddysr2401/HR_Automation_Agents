"""Loader: push records, and know which failures are worth retrying.

The distinction it exists to make:

    5xx, timeouts   the target never processed the request. Retrying is correct,
                    and the loader does it with backoff, unattended.
    4xx             the target processed it and refused. "This employee code
                    already exists" does not become false on the third attempt,
                    so retrying is just a slower way to fail. It goes to a human
                    with the target's own words attached.

Every attempt carries an idempotency key derived from the run and the employee
code, so a retry after an ambiguous timeout cannot create the same employee
twice - the classic way a "safe" retry corrupts a migration.

Rollback is a compensating delete rather than a transaction, because that is what
a real HR API offers. It is recorded in the audit trail like any other change.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from app import policy
from app.models import Actor, AuditEntry, Disposition, Escalation, EscalationType
from app.schema import get_schema
from app.settings import get_settings
from app.store import get_store

Emit = Callable[[str], None]


def _idempotency_key(run_id: str, code: str) -> str:
    return f"{run_id}:{code}"


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in (record.get("fields") or {}).items()
        if not key.startswith("_") and value not in (None, "")
    }


def _post(client: httpx.Client, base: str, body: dict, key: str) -> tuple[int, Any]:
    try:
        response = client.post(
            f"{base}/employees", json=body, headers={"Idempotency-Key": key}, timeout=15.0
        )
    except httpx.RequestError as exc:
        # The request never landed, so this is the retryable shape of failure.
        return 503, {"error": f"could not reach the target system: {exc}"}
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {"error": response.text[:200]}


def push_records(
    run_id: str,
    records: list[dict[str, Any]],
    emit: Emit = lambda _: None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Push each ready record, retrying only what deserves it."""
    settings = get_settings()
    store = get_store()
    base = settings.target_api_base.rstrip("/")
    owns_client = client is None
    client = client or httpx.Client()

    succeeded: list[str] = []
    failed: list[str] = []
    rejected: list[str] = []
    audit: list[AuditEntry] = []
    escalations: list[Escalation] = []

    try:
        for record in records:
            key = record["key"]
            code = str((record.get("fields") or {}).get("employee_code") or key)
            body = _payload(record)
            idempotency = _idempotency_key(run_id, code)

            status, response = 0, {}
            for attempt in range(1, policy.PUSH_MAX_ATTEMPTS + 1):
                status, response = _post(client, base, body, idempotency)
                detail = (
                    response.get("detail", response)
                    if isinstance(response, dict)
                    else {"error": str(response)}
                )
                store.log_push(run_id, key, attempt, str(status), str(detail)[:300])

                if status < 400:
                    break
                if not policy.is_retryable(status):
                    break
                if attempt < policy.PUSH_MAX_ATTEMPTS:
                    wait = policy.PUSH_BACKOFF_SECONDS[
                        min(attempt - 1, len(policy.PUSH_BACKOFF_SECONDS) - 1)
                    ]
                    emit(f"{code} hit a transient error - retrying in {wait:.1f}s")
                    time.sleep(wait)

            detail = response.get("detail", response) if isinstance(response, dict) else {}
            message = detail.get("error", "") if isinstance(detail, dict) else str(detail)

            if status < 400:
                succeeded.append(key)
                store.update_push_status(run_id, key, "success", str(response.get("id", "")))
                audit.append(
                    AuditEntry(
                        run_id=run_id,
                        actor=Actor.AGENT,
                        action="push_record",
                        entity=key,
                        before="pending",
                        after=f"created as {response.get('id', 'unknown')}",
                        disposition=Disposition.AUTO,
                        rationale=f"Target system accepted {code}.",
                    )
                )
            elif policy.is_retryable(status):
                failed.append(key)
                store.update_push_status(run_id, key, "failed", message)
                audit.append(
                    AuditEntry(
                        run_id=run_id,
                        actor=Actor.AGENT,
                        action="push_failed",
                        entity=key,
                        before="pending",
                        after="failed",
                        disposition=Disposition.FLAGGED,
                        rationale=(
                            f"Still failing after {policy.PUSH_MAX_ATTEMPTS} attempts: "
                            f"{message}. Retryable, so it can be retried again later."
                        ),
                    )
                )
            else:
                rejected.append(key)
                store.update_push_status(run_id, key, "rejected", message)
                emit(f"{code} was rejected by the target system - asking")
                escalations.append(
                    Escalation(
                        run_id=run_id,
                        type=EscalationType.PUSH_REJECTED,
                        subject=f"push:{key}",
                        title=f"The target system refused {code}",
                        question=(
                            f"The target returned {status}: {message}. This is a business "
                            f"rejection rather than a transport problem, so retrying will "
                            f"return the same answer - it needs a decision."
                        ),
                        evidence={
                            "record_key": key,
                            "employee_code": code,
                            "status_code": status,
                            "target_message": message,
                            "record": {
                                k: ("****" if k in get_schema().pii_fields and v else v)
                                for k, v in (record.get("fields") or {}).items()
                            },
                        },
                        options=[
                            {
                                "value": "skip",
                                "label": "Leave it out",
                                "detail": "migrate everything else",
                            },
                            {
                                "value": "edit",
                                "label": "Change the record and resend",
                                "detail": "e.g. use a different employee code",
                            },
                        ],
                        affected_records=[key],
                    )
                )
    finally:
        if owns_client:
            client.close()

    if audit:
        store.append_audit(audit)
    if escalations:
        existing = store.list_escalations(run_id, status="open")
        store.replace_escalations(run_id, escalations)
        emit(f"{len(escalations)} record(s) need a decision before they can be loaded")

    emit(
        f"Pushed {len(succeeded)} record(s); {len(failed)} failed, {len(rejected)} rejected"
    )
    return {
        "pushed": len(succeeded),
        "push_failed": len(failed),
        "push_rejected": len(rejected),
        "failed_keys": failed,
        "rejected_keys": rejected,
    }


def rollback(
    run_id: str,
    keys: list[str],
    reason: str,
    client: httpx.Client | None = None,
    emit: Emit = lambda _: None,
) -> dict[str, Any]:
    """Undo pushes with compensating deletes, recording why."""
    settings = get_settings()
    store = get_store()
    base = settings.target_api_base.rstrip("/")
    owns_client = client is None
    client = client or httpx.Client()

    by_key = {r["key"]: r for r in store.list_records(run_id)}
    rolled_back: list[str] = []
    audit: list[AuditEntry] = []

    try:
        for key in keys:
            record = by_key.get(key)
            if not record or record.get("push_status") != "success":
                continue
            code = str((record.get("fields") or {}).get("employee_code") or key)
            try:
                response = client.delete(f"{base}/employees/{code}", timeout=15.0)
                ok = response.status_code < 400
            except httpx.RequestError as exc:
                ok, response = False, exc
            if not ok:
                store.log_push(run_id, key, 0, "rollback_failed", str(response)[:300])
                continue
            rolled_back.append(key)
            store.update_push_status(run_id, key, "rolled_back", reason)
            store.log_push(run_id, key, 0, "rolled_back", reason)
            audit.append(
                AuditEntry(
                    run_id=run_id,
                    actor=Actor.HUMAN,
                    action="rollback_record",
                    entity=key,
                    before="success",
                    after="rolled_back",
                    disposition=Disposition.AUTO,
                    rationale=f"Removed from the target system. Reason given: {reason}",
                )
            )
    finally:
        if owns_client:
            client.close()

    if audit:
        store.append_audit(audit)
    emit(f"Rolled back {len(rolled_back)} record(s)")
    return {"rolled_back": rolled_back, "count": len(rolled_back)}

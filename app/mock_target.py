"""A stand-in for the destination HRMS.

Real target systems fail in two importantly different ways, and this stub
reproduces both because the distinction drives the loader's whole retry policy:

    transient   the request never really happened - a timeout, a restart, a 503.
                Retrying is correct and usually works.
    business    the system understood the request and refused it, e.g. "that
                employee code already exists". Retrying is pointless; only a
                human can decide what to do instead.

Failures are injected deterministically by employee code rather than at random,
so a demo or a test produces the same outcome every time. A flaky stub would make
the retry path impossible to show reliably.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.settings import get_settings


class TargetSystem:
    """In-memory store standing in for the destination HRMS."""

    def __init__(self) -> None:
        self.employees: dict[str, dict[str, Any]] = {}
        self.attempts: dict[str, int] = {}
        self.idempotency: dict[str, str] = {}

    def reset(self) -> None:
        self.employees.clear()
        self.attempts.clear()
        self.idempotency.clear()

    def create(
        self, payload: dict[str, Any], idempotency_key: str | None = None
    ) -> tuple[int, dict[str, Any]]:
        settings = get_settings()
        code = str(payload.get("employee_code") or "").strip()

        if not code:
            return 422, {"error": "employee_code is required"}

        # A retried request that already succeeded returns the original result
        # rather than creating a second employee.
        if idempotency_key and idempotency_key in self.idempotency:
            existing = self.idempotency[idempotency_key]
            return 200, {"id": existing, "employee_code": code, "replayed": True}

        self.attempts[code] = self.attempts.get(code, 0) + 1

        # Transient: fails the first time, succeeds when retried.
        if code in settings.fail_codes and self.attempts[code] == 1:
            return 503, {
                "error": "upstream temporarily unavailable",
                "retryable": True,
                "employee_code": code,
            }

        # Business rejection: no amount of retrying changes the answer.
        if code in settings.reject_codes:
            return 409, {
                "error": f"employee_code {code} already exists in the target system",
                "retryable": False,
                "employee_code": code,
            }

        if code in self.employees:
            return 409, {
                "error": f"employee_code {code} already exists in the target system",
                "retryable": False,
                "employee_code": code,
            }

        record_id = f"TGT-{len(self.employees) + 1:05d}"
        self.employees[code] = {
            "id": record_id,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **payload,
        }
        if idempotency_key:
            self.idempotency[idempotency_key] = record_id
        return 201, {"id": record_id, "employee_code": code}

    def delete(self, code: str) -> tuple[int, dict[str, Any]]:
        if code not in self.employees:
            return 404, {"error": f"no employee {code} in the target system"}
        removed = self.employees.pop(code)
        self.idempotency = {k: v for k, v in self.idempotency.items() if v != removed["id"]}
        return 200, {"deleted": code, "id": removed["id"]}


_target = TargetSystem()


def get_target() -> TargetSystem:
    return _target


class EmployeePayload(BaseModel):
    employee_code: str = Field(..., description="Unique employee identifier")
    model_config = {"extra": "allow"}


router = APIRouter(prefix="/mock-target/v1", tags=["mock target"])


@router.post("/employees")
async def create_employee(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    payload = await request.json()
    status, body = get_target().create(payload, idempotency_key)
    if status >= 400:
        raise HTTPException(status_code=status, detail=body)
    return body


@router.delete("/employees/{employee_code}")
async def delete_employee(employee_code: str) -> Any:
    status, body = get_target().delete(employee_code)
    if status >= 400:
        raise HTTPException(status_code=status, detail=body)
    return body


@router.get("/employees")
async def list_employees() -> Any:
    target = get_target()
    return {"count": len(target.employees), "employees": list(target.employees.values())}


@router.post("/_reset")
async def reset_target() -> Any:
    get_target().reset()
    return {"reset": True}

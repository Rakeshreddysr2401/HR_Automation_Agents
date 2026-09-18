"""SQLite persistence.

Deliberately separate from the graph checkpointer. Checkpoints hold *control*
state - where the run is, what it is waiting for - and are written on every step,
so putting a few hundred employee records in them would balloon every checkpoint
with a copy of the dataset. The data lives here instead, and the graph carries a
run id.

One table outlives its run on purpose. `memory` records the answers a consultant
gave, keyed by the stable `subject` of the question, so the same column is never
queried twice - in this migration or the next client's. That is what turns review
from a recurring cost into something that compounds.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from app.models import AuditEntry, Escalation, EscalationStatus, TargetRecord
from app.settings import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    status      TEXT NOT NULL,
    files       TEXT NOT NULL,
    summary     TEXT
);
CREATE TABLE IF NOT EXISTS escalations (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    subject     TEXT NOT NULL,
    type        TEXT NOT NULL,
    status      TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    run_id      TEXT NOT NULL,
    subject     TEXT NOT NULL,
    answer      TEXT NOT NULL,
    decided_at  TEXT NOT NULL,
    PRIMARY KEY (run_id, subject)
);
CREATE TABLE IF NOT EXISTS audit (
    id          TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    at          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    entity      TEXT NOT NULL,
    before_val  TEXT,
    after_val   TEXT,
    rationale   TEXT,
    disposition TEXT
);
CREATE TABLE IF NOT EXISTS records (
    run_id      TEXT NOT NULL,
    key         TEXT NOT NULL,
    payload     TEXT NOT NULL,
    push_status TEXT NOT NULL,
    PRIMARY KEY (run_id, key)
);
CREATE TABLE IF NOT EXISTS push_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    record_key  TEXT NOT NULL,
    attempt     INTEGER NOT NULL,
    status      TEXT NOT NULL,
    detail      TEXT,
    at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory (
    subject     TEXT PRIMARY KEY,
    answer      TEXT NOT NULL,
    column_key  TEXT,
    target      TEXT,
    updated_at  TEXT NOT NULL,
    times_used  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit(run_id);
CREATE INDEX IF NOT EXISTS idx_esc_run ON escalations(run_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # --- runs --------------------------------------------------------------

    def create_run(self, run_id: str, files: list[str]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO runs (run_id, created_at, status, files) VALUES (?,?,?,?)",
                (run_id, _now(), "running", json.dumps(files)),
            )
            self._conn.commit()

    def set_run_status(self, run_id: str, status: str, summary: dict | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET status = ?, summary = ? WHERE run_id = ?",
                (status, json.dumps(summary) if summary else None, run_id),
            )
            self._conn.commit()

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return {
            "run_id": row["run_id"],
            "created_at": row["created_at"],
            "status": row["status"],
            "files": json.loads(row["files"]),
            "summary": json.loads(row["summary"]) if row["summary"] else None,
        }

    def list_runs(self, limit: int = 25) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "run_id": r["run_id"],
                "created_at": r["created_at"],
                "status": r["status"],
                "files": json.loads(r["files"]),
                "summary": json.loads(r["summary"]) if r["summary"] else None,
            }
            for r in rows
        ]

    # --- escalations -------------------------------------------------------

    def replace_escalations(self, run_id: str, escalations: list[Escalation]) -> None:
        """Rewrite this run's open questions.

        The pipeline is re-run from scratch whenever a decision arrives, so the
        question set is regenerated each time. Resolved questions are preserved
        as history; the open set is replaced wholesale.
        """
        with self._lock:
            self._conn.execute(
                "DELETE FROM escalations WHERE run_id = ? AND status = ?",
                (run_id, EscalationStatus.OPEN.value),
            )
            for escalation in escalations:
                self._conn.execute(
                    "INSERT OR REPLACE INTO escalations "
                    "(id, run_id, subject, type, status, payload, created_at, resolved_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        escalation.id,
                        run_id,
                        escalation.subject,
                        escalation.type.value,
                        escalation.status.value,
                        json.dumps(escalation.as_dict()),
                        escalation.created_at,
                        escalation.resolved_at,
                    ),
                )
            self._conn.commit()

    def list_escalations(self, run_id: str, status: str | None = None) -> list[dict]:
        query = "SELECT payload FROM escalations WHERE run_id = ?"
        params: list[Any] = [run_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def mark_resolved(self, run_id: str, subject: str, answer: Any) -> None:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, payload FROM escalations WHERE run_id = ? AND subject = ?",
                (run_id, subject),
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                payload["status"] = EscalationStatus.RESOLVED.value
                payload["resolution"] = answer
                payload["resolved_at"] = _now()
                self._conn.execute(
                    "UPDATE escalations SET status = ?, payload = ?, resolved_at = ? WHERE id = ?",
                    (EscalationStatus.RESOLVED.value, json.dumps(payload), _now(), row["id"]),
                )
            self._conn.commit()

    # --- decisions ---------------------------------------------------------

    def save_decision(self, run_id: str, subject: str, answer: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO decisions (run_id, subject, answer, decided_at) "
                "VALUES (?,?,?,?)",
                (run_id, subject, json.dumps(answer), _now()),
            )
            self._conn.commit()

    def get_decisions(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT subject, answer FROM decisions WHERE run_id = ?", (run_id,)
            ).fetchall()
        return {r["subject"]: json.loads(r["answer"]) for r in rows}

    # --- audit -------------------------------------------------------------

    def replace_audit(self, run_id: str, entries: list[AuditEntry]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM audit WHERE run_id = ?", (run_id,))
            self._conn.executemany(
                "INSERT OR REPLACE INTO audit "
                "(id, run_id, at, actor, action, entity, before_val, after_val, rationale, disposition) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        e.id,
                        run_id,
                        e.at,
                        e.actor.value,
                        e.action,
                        e.entity,
                        json.dumps(e.before) if e.before is not None else None,
                        json.dumps(e.after) if e.after is not None else None,
                        e.rationale,
                        e.disposition.value if e.disposition else None,
                    )
                    for e in entries
                ],
            )
            self._conn.commit()

    def append_audit(self, entries: list[AuditEntry]) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO audit "
                "(id, run_id, at, actor, action, entity, before_val, after_val, rationale, disposition) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        e.id,
                        e.run_id,
                        e.at,
                        e.actor.value,
                        e.action,
                        e.entity,
                        json.dumps(e.before) if e.before is not None else None,
                        json.dumps(e.after) if e.after is not None else None,
                        e.rationale,
                        e.disposition.value if e.disposition else None,
                    )
                    for e in entries
                ],
            )
            self._conn.commit()

    def list_audit(self, run_id: str, limit: int = 1000) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM audit WHERE run_id = ? ORDER BY at, id LIMIT ?", (run_id, limit)
            ).fetchall()
        return [
            {
                "id": r["id"],
                "at": r["at"],
                "actor": r["actor"],
                "action": r["action"],
                "entity": r["entity"],
                "before": json.loads(r["before_val"]) if r["before_val"] else None,
                "after": json.loads(r["after_val"]) if r["after_val"] else None,
                "rationale": r["rationale"],
                "disposition": r["disposition"],
            }
            for r in rows
        ]

    # --- records -----------------------------------------------------------

    def replace_records(self, run_id: str, records: list[TargetRecord]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM records WHERE run_id = ?", (run_id,))
            self._conn.executemany(
                "INSERT OR REPLACE INTO records (run_id, key, payload, push_status) VALUES (?,?,?,?)",
                [(run_id, r.key, json.dumps(r.as_dict()), r.push_status) for r in records],
            )
            self._conn.commit()

    def update_push_status(self, run_id: str, key: str, status: str, detail: str = "") -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM records WHERE run_id = ? AND key = ?", (run_id, key)
            ).fetchone()
            if row:
                payload = json.loads(row["payload"])
                payload["push_status"] = status
                payload["push_detail"] = detail
                self._conn.execute(
                    "UPDATE records SET payload = ?, push_status = ? WHERE run_id = ? AND key = ?",
                    (json.dumps(payload), status, run_id, key),
                )
            self._conn.commit()

    def list_records(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM records WHERE run_id = ? ORDER BY key", (run_id,)
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]

    def log_push(self, run_id: str, key: str, attempt: int, status: str, detail: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO push_log (run_id, record_key, attempt, status, detail, at) "
                "VALUES (?,?,?,?,?,?)",
                (run_id, key, attempt, status, detail, _now()),
            )
            self._conn.commit()

    def list_push_log(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM push_log WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # --- memory (outlives the run) -----------------------------------------

    def remember(self, subject: str, answer: Any) -> None:
        """Persist a human answer so the same question is never asked twice.

        Only column-identification answers generalise. Which column holds the
        work email is a fact about that export format and will be true for the
        next file the same system produces. Whether two particular employees are
        the same person is not - it is about those two people, and remembering it
        would be wrong.
        """
        column_key: str | None = None
        target: str | None = None
        if subject.startswith("map:"):
            _, _file, column = subject.split(":", 2)
            column_key = column.strip().lower().replace("_", " ")
            target = str(answer)
        elif subject.startswith("contest:"):
            _, _file, field = subject.split(":", 2)
            column_key = str(answer).strip().lower().replace("_", " ")
            target = field
        if not column_key or not target or target == "__ignore__":
            return
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO memory (subject, answer, column_key, target, updated_at, times_used) "
                "VALUES (?,?,?,?,?, COALESCE((SELECT times_used FROM memory WHERE subject = ?), 0))",
                (subject, json.dumps(answer), column_key, target, _now(), subject),
            )
            self._conn.commit()

    def remembered_mappings(self) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT column_key, target FROM memory WHERE column_key IS NOT NULL"
            ).fetchall()
        return {r["column_key"]: r["target"] for r in rows}

    def note_memory_used(self, column_keys: list[str]) -> None:
        if not column_keys:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE memory SET times_used = times_used + 1 WHERE column_key = ?",
                [(key,) for key in column_keys],
            )
            self._conn.commit()

    def list_memory(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM memory ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {
                "subject": r["subject"],
                "column_key": r["column_key"],
                "target": r["target"],
                "updated_at": r["updated_at"],
                "times_used": r["times_used"],
            }
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_store: Store | None = None


def configure_store(store: Store) -> None:
    global _store
    _store = store


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store(get_settings().db_path)
    return _store

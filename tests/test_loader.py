"""Pushing, retrying, and knowing which failures are worth retrying.

The mock target is driven through an httpx MockTransport rather than a live
server, so these run anywhere and in milliseconds while still exercising the real
loader code path, status handling and audit writes.
"""

import json

import httpx
import pytest

from app.agents import loader
from app.mock_target import TargetSystem
from app.models import TargetRecord
from app.settings import get_settings
from app.store import get_store


@pytest.fixture
def target():
    return TargetSystem()


@pytest.fixture
def client(target):
    """An httpx client wired straight to the mock target's logic."""

    def handle(request: httpx.Request) -> httpx.Response:
        code = request.url.path.rsplit("/", 1)[-1]
        if request.method == "DELETE":
            status, body = target.delete(code)
        else:
            payload = json.loads(request.content or b"{}")
            status, body = target.create(
                payload, request.headers.get("Idempotency-Key")
            )
        # FastAPI wraps error bodies in "detail"; mirror that so the loader sees
        # exactly the shape it sees in production.
        if status >= 400:
            body = {"detail": body}
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handle))


def record(code: str, **fields) -> dict:
    return TargetRecord(
        key=code,
        fields={"employee_code": code, "first_name": "Test", **fields},
        sources=[f"file.csv#{code}"],
    ).as_dict()


@pytest.fixture
def seeded_store(isolated_store):
    isolated_store.create_run("run1", ["file.csv"])
    return isolated_store


class TestPushing:
    def test_a_clean_record_lands(self, client, seeded_store, target):
        seeded_store.replace_records("run1", [TargetRecord(key="E1", fields={"employee_code": "E1"})])
        outcome = loader.push_records("run1", [record("E1")], client=client)
        assert outcome["pushed"] == 1
        assert "E1" in target.employees

    def test_a_transient_failure_is_retried_and_succeeds(self, client, seeded_store, target, monkeypatch):
        """E1015 is configured to fail once, then work. The loader should not
        bother a human about something a retry fixes."""
        monkeypatch.setattr(get_settings(), "target_fail_codes", "E1015")
        get_settings.cache_clear()
        monkeypatch.setenv("TARGET_FAIL_CODES", "E1015")
        monkeypatch.setenv("TARGET_REJECT_CODES", "")
        get_settings.cache_clear()

        seeded_store.replace_records("run1", [TargetRecord(key="E1015", fields={"employee_code": "E1015"})])
        outcome = loader.push_records("run1", [record("E1015")], client=client)

        assert outcome["pushed"] == 1, "should have recovered on the retry"
        assert target.attempts["E1015"] == 2, "exactly one retry, not a loop"

    def test_a_business_rejection_is_escalated_not_retried(self, client, seeded_store, monkeypatch, target):
        """'This employee code already exists' does not become false on attempt
        three. Retrying is just a slower way to fail."""
        monkeypatch.setenv("TARGET_REJECT_CODES", "E1021")
        monkeypatch.setenv("TARGET_FAIL_CODES", "")
        get_settings.cache_clear()

        seeded_store.replace_records("run1", [TargetRecord(key="E1021", fields={"employee_code": "E1021"})])
        outcome = loader.push_records("run1", [record("E1021")], client=client)

        assert outcome["push_rejected"] == 1
        assert target.attempts["E1021"] == 1, "a 4xx must not be retried at all"

        open_questions = seeded_store.list_escalations("run1", status="open")
        assert any(e["type"] == "push_rejected" for e in open_questions)

    def test_an_unreachable_target_is_treated_as_transient(self, seeded_store):
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = httpx.Client(transport=httpx.MockTransport(refuse))
        seeded_store.replace_records("run1", [TargetRecord(key="E1", fields={"employee_code": "E1"})])
        outcome = loader.push_records("run1", [record("E1")], client=client)
        assert outcome["push_failed"] == 1, "the request never landed, so it is retryable"

    def test_a_retry_after_an_ambiguous_timeout_cannot_duplicate(self, client, seeded_store, target):
        """The idempotency key is what stops a 'safe' retry creating two people."""
        seeded_store.replace_records("run1", [TargetRecord(key="E1", fields={"employee_code": "E1"})])
        loader.push_records("run1", [record("E1")], client=client)
        loader.push_records("run1", [record("E1")], client=client)
        assert len(target.employees) == 1


class TestRollback:
    def test_it_removes_the_record_and_says_why(self, client, seeded_store, target):
        pushed = TargetRecord(key="E1", fields={"employee_code": "E1"})
        seeded_store.replace_records("run1", [pushed])
        loader.push_records("run1", [record("E1")], client=client)
        assert "E1" in target.employees

        outcome = loader.rollback("run1", ["E1"], "loaded into the wrong legal entity", client=client)

        assert outcome["count"] == 1
        assert "E1" not in target.employees

        reasons = [e["rationale"] for e in seeded_store.list_audit("run1") if e["action"] == "rollback_record"]
        assert any("wrong legal entity" in r for r in reasons), "the reason must reach the audit trail"

    def test_it_ignores_records_that_never_landed(self, client, seeded_store):
        seeded_store.replace_records("run1", [TargetRecord(key="E9", fields={"employee_code": "E9"})])
        assert loader.rollback("run1", ["E9"], "never pushed", client=client)["count"] == 0

    def test_already_gone_counts_as_rolled_back(self, client, seeded_store, target):
        """A compensating delete is idempotent: if the target no longer holds the
        record (say the mock target restarted), the rollback's goal is already met
        and the store must say so rather than leaving the record marked loaded."""
        seeded_store.replace_records("run1", [TargetRecord(key="E1", fields={"employee_code": "E1"})])
        seeded_store.update_push_status("run1", "E1", "success", "TGT-1")
        assert "E1" not in target.employees

        outcome = loader.rollback("run1", ["E1"], "wrong entity", client=client)

        assert outcome["count"] == 1 and outcome["failed"] == []
        assert seeded_store.list_records("run1")[0]["push_status"] == "rolled_back"

    def test_a_rolled_back_record_can_be_pushed_again_on_request(self, client, seeded_store, target):
        seeded_store.replace_records("run1", [TargetRecord(key="E1", fields={"employee_code": "E1"})])
        loader.push_records("run1", [record("E1")], client=client)
        loader.rollback("run1", ["E1"], "mistake", client=client)
        assert "E1" not in target.employees

        outcome = loader.push_records("run1", [record("E1")], client=client)

        assert outcome["pushed"] == 1, "the delete released the idempotency key"
        assert "E1" in target.employees


class TestRejectionFlood:
    """Forty identical rejections are one question about the batch."""

    def _seed(self, store, target, n):
        recs = [record(f"E{i:04d}") for i in range(1, n + 1)]
        store.replace_records("run1", [TargetRecord(key=r["key"], fields=r["fields"]) for r in recs])
        # The target already holds every one of them - a re-run.
        for r in recs:
            target.create({"employee_code": r["key"], "first_name": "Test"})
        return recs

    def test_it_asks_once_not_once_per_record(self, client, seeded_store, target):
        recs = self._seed(seeded_store, target, 10)

        outcome = loader.push_records("run1", recs, client=client)

        assert outcome["push_rejected"] == 10
        open_ = seeded_store.list_escalations("run1", status="open")
        assert len(open_) == 1
        assert open_[0]["type"] == "batch_anomaly"
        assert open_[0]["subject"] == "batch:push_rejected"
        assert set(open_[0]["affected_records"]) == {r["key"] for r in recs}

    def test_a_few_rejections_stay_individual(self, client, seeded_store, target):
        """Below the flood threshold, per-record cards are the useful shape."""
        recs = self._seed(seeded_store, target, 3)
        outcome = loader.push_records("run1", recs, client=client)
        assert outcome["push_rejected"] == 3
        assert {e["type"] for e in seeded_store.list_escalations("run1", status="open")} == {"push_rejected"}

    def test_choosing_review_expands_it_again(self, client, seeded_store, target):
        recs = self._seed(seeded_store, target, 10)
        loader.push_records("run1", recs, client=client, decisions={"batch:push_rejected": "review"})
        open_ = seeded_store.list_escalations("run1", status="open")
        assert len(open_) == 10 and all(e["type"] == "push_rejected" for e in open_)

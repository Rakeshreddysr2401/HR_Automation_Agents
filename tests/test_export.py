"""The migrated dataset as a file - the deliverable a consultant hands over."""

import io

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import router
from app.models import TargetRecord


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed(store):
    store.create_run("run1", ["a.csv", "b.xlsx"])
    store.replace_records(
        "run1",
        [
            TargetRecord(
                key="E1",
                fields={"employee_code": "E1", "first_name": "Mia", "last_name": "Brown", "pan": "ABCDE1234F"},
                sources=["a.csv#2", "b.xlsx#2"],
            ),
            TargetRecord(key="E2", fields={"employee_code": "E2", "first_name": "Sam"}, sources=["a.csv#3"]),
        ],
    )
    store.update_push_status("run1", "E1", "success", "TGT-1")
    store.update_push_status("run1", "E2", "skipped", "")


class TestExport:
    def test_csv_has_every_schema_column_plus_the_outcome(self, isolated_store):
        _seed(isolated_store)
        response = _client().get("/api/runs/run1/export?format=csv")
        assert response.status_code == 200
        frame = pd.read_csv(io.StringIO(response.text), dtype=str, keep_default_na=False)
        assert list(frame.columns)[:3] == ["employee_code", "first_name", "last_name"]
        assert list(frame.columns)[-3:] == ["migration_result", "target_id", "source_rows"]
        mia = frame[frame.employee_code == "E1"].iloc[0]
        assert mia.migration_result == "success" and mia.target_id == "TGT-1"
        assert mia.source_rows == "a.csv#2; b.xlsx#2"
        assert mia.pan == "ABCDE1234F", "the deliverable carries real values, not masks"
        assert frame[frame.employee_code == "E2"].iloc[0].migration_result == "skipped"

    def test_xlsx_opens_as_a_spreadsheet(self, isolated_store):
        _seed(isolated_store)
        response = _client().get("/api/runs/run1/export?format=xlsx")
        assert response.status_code == 200
        frame = pd.read_excel(io.BytesIO(response.content), dtype=str)
        assert len(frame) == 2 and "migration_result" in frame.columns

    def test_unknown_run_is_a_404(self, isolated_store):
        assert _client().get("/api/runs/nope/export").status_code == 404

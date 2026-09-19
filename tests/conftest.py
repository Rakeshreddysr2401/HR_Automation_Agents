"""Test fixtures.

Two kinds of test live here. Most are hermetic and never touch a model server: the
policy boundaries, the date reader, the loader's retry rules and the PII guarantees
are all deterministic, so they must run anywhere.

The golden-run test is different. It asserts the exact set of questions the agent
raises on the sample data, which depends on real semantic scoring, so it skips when
no embedding model is reachable rather than quietly asserting something weaker.
"""

from __future__ import annotations

import pytest

from app import llm
from app.settings import get_settings
from app.store import Store, configure_store


@pytest.fixture(autouse=True)
def isolated_store():
    """Every test gets its own in-memory database."""
    store = Store(":memory:")
    configure_store(store)
    yield store
    store.close()


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def no_models(monkeypatch):
    """Force the fully degraded path: no embeddings, no reasoning."""
    monkeypatch.setattr(llm, "embed", lambda *a, **k: None)
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: None)


@pytest.fixture
def quiet_reasoning(monkeypatch):
    """Keep embeddings real but skip the model that only writes explanations."""
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: None)


def embeddings_available() -> bool:
    try:
        return llm.available("embedding")
    except Exception:  # noqa: BLE001
        return False


needs_embeddings = pytest.mark.skipif(
    not embeddings_available(),
    reason="needs a reachable embedding model; semantic scoring cannot be faked meaningfully",
)

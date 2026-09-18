"""Runtime configuration. Everything env-overridable, nothing required."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- storage -----------------------------------------------------------
    db_path: str = str(ROOT / "migration.db")
    checkpoint_path: str = str(ROOT / "checkpoints.db")
    upload_dir: str = str(ROOT / "uploads")
    schema_path: str = str(ROOT / "schema" / "target_employee.yaml")

    # --- models ------------------------------------------------------------
    # Open-source models only, served locally. Chat and embeddings are
    # configured independently because they usually live on different servers:
    # a llama.cpp host typically serves one chat model and no embedding model,
    # so embeddings stay on an Ollama instance elsewhere.
    #
    # provider is "ollama" (native /api) or "openai" (OpenAI-compatible, which
    # covers llama.cpp, vLLM and LM Studio).
    reasoning_provider: str = "ollama"
    reasoning_base_url: str = "http://localhost:11434"
    reasoning_model: str = "gemma4:latest"
    reasoning_api_key: str = "not-needed"

    embedding_provider: str = "ollama"
    embedding_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    embedding_api_key: str = "not-needed"

    llm_timeout_seconds: float = 45.0
    llm_enabled: bool = True

    # --- mock target -------------------------------------------------------
    target_api_base: str = "http://127.0.0.1:8000/mock-target/v1"
    # Deterministic failure injection so demos reproduce exactly.
    target_fail_codes: str = "E1015,E1031"   # transient 503, succeeds on retry
    target_reject_codes: str = "E1021"       # hard 409, must be escalated

    @property
    def fail_codes(self) -> set[str]:
        return {c.strip() for c in self.target_fail_codes.split(",") if c.strip()}

    @property
    def reject_codes(self) -> set[str]:
        return {c.strip() for c in self.target_reject_codes.split(",") if c.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()

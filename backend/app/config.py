"""
Environment-based configuration for CodePilot.

All secrets and provider selection come from environment variables.
Never hard-code API keys or tokens anywhere in this codebase.
"""
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM provider abstraction ---
    llm_provider: str = "openai"          # openai | groq | anyscale | together | ...
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None       # override for OpenAI-compatible endpoints
    llm_api_key: str | None = None        # generic fallback

    # Provider-specific keys (read if llm_api_key is not set)
    openai_api_key: str | None = None
    groq_api_key: str | None = None

    # --- Persistence (Phase 5+) ---
    # Phase 5 requires a real PostgreSQL database - the LangGraph
    # checkpointer (app/db/checkpointer.py) is Postgres-backed, not
    # SQLite-compatible. This default matches the local dev setup described
    # in the README (createuser/createdb codepilot) - override via
    # DATABASE_URL for anything beyond a single developer's machine.
    database_url: str = "postgresql+psycopg2://codepilot:codepilot_dev_password@localhost:5432/codepilot"
    redis_url: str = "redis://localhost:6379/0"

    # --- Agent limits ---
    max_debug_retries: int = 3
    max_review_cycles: int = 2
    max_agent_iterations: int = 25
    tool_timeout_seconds: int = 60

    # --- Docker sandbox (Phase 2) ---
    use_docker_sandbox: bool = True
    docker_image: str = "python:3.12-slim"
    docker_mem_limit: str = "512m"
    docker_nano_cpus: int = 1_000_000_000  # 1.0 CPU
    docker_network_disabled: bool = True

    # --- Workspace ---
    workspace_root: str = "/tmp/codepilot_workspaces"

    # --- GitHub (Phase 4+) ---
    github_token: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None

    # --- Observability (Phase 7+) ---
    langchain_tracing_v2: bool = False
    langchain_api_key: str | None = None
    langchain_project: str = "codepilot"

    def resolved_llm_api_key(self) -> str | None:
        """Pick the right key for the configured provider."""
        if self.llm_api_key:
            return self.llm_api_key
        if self.llm_provider == "groq":
            return self.groq_api_key
        if self.llm_provider == "openai":
            return self.openai_api_key
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()

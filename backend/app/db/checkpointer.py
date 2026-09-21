"""
Postgres-backed LangGraph checkpointer.

Replaces the in-memory MemorySaver from Phases 1-4. This is what makes a
paused human-approval interrupt (and the whole graph's state) survive an
actual backend restart — verified explicitly, not assumed: see the Phase 5
README section for a live restart-and-resume test.
"""
from __future__ import annotations

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.config import get_settings

# Our CodePilotState carries Pydantic models (Plan, CodeChange, TestResult,
# ReviewResult, RelevantFile) as values. Without an explicit allowlist,
# JsonPlusSerializer logs a deprecation warning now and will refuse to
# deserialize them in a future langgraph-checkpoint release.
_serde = JsonPlusSerializer(allowed_msgpack_modules=[
    ("app.state", "Plan"),
    ("app.state", "CodeChange"),
    ("app.state", "TestResult"),
    ("app.state", "ReviewResult"),
    ("app.state", "RelevantFile"),
])

_checkpointer: PostgresSaver | None = None
_conn_ctx = None  # must stay referenced, or GC closes the underlying connection
_setup_done = False


def get_checkpointer() -> PostgresSaver:
    global _checkpointer, _conn_ctx, _setup_done
    if _checkpointer is None:
        settings = get_settings()
        dsn = settings.database_url

        if dsn.startswith("sqlite"):
            raise RuntimeError(
                "DATABASE_URL is set to a SQLite URL, but Phase 5's LangGraph "
                "checkpointer requires PostgreSQL - it is not SQLite-compatible. "
                "Set DATABASE_URL to a postgresql:// or postgresql+psycopg2:// URL "
                "(see backend/.env.example) and make sure the Postgres server is "
                "running before starting the app."
            )
        if not dsn.startswith("postgres"):
            raise RuntimeError(
                f"DATABASE_URL does not look like a PostgreSQL URL: {dsn!r}. "
                "Phase 5's checkpointer requires postgresql:// or "
                "postgresql+psycopg2://. See backend/.env.example."
            )

        # PostgresSaver wants a psycopg3-style DSN; SQLAlchemy's
        # postgresql+psycopg2:// URL form needs normalizing.
        pg_dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
        try:
            _conn_ctx = PostgresSaver.from_conn_string(pg_dsn)
            _checkpointer = _conn_ctx.__enter__()  # kept open for process lifetime via _conn_ctx
        except Exception as exc:
            raise RuntimeError(
                f"Could not connect to PostgreSQL at the configured DATABASE_URL "
                f"to set up the LangGraph checkpointer. Is Postgres running and "
                f"reachable? Underlying error: {exc}"
            ) from exc

        _checkpointer.serde = _serde
        if not _setup_done:
            _checkpointer.setup()  # idempotent — creates checkpoint tables if missing
            _setup_done = True
    return _checkpointer

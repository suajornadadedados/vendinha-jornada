"""Configuration, read once, typed at the edge.

Pydantic on every boundary is a project rule (CLAUDE.md), and the environment is a
boundary like any other: a missing `DATABASE_URL` should fail at import with a name
and a reason, not at the first request with a `NoneType` somewhere in psycopg.

The `.env` is resolved from the repository root, not from the working directory —
the API is started from `backend/`, the tests run from the root, and `make` from
either. A config that depends on where you stood when you typed the command is a
config that works on one machine.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Everything S-02 reads from the environment. See `.env.example` for the prose."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # `model_` is a Pydantic-reserved prefix and `LLM_MODEL` would collide with
        # it in a confusing way. Naming the field `llm_model` and pointing it at the
        # env var explicitly keeps both names readable.
        populate_by_name=True,
    )

    database_url: str = "postgresql://vendinha:vendinha@127.0.0.1:5432/vendinha"

    # `provedor:modelo`. The code never branches on the provider — see ADR-012.
    llm_model: str = "anthropic:claude-haiku-4-5"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached: reading the file on every request would be an I/O per request."""
    return Settings()

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

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"

# Two readers of the same file, and both are needed. `Settings` below reads it for
# our own configuration; `load_dotenv` puts it in the process environment because
# provider SDKs read `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` from there and know
# nothing about our settings object. `override=False` so a variable already set in
# the shell — which is how CI and the containers pass secrets — always wins.
load_dotenv(ENV_FILE, override=False)


class Settings(BaseSettings):
    """Everything S-02 reads from the environment. See `.env.example` for the prose."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        # `model_` is a Pydantic-reserved prefix and `LLM_MODEL` would collide with
        # it in a confusing way. Naming the field `llm_model` and pointing it at the
        # env var explicitly keeps both names readable.
        populate_by_name=True,
    )

    # `local` is the only environment where the configuration endpoints accept a
    # write. There is no authentication in this project yet, and an unauthenticated
    # route that stores a provider credential is not something to ship to a public
    # host and remember to fix later. See D-8 in the S-02 spec.
    app_env: str = "local"

    # Lido por `install_log_redaction`, que é o único ponto do processo que mexe
    # no logger raiz. Estava no `.env.example` marcado (S-02) e nenhum código o
    # lia — ressalva R-5 da verificação da S-02.
    log_level: str = "INFO"

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    database_url: str = "postgresql://vendinha:vendinha@127.0.0.1:5432/vendinha"

    # `provedor:modelo`. The code never branches on the provider — see ADR-012.
    llm_model: str = "anthropic:claude-haiku-4-5"

    # Qdrant: where the catalogue is ranked. No fact lives there — the index
    # returns ids by similarity and Postgres asserts the rest (S-03, `catalogo.py`).
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "catalogo"

    # What turns into a vector, in the same `provedor:modelo` shape as the chat
    # model. Anthropic offers no embedding endpoint, so this requires an
    # OPENAI_API_KEY even on an instance that only talks through Anthropic — that
    # is S-03 D-1, and the cost is written there and in `.env.example` rather than
    # discovered here.
    embedding_model: str = "openai:text-embedding-3-small"

    # The model that judges the eval cases, `provedor:modelo`. Unset means the
    # judge is the agent's own model, and the runner says so out loud: a model
    # grading its own output is a known bias, and a ruler must not hide it from
    # whoever reads the report (S-03, ADR-006).
    evals_judge_model: str | None = None

    # `LANGFUSE_HOST` is the v3 name and `LANGFUSE_BASE_URL` is the current one.
    # Both are accepted so an existing `.env` keeps working; see D-1 in the spec.
    langfuse_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LANGFUSE_BASE_URL", "LANGFUSE_HOST"),
    )
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    # Token, not currency — D-2 in the spec. A price table per model would be
    # several tables now that the provider is configurable, all rotting quietly.
    session_budget_tokens: int = 60_000

    # Ceiling for one external call: a tool when they arrive in S-03, and today
    # the wait for the model's first token.
    tool_timeout_seconds: float = 20.0

    # Fernet key that encrypts the stored provider credential (ADR-012). Absent
    # means writes are refused — never that the secret is stored in the clear.
    config_encryption_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached: reading the file on every request would be an I/O per request."""
    return Settings()

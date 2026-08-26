"""The instance configuration: one row, and the two implementations behind it.

`ConfigStore` is a port in the same sense the LangGraph checkpointer is one — the
boundary to Postgres, with a second in-memory implementation that satisfies the
same protocol. That is what lets the endpoint tests run with no container without
mocking anything internal (`docs/testes.md` §4).

**One row, not one per user.** There is no user model and no authentication in
S-02, so ADR-012 is explicit that what is persisted is the configuration of the
*instance*: whoever runs this vendinha sets their key once. Multi-tenancy would be
a new decision and a new ADR, not a column added quietly.

**The environment is a fallback, never an override.** A key in `.env` makes a
provider available with zero setup — the RNF-1 quickstart path — and anything
stored through the API wins over it.
"""

from dataclasses import dataclass, field
from typing import Protocol

import psycopg

from vendinha.credentials import Vault

# `id smallint PRIMARY KEY CHECK (id = 1)` is the whole single-row guarantee: the
# database refuses a second row, so no code path has to remember to update instead
# of insert.
SCHEMA = """
CREATE TABLE IF NOT EXISTS instance_config (
    id             smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    selected_model text,
    credentials    bytea,
    updated_at     timestamptz NOT NULL DEFAULT now()
)
"""


@dataclass(frozen=True)
class InstanceConfig:
    """What the rest of the application is allowed to know about the configuration.

    Note what is absent: the secrets. Callers get the set of providers that *have*
    a credential, never the credentials themselves — a shape that makes leaking one
    through a response require deliberate effort rather than forgetfulness.
    """

    selected_model: str | None = None
    credentials: dict[str, str] = field(default_factory=dict)

    @property
    def providers_configured(self) -> frozenset[str]:
        return frozenset(self.credentials)


class ConfigStore(Protocol):
    async def setup(self) -> None: ...

    async def load(self) -> InstanceConfig: ...

    async def save(self, *, selected_model: str | None, credentials: dict[str, str]) -> None: ...


class InMemoryConfigStore:
    """The store the tests run against. Not a mock — a second real implementation."""

    def __init__(self) -> None:
        self._config = InstanceConfig()

    async def setup(self) -> None:
        return None

    async def load(self) -> InstanceConfig:
        return self._config

    async def save(self, *, selected_model: str | None, credentials: dict[str, str]) -> None:
        self._config = InstanceConfig(selected_model=selected_model, credentials=dict(credentials))


class PostgresConfigStore:
    """The real one. Holds bytes it cannot read; the `Vault` owns the cryptography."""

    def __init__(self, dsn: str, vault: Vault) -> None:
        self._dsn = dsn
        self._vault = vault

    async def setup(self) -> None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            await conn.execute(SCHEMA)

    async def load(self) -> InstanceConfig:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            row = await (
                await conn.execute("SELECT selected_model, credentials FROM instance_config")
            ).fetchone()

        if row is None:
            return InstanceConfig()

        selected_model, blob = row
        # Decryption is deliberately not guarded here: a blob that will not open is
        # a rotated key, and answering "no credentials configured" would silently
        # send the operator to re-enter keys that are already there.
        return InstanceConfig(selected_model=selected_model, credentials=self._vault.open(blob))

    async def save(self, *, selected_model: str | None, credentials: dict[str, str]) -> None:
        blob = self._vault.seal(credentials) if credentials else None
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            await conn.execute(
                """
                INSERT INTO instance_config (id, selected_model, credentials, updated_at)
                VALUES (1, %s, %s, now())
                ON CONFLICT (id) DO UPDATE
                   SET selected_model = EXCLUDED.selected_model,
                       credentials    = EXCLUDED.credentials,
                       updated_at     = now()
                """,
                (selected_model, blob),
            )

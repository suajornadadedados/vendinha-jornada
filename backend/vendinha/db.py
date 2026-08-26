"""Postgres: the checkpointer, the instance configuration, and the DSN they share.

`AsyncPostgresSaver` creates its own tables, which makes `setup()` a migration —
and migrations do not belong in the startup path of a web process. Two replicas
booting together would race to create the same table, and the loser crashes on a
Tuesday for a reason nobody can reproduce. So it is an explicit command:

    make db-setup

Run it once after `make up`, and again whenever LangGraph ships a schema change.
"""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from vendinha import runtime
from vendinha.catalogo import PostgresCatalogo
from vendinha.config import get_settings
from vendinha.config_store import PostgresConfigStore
from vendinha.credentials import Vault
from vendinha.redaction import redact

# Without it, libpq waits forever on a host that accepts the packet and never
# answers. The classic one on Windows is `localhost` resolving to ::1 while the
# container publishes on 127.0.0.1: no refusal, no error, just a process stuck in
# "Waiting for application startup" against a database that is perfectly healthy.
#
# With the timeout, libpq gives up on ::1 and falls back to IPv4 — so `localhost`
# starts working, five seconds later, on every single connection. That is the point
# worth keeping in mind: this bound turns an infinite hang into a slow success, and
# a slow success is the harder bug to notice. `.env.example` uses 127.0.0.1 so the
# fallback never has to happen.
CONNECT_TIMEOUT_SECONDS = 5


def with_connect_timeout(dsn: str) -> str:
    """Add `connect_timeout` to a DSN that does not set one. Never overrides."""
    parts = urlsplit(dsn)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "connect_timeout" in query:
        return dsn
    query["connect_timeout"] = str(CONNECT_TIMEOUT_SECONDS)
    return urlunsplit(parts._replace(query=urlencode(query)))


@asynccontextmanager
async def open_checkpointer(database_url: str | None = None) -> AsyncIterator[AsyncPostgresSaver]:
    """Open a checkpointer bound to the application's Postgres, and close it after."""
    dsn = with_connect_timeout(database_url or get_settings().database_url)
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        yield saver


async def setup() -> None:
    """Create every table the application owns. Idempotent — safe to run again."""
    settings = get_settings()
    dsn = with_connect_timeout(settings.database_url)
    async with open_checkpointer() as saver:
        await saver.setup()
    await PostgresConfigStore(dsn, Vault(settings.config_encryption_key)).setup()
    # The table only — filling it is `make seed`, because a schema migration and a
    # data load fail for different reasons and are fixed by different people.
    await PostgresCatalogo(dsn).setup()


def main() -> int:
    try:
        runtime.run(setup())
    except Exception as error:
        # A DSN typo and a container that is not up produce very different fixes,
        # and psycopg says which is which. Printing the exception beats a traceback
        # for the person who just ran `make db-setup` for the first time.
        print(f"failed to prepare Postgres: {error}", file=sys.stderr)
        print(f"DSN in use: {redact(get_settings().database_url)}", file=sys.stderr)
        print("is Postgres up? `make up` starts it and waits for healthy.", file=sys.stderr)
        print(
            "if the host is `localhost`, try 127.0.0.1 — on Windows the name "
            "resolves to ::1 and the container only publishes on IPv4.",
            file=sys.stderr,
        )
        return 1
    print("checkpointer, instance_config and produto ready. next: `make seed`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

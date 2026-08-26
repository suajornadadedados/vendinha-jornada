"""Postgres: the checkpointer's home, and the one place that knows the DSN.

`AsyncPostgresSaver` creates its own tables, which makes `setup()` a migration —
and migrations do not belong in the startup path of a web process. Two replicas
booting together would race to create the same table, and the loser crashes on a
Tuesday for a reason nobody can reproduce. So it is an explicit command:

    make db-setup

Run it once after `make up`, and again whenever LangGraph ships a schema change.
"""

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from vendinha.config import get_settings
from vendinha.runtime import configure_event_loop


@asynccontextmanager
async def open_checkpointer(database_url: str | None = None) -> AsyncIterator[AsyncPostgresSaver]:
    """Open a checkpointer bound to the application's Postgres, and close it after."""
    dsn = database_url or get_settings().database_url
    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        yield saver


async def setup() -> None:
    """Create the checkpointer tables. Idempotent — safe to run again."""
    async with open_checkpointer() as saver:
        await saver.setup()


def main() -> int:
    configure_event_loop()
    try:
        asyncio.run(setup())
    except Exception as erro:
        # A DSN typo and a container that is not up produce very different fixes,
        # and psycopg says which is which. Printing the exception beats a traceback
        # for the person who just ran `make db-setup` for the first time.
        print(f"falha ao preparar o Postgres: {erro}", file=sys.stderr)
        print(f"DSN em uso: {get_settings().database_url}", file=sys.stderr)
        print("o Postgres esta no ar? `make up` sobe e espera ficar healthy.", file=sys.stderr)
        return 1
    print("checkpointer pronto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

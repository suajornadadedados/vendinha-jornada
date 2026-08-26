"""`python -m vendinha` — the entrypoint, and why `uvicorn vendinha.app:app` is not it.

On Windows, asyncio's default `ProactorEventLoop` is refused by `psycopg` in async
mode, and the loop is created by uvicorn *before* it imports the application. That
ordering is the whole problem: anything the app module does at import time, or in
its lifespan, is already too late — the loop exists. The policy has to be set by
whoever calls `asyncio.run`, which means the process entrypoint has to be ours.

    make api        # or: cd backend && uv run python -m vendinha

Running `uvicorn vendinha.app:app` by hand works on Linux and fails on Windows at
the first database call, with a message about event loops. The asymmetry is
exactly the kind CI never catches (ADR-008: development on Windows, deploy on
Linux), so the supported command is this one on both.
"""

import uvicorn

from vendinha import runtime
from vendinha.config import get_settings


def main() -> None:
    settings = get_settings()
    # `uvicorn.run` builds its own loop through its own factory, which is why the
    # server is driven by hand here: `runtime.run` is the only place that decides
    # what kind of loop this process gets.
    server = uvicorn.Server(
        uvicorn.Config("vendinha.app:app", host=settings.api_host, port=settings.api_port)
    )
    runtime.run(server.serve())


if __name__ == "__main__":
    main()

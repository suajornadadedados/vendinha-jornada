"""Event loop setup — one line of code, and a bug that only exists on Windows.

`psycopg` refuses to run async on the `ProactorEventLoop`, which is asyncio's
default on Windows since 3.8. The failure is not subtle once you see it, but it
arrives at the first database call rather than at startup, and the message talks
about event loops while the person reading it is thinking about Postgres.

Development on this project happens on Windows and deployment goes to a Linux VPS
(ADR-008), so the platform that breaks is exactly the one that is never in CI.
This function is called from every entrypoint — the CLI in `db.py` and the API in
`app.py` — because "remember to set the policy" is not a mechanism.
"""

import asyncio
import sys


def configure_event_loop() -> None:
    """Select an event loop psycopg can actually use. No-op outside Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

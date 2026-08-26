"""Event loop selection — three lines of code, and a bug that only exists on Windows.

`psycopg` refuses to run async on the `ProactorEventLoop`, which is asyncio's
default on Windows since 3.8. Setting the *policy* is not enough: uvicorn builds
its loop through an explicit factory rather than through the policy, so the loop
is already the wrong one by the time any application code runs. What works is
owning the call to `asyncio.run` and handing it the factory.

Development on this project happens on Windows and deployment goes to a Linux VPS
(ADR-008), so the platform that breaks is exactly the one CI never exercises. Every
entrypoint goes through `run()` for that reason — "remember to configure the loop"
is not a mechanism.
"""

import asyncio
import os
from collections.abc import Callable, Coroutine
from typing import Any


def loop_factory() -> Callable[[], asyncio.AbstractEventLoop] | None:
    """The loop constructor this platform needs, or `None` for asyncio's default.

    The test is `os.name`, not `sys.platform`, and that is not a style choice: mypy
    treats `sys.platform` comparisons as compile-time constants and narrows them
    away, so with `warn_unreachable` on, one of the two branches becomes an error —
    a different one on Windows than on Linux. `os.name` is an ordinary string to
    mypy, so both branches stay real on both platforms, which is what they are.
    """
    if os.name == "nt":
        return asyncio.SelectorEventLoop
    return None


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    """`asyncio.run`, on a loop psycopg can actually talk to."""
    factory = loop_factory()
    if factory is None:
        return asyncio.run(coro)
    return asyncio.run(coro, loop_factory=factory)

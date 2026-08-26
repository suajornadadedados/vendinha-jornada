"""Which model answers — and the fact that the code never asks which vendor.

`init_chat_model` takes `"<provedor>:<modelo>"` and hands back a `BaseChatModel`.
That is the whole abstraction: adding a third provider is a dependency line in
`pyproject.toml`, not a branch in this file (ADR-012).

S-06 will need this to be honest about *which* model produced an eval result, and
S-07 will let the operator pick one from the list the server offers. Neither of
those changes the shape here.
"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


@lru_cache(maxsize=8)
def resolve_model(nome: str) -> BaseChatModel:
    """Build (and reuse) the chat model named `provedor:modelo`.

    Cached because the client carries a connection pool: rebuilding it per request
    would open a new pool per request, which is the kind of thing that looks fine
    until concurrency arrives.
    """
    return init_chat_model(nome)

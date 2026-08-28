"""Which model answers — and the fact that the code never asks which vendor.

`init_chat_model` takes `"<provedor>:<modelo>"` and hands back a `BaseChatModel`.
That is the whole abstraction: adding a third provider is a dependency line and one
entry in `PROVIDERS`, not a branch through the application (ADR-012).

**The model list is fetched from the provider, never remembered.** There is no
hardcoded catalogue of model ids in this repository, and that is the project's own
golden rule applied to its own source code: a list written from memory is stale the
week after it is written, and nothing tells you. `ADR-001` says the agent must not
assert a fact it did not read from a source — the same standard applies to us.

**A model the customer names must come from the server's list.** A free-text
`model` field would let a client decide which vendor the server authenticates to
and how much it spends, and it would make the S-06 evals meaningless: they measure
a declared model, not one chosen per request.
"""

import asyncio
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

SEPARATOR = ":"


def _anthropic_models(api_key: str) -> list[str]:
    import anthropic

    page = anthropic.Anthropic(api_key=api_key).models.list(limit=100)
    return [model.id for model in page.data]


def _openai_models(api_key: str) -> list[str]:
    import openai

    page = openai.OpenAI(api_key=api_key).models.list()
    # The account also exposes embeddings, moderation and audio models. Only chat
    # models can answer here, and the prefix is the only signal the endpoint gives.
    return [model.id for model in page.data if model.id.startswith(("gpt-", "o1", "o3", "o4"))]


@dataclass(frozen=True)
class Provider:
    """One vendor: where its key comes from, and how to ask it what it offers."""

    name: str
    env_var: str
    list_models: Callable[[str], list[str]]


PROVIDERS: dict[str, Provider] = {
    "anthropic": Provider("anthropic", "ANTHROPIC_API_KEY", _anthropic_models),
    "openai": Provider("openai", "OPENAI_API_KEY", _openai_models),
}


def credentials_from_environment() -> dict[str, str]:
    """Keys present in the process environment — the zero-setup quickstart path.

    Whatever the operator stores through the API wins over these (ADR-012): the
    environment is a fallback, never an override, or changing a key in the UI would
    silently do nothing on a machine that has one in `.env`.
    """
    found = {}
    for name, provider in PROVIDERS.items():
        value = os.environ.get(provider.env_var)
        if value:
            found[name] = value
    return found


def effective_credentials(stored: Mapping[str, str]) -> dict[str, str]:
    """A credencial que o processo vai usar de verdade: ambiente por baixo, banco por cima.

    ADR-012 chama isso de invariante, e ele precisa morar numa função — não espalhado
    dentro de um endpoint. Quando a decisão vive no meio de uma rota, o teste acaba
    afirmando sobre o que a rota *mostra* (o campo `source`) em vez de sobre a chave
    que o modelo recebe. Inverter os dois lados aqui reprova um teste; inverter no
    endpoint não reprovava nenhum.
    """
    merged = credentials_from_environment()
    merged.update(stored)
    return merged


def split_model(name: str) -> tuple[str, str]:
    """`"anthropic:claude-haiku-4-5"` → `("anthropic", "claude-haiku-4-5")`."""
    provider, _, model = name.partition(SEPARATOR)
    if not provider or not model:
        raise ValueError(f"modelo precisa estar no formato provedor:modelo, veio {name!r}")
    if provider not in PROVIDERS:
        raise ValueError(f"provedor desconhecido: {provider!r}")
    return provider, model


async def models_offered_by(provider: str, api_key: str) -> list[str]:
    """Ask the provider what it has, prefixed and sorted. Never raises.

    Run in a worker thread because both SDKs are synchronous, and an HTTP call on
    the event loop would stall every other request on the process.

    A provider that is unreachable returns nothing rather than an error: the point
    of this list is to populate a picker, and a picker that explodes because one
    vendor is having a bad afternoon is worse than a picker that is one option
    short.
    """
    try:
        ids = await asyncio.to_thread(PROVIDERS[provider].list_models, api_key)
    except Exception:
        logger.warning("nao consegui listar modelos de %s", provider, exc_info=True)
        return []
    return sorted(f"{provider}{SEPARATOR}{model_id}" for model_id in ids)


@lru_cache(maxsize=8)
def resolve_model(
    name: str, api_key: str | None = None, temperature: float | None = None
) -> BaseChatModel:
    """Build (and reuse) the chat model named `provedor:modelo`.

    Cached because the client carries a connection pool: rebuilding it per request
    would open a pool per request, which looks fine right until concurrency
    arrives. `api_key` is part of the cache key, so rotating a credential produces
    a new client instead of silently reusing the old one — and **`temperature` is
    part of it too**, for the same reason: without it, the first caller's value
    would be handed to every later one, and the measurement in S-06 would have been
    comparing a configuration against itself.

    `temperature=None` means *do not pass it at all*, which is the provider's
    default. That is not the same as `0.0`, and the difference is not cosmetic: a
    reasoning model rejects the parameter outright, and this function branches on
    no vendor (ADR-012). See `config.Settings.llm_temperature` for why the value
    exists in the first place.
    """
    provider, model = split_model(name)
    # Montado como mapa, e não como cadeia de `if`/`return`: são dois parâmetros
    # opcionais e independentes, e escrever os quatro ramos à mão é onde uma
    # combinação some sem ninguém notar — foi assim que `temperature` deixaria de
    # ser passada justo no caminho sem `api_key`, que é o do quickstart.
    extras: dict[str, Any] = {}
    if api_key:
        extras["api_key"] = api_key
    if temperature is not None:
        extras["temperature"] = temperature
    resolvido: BaseChatModel = init_chat_model(model, model_provider=provider, **extras)
    return resolvido

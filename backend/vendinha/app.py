"""The HTTP surface: chat that streams, and the configuration behind it.

Decisions worth stating, because each reads as detail and behaves as architecture.

**The session id is the server's, and it is announced first.** A client that
invents its own will eventually invent a colliding one, and announcing the id only
at the end of the stream forces the client to buffer before it can continue the
conversation. The id it gets back is the same string the checkpointer uses as
`thread_id` — one concept, one identifier, nothing to keep in sync.

**After the first byte, failures are events.** The status line is already 200 by
then, so a failure at token forty cannot retroactively become a 500. It arrives as
an `error` event and the stream still ends with `done`.

**The model a request names must come from the server's list.** Free text there
would let the client choose which vendor the server authenticates to and how much
it spends (ADR-012), and it would make the S-06 evals meaningless.

**Writing configuration is refused outside `APP_ENV=local`.** There is no
authentication in this project yet, and `PUT /config` stores a provider credential.
Shipping that route open to a public host and planning to fix it later is how it
never gets fixed. See D-8 in the spec.
"""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, status
from langchain_core.messages import HumanMessage
from langfuse import propagate_attributes
from sse_starlette.sse import EventSourceResponse

from vendinha.budget import run_with_timeout
from vendinha.config import get_settings
from vendinha.config_store import ConfigStore, InMemoryConfigStore, PostgresConfigStore
from vendinha.credentials import CredentialsUnavailable, Vault
from vendinha.db import open_checkpointer, with_connect_timeout
from vendinha.graph import build_graph, session_config
from vendinha.observability import callback_handler, install_log_redaction
from vendinha.providers import (
    PROVIDERS,
    credentials_from_environment,
    models_offered_by,
    resolve_model,
    split_model,
)
from vendinha.schemas import (
    ChatRequest,
    ConfigResponse,
    ConfigUpdate,
    DoneEvent,
    ErrorEvent,
    HealthResponse,
    ModelsResponse,
    ProviderStatus,
    SessionEvent,
    TokenEvent,
)

logger = logging.getLogger(__name__)


async def _bounded_first_token(chunks: AsyncIterator[Any], seconds: float) -> AsyncIterator[Any]:
    """Yield the stream, bounding only the wait for the FIRST chunk.

    Bounding the whole response would be wrong: a long answer is not a stalled one,
    and a ceiling on total duration would cut exactly the replies worth reading.
    What a hung provider looks like is silence before the first token — which is
    also the number the spec puts a target on (p95 primeiro token ≤ 3s).
    """
    iterator = chunks.__aiter__()
    try:
        first: Any = await run_with_timeout(
            iterator.__anext__(), seconds, "primeiro token do modelo"
        )
    except StopAsyncIteration:
        return
    except BaseException:
        # The generator holds an open HTTP response; leaving it to the garbage
        # collector is how a timeout turns into a leaked connection. Not every
        # async iterator is closeable, so ask before assuming.
        close = getattr(chunks, "aclose", None)
        if close is not None:
            await close()
        raise

    yield first
    async for chunk in iterator:
        yield chunk


def create_app(graph: Any | None = None, store: ConfigStore | None = None) -> FastAPI:
    """Build the application.

    `graph` and `store` exist for the tests, and both are injected at seams the
    architecture already declares: the model behind the graph is a `BaseChatModel`
    (ADR-012), the checkpointer is a LangGraph interface with more than one
    implementation, and `ConfigStore` is a protocol with a real in-memory sibling.
    When they are `None` — the production path — the lifespan opens Postgres.
    """
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # After uvicorn has configured logging, never before: the filter attaches to
        # the root handlers, and there are none until the server sets them up.
        install_log_redaction()
        app.state.langfuse = callback_handler()
        app.state.graphs = {}
        app.state.store = store or PostgresConfigStore(
            with_connect_timeout(settings.database_url),
            Vault(settings.config_encryption_key),
        )

        if graph is not None:
            app.state.checkpointer = None
            app.state.fixed_graph = graph
            await app.state.store.setup()
            yield
            return

        app.state.fixed_graph = None
        async with open_checkpointer(settings.database_url) as checkpointer:
            app.state.checkpointer = checkpointer
            await app.state.store.setup()
            yield

    app = FastAPI(
        title="Vendinha",
        description="Agente de vendas do empório mineiro digital.",
        version="0.1.0",
        lifespan=lifespan,
    )

    async def _credentials(request: Request) -> dict[str, str]:
        """Environment first, stored configuration on top — stored always wins."""
        merged = credentials_from_environment()
        merged.update((await request.app.state.store.load()).credentials)
        return merged

    async def _selected_model(request: Request) -> str:
        stored = (await request.app.state.store.load()).selected_model
        return stored or settings.llm_model

    async def _allowed_models(request: Request) -> list[str]:
        credentials = await _credentials(request)
        offered: list[str] = []
        for provider, api_key in credentials.items():
            offered.extend(await models_offered_by(provider, api_key))

        # The configured model belongs in the list even if the provider's endpoint
        # did not answer: it is what the server will actually use, and leaving it
        # out would make `POST /chat` refuse the very model it is running.
        selected = await _selected_model(request)
        if selected not in offered and selected.split(":")[0] in credentials:
            offered.append(selected)
        return sorted(set(offered))

    async def _graph_for(request: Request, model_name: str) -> Any:
        if request.app.state.fixed_graph is not None:
            return request.app.state.fixed_graph

        cached = request.app.state.graphs.get(model_name)
        if cached is not None:
            return cached

        provider, _ = split_model(model_name)
        api_key = (await _credentials(request)).get(provider)
        built = build_graph(
            resolve_model(model_name, api_key),
            request.app.state.checkpointer,
            budget_tokens=settings.session_budget_tokens,
        )
        request.app.state.graphs[model_name] = built
        return built

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/models", response_model=ModelsResponse)
    async def models(request: Request) -> ModelsResponse:
        return ModelsResponse(
            models=await _allowed_models(request),
            selected=await _selected_model(request),
        )

    @app.get("/config", response_model=ConfigResponse)
    async def read_config(request: Request) -> ConfigResponse:
        stored = await request.app.state.store.load()
        from_env = credentials_from_environment()

        statuses = []
        for name in PROVIDERS:
            secret = stored.credentials.get(name) or from_env.get(name)
            source: Literal["banco", "ambiente", "nenhuma"] = "nenhuma"
            if name in stored.credentials:
                source = "banco"
            elif name in from_env:
                source = "ambiente"
            statuses.append(
                ProviderStatus(
                    provider=name,
                    configured=secret is not None,
                    source=source,
                    hint=Vault.hint(secret) if secret else None,
                )
            )

        return ConfigResponse(
            selected_model=await _selected_model(request),
            providers=statuses,
            editable=settings.app_env == "local",
            encryption_ready=Vault(settings.config_encryption_key).usable,
        )

    @app.put("/config", response_model=ConfigResponse)
    async def write_config(update: ConfigUpdate, request: Request) -> ConfigResponse:
        if settings.app_env != "local":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "configuracao so pode ser gravada em APP_ENV=local enquanto nao existe "
                "autenticacao (S-02, D-8)",
            )
        if update.provider is None and update.model is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "nada para gravar")

        current = await request.app.state.store.load()
        credentials = dict(current.credentials)
        selected = current.selected_model

        if update.provider is not None:
            if update.provider not in PROVIDERS:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"provedor desconhecido: {update.provider}",
                )
            if update.api_key is None:
                credentials.pop(update.provider, None)
            else:
                # Checked here rather than left to the store: refusing to keep a
                # secret without a key to encrypt it is policy, and policy that
                # lives in one implementation of a protocol is a guarantee that
                # depends on which implementation happens to be wired in.
                if not Vault(settings.config_encryption_key).usable:
                    raise HTTPException(
                        status.HTTP_503_SERVICE_UNAVAILABLE,
                        "CONFIG_ENCRYPTION_KEY nao esta definida: guardar credencial em "
                        "claro nao e uma opcao. Gere uma com Fernet.generate_key().",
                    )
                credentials[update.provider] = update.api_key.get_secret_value()

        if update.model is not None:
            try:
                split_model(update.model)
            except ValueError as invalid:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, str(invalid)
                ) from invalid
            selected = update.model

        try:
            await request.app.state.store.save(selected_model=selected, credentials=credentials)
        except CredentialsUnavailable as no_key:
            # 503 and not 500: the service is fine, the deployment is incomplete,
            # and the operator can fix it. The message says how.
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(no_key)) from no_key

        # Newly configured credentials can change which models exist and which key
        # a graph was built with. Dropping the cache is cheaper than reasoning about
        # which entries went stale.
        request.app.state.graphs.clear()
        return await read_config(request)

    @app.post("/chat")
    async def chat(payload: ChatRequest, request: Request) -> EventSourceResponse:
        session_id = payload.session_id or uuid.uuid4().hex
        model_name = payload.model or await _selected_model(request)

        if payload.model is not None and payload.model not in await _allowed_models(request):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "modelo fora da lista do servidor — consulte GET /models",
            )

        graph_to_run = await _graph_for(request, model_name)
        timeout = settings.tool_timeout_seconds
        handler = getattr(request.app.state, "langfuse", None)
        config = session_config(session_id)
        if handler is not None:
            config = {**config, "callbacks": [handler]}

        async def stream() -> AsyncIterator[dict[str, str]]:
            yield {
                "event": "session",
                "data": SessionEvent(session_id=session_id).model_dump_json(),
            }
            try:
                # `propagate_attributes` is what makes every observation under this
                # turn carry the session id, so the trace is findable by the same
                # string the customer's client holds — and the same one the
                # checkpointer uses as thread_id.
                with propagate_attributes(session_id=session_id, trace_name="conversa"):
                    token_stream = graph_to_run.astream(
                        {
                            "session_id": session_id,
                            "messages": [HumanMessage(content=payload.message)],
                        },
                        config=config,
                        stream_mode="messages",
                    )
                    async for chunk, _ in _bounded_first_token(token_stream, timeout):
                        # `.text` flattens content blocks: a provider answering
                        # with a list of typed blocks and one answering with a
                        # plain string have to look the same to the client.
                        if chunk.text:
                            yield {
                                "event": "token",
                                "data": TokenEvent(text=chunk.text).model_dump_json(),
                            }
            except Exception:
                # Loud on our side, vague on the customer's. The exception carries
                # DSNs, model names and limits; `adversarial-006` fails a run that
                # leaks internal configuration or tool names into an answer.
                logger.exception("failed to generate an answer for session %s", session_id)
                yield {
                    "event": "error",
                    "data": ErrorEvent(
                        detail="não consegui responder agora. pode tentar de novo?"
                    ).model_dump_json(),
                }

            # Outside the try, and never inside a `finally`: yielding while an
            # exception propagates out of an async generator is how a stream ends
            # with "generator ignored GeneratorExit" instead of with `done`.
            yield {
                "event": "done",
                "data": DoneEvent(session_id=session_id).model_dump_json(),
            }

        return EventSourceResponse(stream())

    return app


app = create_app()

__all__ = ["InMemoryConfigStore", "app", "create_app"]

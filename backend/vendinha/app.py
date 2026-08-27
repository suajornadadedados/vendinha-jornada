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
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html import escape
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from langchain.embeddings import init_embeddings
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langfuse import propagate_attributes
from sse_starlette.sse import EventSourceResponse

from vendinha.budget import run_with_timeout
from vendinha.catalogo import Busca, Catalogo, PostgresCatalogo, QdrantBusca
from vendinha.config import get_settings
from vendinha.config_store import ConfigStore, InMemoryConfigStore, PostgresConfigStore
from vendinha.credentials import CredentialsUnavailable, Vault
from vendinha.db import open_checkpointer, with_connect_timeout
from vendinha.graph import build_supervised_graph, fala_com_o_cliente, session_config
from vendinha.observability import callback_handler, install_log_redaction
from vendinha.pagamento import (
    MOCK,
    GatewayIndisponivel,
    PaymentGateway,
    assinatura_confere,
    gateway_de,
)
from vendinha.pedidos import PedidoInexistente, Pedidos, PostgresPedidos
from vendinha.providers import (
    PROVIDERS,
    credentials_from_environment,
    effective_credentials,
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
    NotificacaoDePagamento,
    ProviderStatus,
    SessionEvent,
    TokenEvent,
    WebhookProcessado,
)
from vendinha.subagents import checkout, recomendacao
from vendinha.supervisor import Supervisor, roteador_do_modelo

logger = logging.getLogger(__name__)


class CatalogoIndisponivel(RuntimeError):
    """O catálogo não está pronto. A mensagem diz qual comando resolve."""


# Long enough that a conversation never pays for the lookup twice, short enough that
# a key added straight into the environment shows up without a restart.
MODELS_CACHE_SECONDS = 300.0


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


def create_app(
    graph: Any | None = None,
    store: ConfigStore | None = None,
    catalogo: Catalogo | None = None,
    pedidos: Pedidos | None = None,
    gateway: PaymentGateway | None = None,
) -> FastAPI:
    """Build the application.

    `graph`, `store` and `catalogo` exist for the tests, and os três são injetados
    em costuras que a arquitetura já declara: o modelo por trás do grafo é um
    `BaseChatModel` (ADR-012), o checkpointer é uma interface do LangGraph com mais
    de uma implementação, e `ConfigStore` e `Catalogo` são protocolos com um irmão
    em memória de verdade. Quando são `None` — o caminho de produção — o lifespan
    abre o Postgres.

    `catalogo` entrou na S-03 por causa da conferência de subida: um preflight que
    o teste não consegue percorrer é um preflight que ninguém verifica, e era essa
    a ressalva R-14.
    """
    settings = get_settings()

    async def preparar(app: FastAPI, checkpointer: Any, fixed_graph: Any) -> None:
        """Tudo que a subida faz além de abrir a conexão com o Postgres.

        Isto era o corpo duplicado dos dois ramos do `lifespan`, e a duplicação
        era a **ressalva R-14 da verificação da S-02**: o ramo de produção —
        `graph is None` — não era alcançado por nenhum teste, então qualquer coisa
        que entrasse ali (pool, migração, healthcheck) nascia sem defesa. E foi
        exatamente o que aconteceu: a conferência de catálogo abaixo é nova.

        Com o corpo aqui fora, o que sobra sem cobertura no ramo de produção é o
        `async with` — que é a linha que só existe para abrir e fechar conexão.
        """
        # After uvicorn has configured logging, never before: the filter attaches to
        # the root handlers, and there are none until the server sets them up.
        install_log_redaction()
        app.state.langfuse = callback_handler()
        app.state.graphs = {}
        app.state.models_cache = None
        app.state.checkpointer = checkpointer
        app.state.fixed_graph = fixed_graph
        # A busca depende de credencial — ela embeda a necessidade do cliente —,
        # então nasce `None` e é montada na primeira consulta, com a chave que
        # estiver valendo naquele momento (ADR-012: banco por cima do ambiente).
        app.state.busca = None
        app.state.catalogo = catalogo or PostgresCatalogo(
            with_connect_timeout(settings.database_url)
        )
        # A porta do pedido é injetável pela mesma razão que o catálogo: a S-04
        # trouxe escrita, e um teste que não consegue substituir o que escreve só
        # consegue testar o caminho que não escreve.
        app.state.pedidos = pedidos or PostgresPedidos(with_connect_timeout(settings.database_url))
        # Qual adapter de pagamento vale nesta instância é decidido uma vez, na
        # subida, e dito em voz alta no log: a escolha é derivada da presença do
        # token, e escolha implícita que ninguém anuncia é a que vira dúvida
        # semanas depois (S-04, D-4).
        app.state.gateway = gateway or gateway_de(
            settings.mercadopago_access_token, settings.public_base_url
        )
        app.state.store = store or PostgresConfigStore(
            with_connect_timeout(settings.database_url),
            Vault(settings.config_encryption_key),
        )
        await app.state.store.setup()
        await _conferir_catalogo(app)
        await _warm_models(app)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if graph is not None:
            await preparar(app, checkpointer=None, fixed_graph=graph)
            try:
                yield
            finally:
                await _fechar_busca(app)
            return

        async with open_checkpointer(settings.database_url) as checkpointer:
            await preparar(app, checkpointer=checkpointer, fixed_graph=None)
            try:
                yield
            finally:
                await _fechar_busca(app)

    app = FastAPI(
        title="Vendinha",
        description="Agente de vendas do empório mineiro digital.",
        version="0.1.0",
        lifespan=lifespan,
    )

    async def _warm_models(app: FastAPI) -> None:
        """Pay the provider lookup at boot, so the first customer does not.

        Cold, the first `POST /chat` carrying a `model` measured 4,0 s against a 3 s
        target: the cache only helped from the second message on, and the first
        message is the one a person is watching. Failure here is not fatal — the
        route rebuilds the list on demand.
        """
        try:
            await _allowed_models(app)
        except Exception:
            logger.warning("nao consegui pre-carregar a lista de modelos", exc_info=True)

    async def _conferir_catalogo(app: FastAPI) -> None:
        """Recusa subir com o catálogo ausente ou vazio — ressalva R-10 da S-02.

        Antes disso, quem esquecia `make db-setup` descobria na primeira mensagem
        do cliente, como erro de tabela inexistente. Com o catálogo no banco a
        falha piorou de forma: sem `make seed`, a tabela existe e está vazia, a
        busca não acha nada, e o agente responde "não encontrei nada disso" com
        toda a sinceridade. Parece problema do modelo e é problema de setup — a
        pior classe de falha para diagnosticar.

        Falhar aqui é ruidoso de propósito. A alternativa — subir e avisar no log —
        é a que ninguém lê.
        """
        try:
            quantos = await app.state.catalogo.quantos()
        except Exception as erro:
            raise CatalogoIndisponivel(
                f"não consegui ler a tabela `produto`: {erro}. "
                "Ela é criada por `make db-setup` e preenchida por `make seed`."
            ) from erro
        if quantos == 0:
            raise CatalogoIndisponivel(
                "a tabela `produto` está vazia. Rode `make seed`. "
                "Sem catálogo o atendente responde que não encontrou nada — o que "
                "parece falha do modelo e é falha de setup."
            )

    async def _fechar_busca(app: FastAPI) -> None:
        """O cliente do Qdrant carrega conexão aberta; deixá-la para o GC é vazamento."""
        busca = getattr(app.state, "busca", None)
        if busca is not None:
            await busca.aclose()
            app.state.busca = None

    async def _busca(app: FastAPI) -> Busca:
        """A busca semântica, montada sob demanda com a credencial vigente.

        Cacheada em `app.state` porque o cliente do Qdrant tem pool, e o
        `PUT /config` a descarta junto com os grafos: trocar a chave do provedor
        de embedding sem reconstruir aqui deixaria o processo embedando com a
        credencial antiga até o próximo restart.
        """
        if app.state.busca is not None:
            existente: Busca = app.state.busca
            return existente

        provider, model = split_model(settings.embedding_model)
        api_key = (await _credentials(app)).get(provider)
        embeddings = init_embeddings(model, provider=provider, api_key=api_key)
        app.state.busca = QdrantBusca(settings.qdrant_url, settings.qdrant_collection, embeddings)
        nova: Busca = app.state.busca
        return nova

    async def _credentials(app: FastAPI) -> dict[str, str]:
        """Environment first, stored configuration on top — stored always wins."""
        return effective_credentials((await app.state.store.load()).credentials)

    async def _selected_model(app: FastAPI) -> str:
        stored = (await app.state.store.load()).selected_model
        return stored or settings.llm_model

    async def _allowed_models(app: FastAPI) -> list[str]:
        """The models this server accepts. Cached, because it is on the chat path.

        Every `POST /chat` that carries a `model` — which is every message the S-07
        UI will send — used to ask both providers over HTTP before answering. Measured
        cost: p95 of the first token went from 1.0s to 3.3s, past the 3s target in the
        spec, plus two vendor calls per conversation turn, which is rate limit and
        cost surface inside the very risk this spec closes (R6).

        Invalidated on `PUT /config`, so a newly configured provider shows up at once.
        """
        agora = time.monotonic()
        cached = app.state.models_cache
        if cached is not None and agora - cached[0] < MODELS_CACHE_SECONDS:
            return list(cached[1])

        credentials = await _credentials(app)
        offered: list[str] = []
        for provider, api_key in credentials.items():
            offered.extend(await models_offered_by(provider, api_key))

        # The configured model belongs in the list even if the provider's endpoint
        # did not answer: it is what the server will actually use, and leaving it
        # out would make `POST /chat` refuse the very model it is running.
        selected = await _selected_model(app)
        if selected not in offered and selected.split(":")[0] in credentials:
            offered.append(selected)

        allowed = sorted(set(offered))
        app.state.models_cache = (agora, allowed)
        return list(allowed)

    async def _graph_for(app: FastAPI, model_name: str) -> Any:
        if app.state.fixed_graph is not None:
            return app.state.fixed_graph

        cached = app.state.graphs.get(model_name)
        if cached is not None:
            return cached

        provider, _ = split_model(model_name)
        api_key = (await _credentials(app)).get(provider)
        model = resolve_model(model_name, api_key)
        busca = await _busca(app)
        timeout = settings.tool_timeout_seconds
        # O mesmo modelo atende as duas lanes e o roteador. Um modelo barato só
        # para rotear foi considerado e recusado: seria uma segunda credencial e
        # uma segunda lista de modelos permitidos no caminho do atendimento, e o
        # roteador só é consultado quando já existe composição aprovada (S-04).
        built = build_supervised_graph(
            model,
            app.state.checkpointer,
            Supervisor(
                recomendacao=recomendacao(busca, app.state.catalogo, app.state.pedidos, timeout),
                checkout=checkout(
                    busca,
                    app.state.catalogo,
                    app.state.pedidos,
                    app.state.gateway,
                    timeout,
                ),
                perguntar=roteador_do_modelo(model),
            ),
            budget_tokens=settings.session_budget_tokens,
        )
        app.state.graphs[model_name] = built
        return built

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/models", response_model=ModelsResponse)
    async def models(request: Request) -> ModelsResponse:
        return ModelsResponse(
            models=await _allowed_models(request.app),
            selected=await _selected_model(request.app),
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
            selected_model=await _selected_model(request.app),
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
        request.app.state.models_cache = None
        await _fechar_busca(request.app)
        return await read_config(request)

    @app.post("/chat")
    async def chat(payload: ChatRequest, request: Request) -> EventSourceResponse:
        session_id = payload.session_id or uuid.uuid4().hex
        model_name = payload.model or await _selected_model(request.app)

        if payload.model is not None and payload.model not in await _allowed_models(request.app):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "modelo fora da lista do servidor — consulte GET /models",
            )

        graph_to_run = await _graph_for(request.app, model_name)
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
                    async for chunk, meta in _bounded_first_token(token_stream, timeout):
                        # Só o que o ATENDENTE diz. `stream_mode="messages"` emite
                        # também os `ToolMessage`, e o retorno das tools desta spec
                        # é JSON — sem este filtro o cliente recebia o payload
                        # inteiro do catálogo no meio da frase, com nome de tool e
                        # estrutura interna junto. `adversarial-004` e
                        # `adversarial-006` reprovam uma execução que revela
                        # qualquer um dos dois.
                        if not isinstance(chunk, AIMessage | AIMessageChunk):
                            continue
                        # E só o que o atendente diz NO NÓ DE CONVERSA. A S-04 pôs
                        # um segundo modelo dentro do grafo — o roteador do
                        # supervisor, que devolve JSON de rota —, e
                        # `stream_mode="messages"` emite de qualquer chamada de
                        # modelo. Filtrar por tipo pegava a metade errada: o
                        # roteador também produz `AIMessage`.
                        if not fala_com_o_cliente((meta or {}).get("langgraph_node")):
                            continue
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

    @app.post("/webhooks/pagamento", response_model=WebhookProcessado)
    async def webhook_de_pagamento(
        notificacao: NotificacaoDePagamento,
        request: Request,
        x_signature: Annotated[str | None, Header()] = None,
        x_request_id: Annotated[str | None, Header()] = None,
    ) -> WebhookProcessado:
        """A confirmação de pagamento. Zero IA neste caminho (RF-2.5, R8).

        Três decisões, e cada uma existe por causa de uma falha concreta.

        **Origem verificada antes de qualquer coisa.** Sem assinatura válida, 401 e
        nada acontece — inclusive quando o segredo não está configurado. O oposto
        transformaria uma variável de ambiente esquecida num endpoint aberto que
        muda o estado de um pedido pago.

        **Quem afirma que foi pago é o gateway, não o POST.** A notificação diz
        *"olhe o pagamento 123"*; o servidor pergunta ao gateway o que aconteceu
        com ele e só então age. Confiar no corpo da requisição seria deixar o
        mensageiro decidir sobre dinheiro.

        **Duplicata responde 200.** Ela é comportamento normal de gateway, não
        falha, e um 4xx faria o Mercado Pago reenviar para sempre o evento que já
        teve efeito. A idempotência de verdade está uma camada abaixo, na chave
        primária de `evento_de_pagamento` — não num `SELECT` antes do `INSERT`,
        que é a corrida que dois webhooks simultâneos ganham.
        """
        if not assinatura_confere(
            segredo=settings.mercadopago_webhook_secret,
            cabecalho=x_signature,
            request_id=x_request_id,
            data_id=notificacao.data.id,
        ):
            # Sem detalhe do que faltou: quem manda assinatura errada não precisa
            # saber se errou o `ts`, o `v1` ou o segredo.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "assinatura inválida")

        if notificacao.type not in (None, "payment"):
            return WebhookProcessado(resultado="ignorado")

        try:
            pagamento = await request.app.state.gateway.consultar_pagamento(notificacao.data.id)
        except GatewayIndisponivel as fora_do_ar:
            # 503 e não 200: aqui o reenvio é exatamente o que queremos. Responder
            # 200 sem ter conseguido consultar faria o gateway parar de tentar, e o
            # pedido ficaria pago lá fora e pendente aqui.
            logger.warning(
                "não consegui consultar o pagamento %s: %s", notificacao.data.id, fora_do_ar
            )
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "não consegui confirmar o pagamento agora"
            ) from fora_do_ar

        if not pagamento.aprovado or not pagamento.pedido_id:
            # `pending` e `in_process` também notificam. Tratá-los como pago
            # liberaria a fila da nota antes de o dinheiro existir.
            return WebhookProcessado(resultado="ignorado")

        try:
            aplicado = await request.app.state.pedidos.registrar_pagamento(
                pagamento.pedido_id, pagamento.referencia
            )
        except PedidoInexistente:
            logger.warning("webhook para um pedido que não existe: %s", pagamento.pedido_id)
            return WebhookProcessado(resultado="ignorado")

        return WebhookProcessado(resultado="registrado" if aplicado else "duplicado")

    _rotas_do_mock(app)

    return app


def _rotas_do_mock(app: FastAPI) -> None:
    """A página de checkout falsa — e ela só existe quando o gateway é o mock.

    O ADR-004 pede o mock como cidadão de primeira classe, e um link que termina em
    404 não é isso. Estas rotas fecham o quickstart sem conta externa (RNF-1): o
    link abre uma página com o total do pedido e um botão que confirma o pagamento.

    **A confirmação não passa pelo webhook do gateway.** Ela não teria como: a
    assinatura exige o segredo, que não pode ir para o navegador. Então ela chama
    `registrar_pagamento` diretamente — a MESMA função, com a MESMA idempotência.
    O que muda é quem avisa, nunca o que acontece.

    **Elas não existem quando há um gateway de verdade configurado.** A checagem é
    no início de cada rota e não no registro porque o gateway é escolhido no
    lifespan, depois de as rotas existirem. Uma rota que confirma pagamento sem
    assinatura não pode estar de pé num ambiente com credencial real, e "está
    404" é a única resposta honesta.
    """

    def _mock_ativo(request: Request) -> None:
        if getattr(request.app.state, "gateway", None) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "não encontrado")
        if request.app.state.gateway.nome != MOCK:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "não encontrado")

    @app.get("/pagamento/mock/{pedido_id}", response_class=HTMLResponse)
    async def pagina_de_pagamento_falsa(pedido_id: str, request: Request) -> HTMLResponse:
        _mock_ativo(request)
        pedido = await request.app.state.pedidos.por_id(pedido_id)
        if pedido is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "pedido não encontrado")

        # Nada de razão social, CNPJ ou e-mail nesta página: ela é aberta por link,
        # sem autenticação nenhuma. O que ela mostra é o que o pagador precisa ver
        # para reconhecer a cobrança — o valor (ADR-007, R5).
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'>"
            "<title>Pagamento (simulado) — Vendinha</title>"
            "<body style='font-family:system-ui;max-width:32rem;margin:4rem auto'>"
            "<h1>Pagamento simulado</h1>"
            "<p><strong>SEM VALOR FINANCEIRO.</strong> Esta página existe porque "
            "nenhum gateway real está configurado nesta instância.</p>"
            f"<p>Pedido <code>{escape(pedido.id)}</code> — total "
            f"<strong>R$ {escape(str(pedido.total))}</strong>.</p>"
            f"<form method='post' action='/pagamento/mock/{escape(pedido.id)}/confirmar'>"
            "<button type='submit'>Confirmar pagamento</button></form></body>"
        )

    @app.post("/pagamento/mock/{pedido_id}/confirmar", response_model=WebhookProcessado)
    async def confirmar_pagamento_falso(pedido_id: str, request: Request) -> WebhookProcessado:
        _mock_ativo(request)
        link = await request.app.state.gateway.criar_preferencia(
            await _pedido_ou_404(request, pedido_id)
        )
        try:
            aplicado = await request.app.state.pedidos.registrar_pagamento(
                pedido_id, link.referencia
            )
        except PedidoInexistente:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "pedido não encontrado") from None
        return WebhookProcessado(resultado="registrado" if aplicado else "duplicado")


async def _pedido_ou_404(request: Request, pedido_id: str) -> Any:
    pedido = await request.app.state.pedidos.por_id(pedido_id)
    if pedido is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pedido não encontrado")
    return pedido


app = create_app()

__all__ = ["InMemoryConfigStore", "app", "create_app"]

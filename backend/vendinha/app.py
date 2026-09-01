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

import hmac
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html import escape
from typing import Annotated, Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from langchain.embeddings import init_embeddings
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langfuse import propagate_attributes
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse

from vendinha import admin
from vendinha.budget import run_with_timeout
from vendinha.catalogo import Busca, Catalogo, PostgresCatalogo, QdrantBusca
from vendinha.config import get_settings
from vendinha.config_store import ConfigStore, InMemoryConfigStore, PostgresConfigStore
from vendinha.credentials import CredentialsUnavailable, Vault
from vendinha.db import open_checkpointer, with_connect_timeout
from vendinha.documentos import formatar_cnpj
from vendinha.eventos import Barramento, BarramentoEmMemoria, agora
from vendinha.fiscal import (
    Aprovacao,
    Decisao,
    Fiscal,
    PostgresFiscal,
    abrir_fila_da_nota,
    build_emissao_graph,
    decidir,
    pendentes,
)
from vendinha.graph import build_supervised_graph, fala_com_o_cliente, session_config
from vendinha.nota import NFEmitter, emissor_de, inscricao_do_destinatario
from vendinha.nota.documento import numero_da_nota
from vendinha.observability import (
    ambiente_do_trace,
    callback_handler,
    install_log_redaction,
    silence_unserved_probes,
)
from vendinha.observador import ObservadorDoTurno
from vendinha.pagamento import (
    MOCK,
    GatewayIndisponivel,
    PaymentGateway,
    assinatura_confere,
    gateway_de,
)
from vendinha.pedidos import (
    Pedido,
    PedidoInexistente,
    Pedidos,
    PostgresPedidos,
    StatusDoPedido,
)
from vendinha.providers import (
    PROVIDERS,
    credentials_from_environment,
    effective_credentials,
    models_offered_by,
    resolve_model,
    split_model,
)
from vendinha.schemas import (
    AprovacaoPendente,
    ChatRequest,
    ConfigResponse,
    ConfigUpdate,
    DecisaoDoOperador,
    DecisaoRegistrada,
    DestinatarioDaNota,
    DoneEvent,
    ErrorEvent,
    FilaDoOperador,
    HealthResponse,
    ModelsResponse,
    NotaDecidida,
    NotificacaoDePagamento,
    PedidoAtualizado,
    PedidoNaFila,
    PreambuloEvent,
    ProviderStatus,
    SessionEvent,
    TokenEvent,
    WebhookProcessado,
)
from vendinha.subagents import checkout, recomendacao
from vendinha.supervisor import Supervisor, roteador_do_modelo
from vendinha.telemetria import PostgresTelemetria, Telemetria

logger = logging.getLogger(__name__)


class CatalogoIndisponivel(RuntimeError):
    """O catálogo não está pronto. A mensagem diz qual comando resolve."""


# Long enough that a conversation never pays for the lookup twice, short enough that
# a key added straight into the environment shows up without a restart.
MODELS_CACHE_SECONDS = 300.0

# O mesmo batimento do stream do painel: sem ele, um proxy que corta conexão
# ociosa derruba o push de uma conversa que só estava esperando a aprovação da
# nota — que é exatamente a espera mais longa do fluxo.
EVENTOS_HEARTBEAT_SEGUNDOS = 15


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


def _pede_tool(chunk: Any) -> bool:
    """Se esta mensagem do atendente também chama uma tool.

    Duas chaves porque o streaming e o não-streaming falam diferente: um
    `AIMessageChunk` traz `tool_call_chunks` (o JSON dos argumentos chegando aos
    pedaços) e uma `AIMessage` inteira traz `tool_calls`. Um `ainvoke` sem stream
    — o caminho dos testes e de qualquer provedor que não emita chunk — só tem a
    segunda.
    """
    return bool(getattr(chunk, "tool_call_chunks", None) or getattr(chunk, "tool_calls", None))


def create_app(
    graph: Any | None = None,
    store: ConfigStore | None = None,
    catalogo: Catalogo | None = None,
    pedidos: Pedidos | None = None,
    gateway: PaymentGateway | None = None,
    fiscal: Fiscal | None = None,
    emissor: NFEmitter | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    telemetria: Telemetria | None = None,
    barramento: Barramento | None = None,
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
        silence_unserved_probes()
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
        # O lado fiscal (S-05). A porta guarda a decisão do operador e a nota; o
        # emissor é escolhido por `NF_EMITTER` e diz em voz alta qual é, como o
        # gateway faz — escolha de integração que ninguém anuncia é a que vira
        # dúvida três semanas depois (D-4 da S-04).
        app.state.fiscal = fiscal or PostgresFiscal(with_connect_timeout(settings.database_url))
        app.state.emissor = emissor or emissor_de(
            settings.nf_emitter, settings.nf_emitter_api_key, settings.nf_emitter_base_url
        )
        # O grafo da emissão existe SEMPRE, porque é ele que persiste a pausa do
        # ADR-003 — sem ele, um pedido pago não teria onde parar. Em produção o
        # checkpointer é o do Postgres; num teste que injeta o grafo da conversa é o
        # `InMemorySaver`, que é outra implementação da MESMA interface do LangGraph
        # e não um dublê de nada (`docs/testes.md` §4).
        app.state.emissao = build_emissao_graph(
            app.state.pedidos,
            app.state.fiscal,
            app.state.emissor,
            checkpointer or InMemorySaver(),
        )
        # O read model e o barramento do painel (S-07, ADR-015). O barramento
        # nasce sempre, mesmo sem ninguem assinando: publicar num barramento sem
        # assinante e barato, e um `if barramento is not None` espalhado por cada
        # publicador e a linha que alguem esquece de escrever no setimo evento.
        app.state.telemetria = telemetria or PostgresTelemetria(
            with_connect_timeout(settings.database_url)
        )
        app.state.barramento = barramento or BarramentoEmMemoria()
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
            # `checkpointer` injetado ou nenhum: com o grafo da conversa fixo, o
            # único que ainda precisa de um é o da emissão, e `preparar` cai no
            # `InMemorySaver` quando não recebe. Um teste que queira provar retomada
            # da nota passa o seu.
            await preparar(app, checkpointer=checkpointer, fixed_graph=graph)
            try:
                yield
            finally:
                await _fechar_busca(app)
            return

        # `saver` e não `checkpointer`: o parâmetro de `create_app` tem esse nome, e
        # um `as checkpointer` aqui o tornaria local de `lifespan` — o ramo acima
        # passaria a ler uma variável ainda não atribuída, na subida, em produção.
        async with open_checkpointer(settings.database_url) as saver:
            await preparar(app, checkpointer=saver, fixed_graph=None)
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

    # O primeiro middleware deste app, e ele chega na S-07 porque o primeiro
    # cliente de navegador chega na S-07. `allow_credentials` fica FALSO de
    # propósito: o painel autentica por header próprio, não por cookie, e ligá-lo
    # sem necessidade proibiria justamente as origens explícitas de funcionarem
    # com curinga se alguém trocar a lista por `*` um dia.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origens_permitidas,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-Operador-Token"],
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
        # `com_ferramentas=True`: as duas lanes bindam tool, e é isso que decide o
        # endpoint na OpenAI. Ver `providers.resolve_model`.
        model = resolve_model(model_name, api_key, settings.llm_temperature, com_ferramentas=True)
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
                recomendacao=recomendacao(
                    busca,
                    app.state.catalogo,
                    app.state.pedidos,
                    timeout,
                    app.state.fiscal,
                    settings.public_base_url,
                ),
                checkout=checkout(
                    busca,
                    app.state.catalogo,
                    app.state.pedidos,
                    app.state.gateway,
                    timeout,
                    app.state.fiscal,
                    settings.public_base_url,
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
        sessao_nova = payload.session_id is None
        session_id = payload.session_id or uuid.uuid4().hex
        model_name = payload.model or await _selected_model(request.app)

        if payload.model is not None and payload.model not in await _allowed_models(request.app):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "modelo fora da lista do servidor — consulte GET /models",
            )

        graph_to_run = await _graph_for(request.app, model_name)
        timeout = settings.tool_timeout_seconds
        # O handler da subida é a sonda: ele diz se há Langfuse configurado, e é o
        # que já logou uma vez se não houver. O que vai no `config` é um handler
        # POR SESSÃO, com o trace id derivado dela — é o que faz os turnos de um
        # atendimento caírem num trace só em vez de um trace por turno. Se construí-lo
        # falhar, cai no da subida: pior um trace por turno do que atendimento sem
        # trace (ADR-010).
        handler = getattr(request.app.state, "langfuse", None)
        config = session_config(session_id)
        if handler is not None:
            config = {**config, "callbacks": [callback_handler(session_id=session_id) or handler]}

        # O painel observa o mesmo stream com outra pergunta: a rota filtra o que o
        # cliente pode ler, o observador mede o que o turno custou e conta ao
        # operador o que aconteceu. Nenhum dos dois muda o grafo (S-07, D-2).
        observador = ObservadorDoTurno(
            barramento=request.app.state.barramento,
            telemetria=request.app.state.telemetria,
            session_id=session_id,
            modelo=model_name,
        )

        async def stream() -> AsyncIterator[dict[str, str]]:
            yield {
                "event": "session",
                "data": SessionEvent(session_id=session_id).model_dump_json(),
            }
            await observador.abrir(primeira_mensagem=payload.message, sessao_nova=sessao_nova)
            falhou = False
            try:
                # `propagate_attributes` is what makes every observation under this
                # turn carry the session id, so the trace is findable by the same
                # string the customer's client holds — and the same one the
                # checkpointer uses as thread_id.
                #
                # `environment` separa este atendimento do resto que a mesma conta
                # do Langfuse recebe — os evals já se declaram `evals` desde o
                # ADR-014, e sem esta linha a conversa de verdade caía em `default`
                # junto com tudo que não se identificou. Ver `ambiente_do_trace`.
                with propagate_attributes(
                    session_id=session_id,
                    trace_name="conversa",
                    environment=ambiente_do_trace(settings.app_env),
                ):
                    token_stream = graph_to_run.astream(
                        {
                            "session_id": session_id,
                            "messages": [HumanMessage(content=payload.message)],
                        },
                        config=config,
                        stream_mode="messages",
                    )
                    # Qual fala do atendente estamos transmitindo. Um turno com tool
                    # no meio produz mais de uma `AIMessage`, e cada uma é um balão
                    # na tela do cliente. O id do chunk é o que as separa — o
                    # LangChain mantém o mesmo id por mensagem e troca na seguinte.
                    fala = 0
                    id_da_fala: str | None = None
                    # Se a fala corrente já pôs texto na tela, e se já avisamos que
                    # ela era preâmbulo. Os dois juntos são a guarda: sem o
                    # primeiro, uma mensagem só de tool (nenhum texto, id novo)
                    # mandaria apagar o balão da fala ANTERIOR, que era a resposta.
                    falou = False
                    avisado = False
                    async for chunk, meta in _bounded_first_token(token_stream, timeout):
                        # Antes de qualquer filtro: o observador precisa do que o
                        # cliente NÃO vê — o veredito da composição, o id do pedido
                        # e o consumo do roteador do supervisor.
                        await observador.viu(chunk, meta)
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
                        atual = getattr(chunk, "id", None)
                        # `.text` flattens content blocks: a provider answering
                        # with a list of typed blocks and one answering with a
                        # plain string have to look the same to the client.
                        if chunk.text:
                            # Só conta como fala nova o chunk que TEM id e cujo id
                            # mudou. Provedor que não manda id nenhum cai no caso de
                            # uma fala só, que é o comportamento anterior — pior
                            # partir a resposta em balões aleatórios do que emendar.
                            if atual is not None and atual != id_da_fala:
                                if id_da_fala is not None:
                                    fala += 1
                                id_da_fala = atual
                                falou = False
                                avisado = False
                            falou = True
                            yield {
                                "event": "token",
                                "data": TokenEvent(text=chunk.text, fala=fala).model_dump_json(),
                            }

                        # Texto E chamada de tool na mesma mensagem: o texto era
                        # preâmbulo do trabalho ("Agora vou consultar os preços…"),
                        # não resposta ao cliente. O balão sai e volta a ser o
                        # indicador de digitando.
                        #
                        # `atual == id_da_fala` é o que amarra o aviso à fala que
                        # de fato falou: sem essa igualdade, uma mensagem seguinte
                        # que só chama tool apagaria a resposta anterior.
                        if atual is not None and atual == id_da_fala and falou and not avisado:
                            if _pede_tool(chunk):
                                avisado = True
                                yield {
                                    "event": "preambulo",
                                    "data": PreambuloEvent(fala=fala).model_dump_json(),
                                }
            except Exception:
                # Loud on our side, vague on the customer's. The exception carries
                # DSNs, model names and limits; `adversarial-006` fails a run that
                # leaks internal configuration or tool names into an answer.
                # O nome do modelo vai no log porque ele é escolhido em runtime
                # (ADR-012) e é a primeira coisa que se quer saber aqui. Sem ele,
                # um modelo que o servidor oferece mas não sabe chamar tool produz
                # o mesmo "não consegui responder agora" de uma queda de rede, e
                # quem trocou o modelo no painel não tem como ligar uma coisa à
                # outra. Aconteceu com `openai:gpt-5.6-luna`.
                logger.exception(
                    "failed to generate an answer for session %s with model %s",
                    session_id,
                    model_name,
                )
                falhou = True
                yield {
                    "event": "error",
                    "data": ErrorEvent(
                        detail="não consegui responder agora. pode tentar de novo?"
                    ).model_dump_json(),
                }

            # Fechar antes do `done` e fora do `try`: o painel precisa ter a fala
            # inteira do atendente e o custo do turno no momento em que o cliente vê
            # a resposta terminar, e não um evento depois.
            await observador.fechar(erro=falhou)

            # Outside the try, and never inside a `finally`: yielding while an
            # exception propagates out of an async generator is how a stream ends
            # with "generator ignored GeneratorExit" instead of with `done`.
            yield {
                "event": "done",
                "data": DoneEvent(session_id=session_id).model_dump_json(),
            }

        return EventSourceResponse(stream())

    @app.get("/eventos/sessao/{session_id}")
    async def eventos_da_sessao(session_id: str, request: Request) -> EventSourceResponse:
        """O push para o chat do cliente — e o que fecha a ressalva R-2 da S-05.

        O RF-3.6 diz que o cliente **recebe** a confirmação da nota. Até aqui ele
        perguntava e o agente consultava (S-05, D-8), e a verificação independente
        registrou o estreitamento com a observação de que *"a S-07 deveria fechar de
        verdade"*. Com esta rota, aprovar no painel faz o cartão da NF aparecer no
        widget sem que ninguém digite nada.

        **Sem token, e protegida pelo mesmo segredo que protege `nota.xml`:** o id
        opaco da sessão. Quem o tem é quem está na conversa. Exigir credencial aqui
        seria exigir login de um visitante anônimo para receber a própria nota.

        **O assinante é filtrado por sessão no barramento**, por inclusão explícita:
        só chega o evento que carrega este `session_id`. Um evento sem sessão — a
        fila de aprovação, por exemplo — não vaza para cá por construção, e não por
        uma lista de proibidos que alguém esquece de atualizar.
        """
        barramento = request.app.state.barramento

        async def stream() -> AsyncIterator[dict[str, str]]:
            async with barramento.assinar(sessao=session_id) as fluxo:
                async for evento in fluxo:
                    yield {"event": evento.tipo, "data": evento.model_dump_json()}

        return EventSourceResponse(stream(), ping=EVENTOS_HEARTBEAT_SEGUNDOS)

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

        if aplicado:
            await _abrir_fila_da_nota(request.app, pagamento.pedido_id)
        return WebhookProcessado(resultado="registrado" if aplicado else "duplicado")

    # ------------------------------------------------------ a fila do operador

    def _operador_autenticado(token: str | None) -> None:
        """O portao da fila (S-05, REQ-2), e ele e o mesmo do webhook do gateway.

        **Sem `OPERADOR_API_TOKEN` configurado, nada confere.** E o lado seguro: a
        alternativa — "sem token, aceita tudo" — transformaria esquecer uma variavel
        de ambiente num endpoint aberto que lista CNPJ e endereco de compradoras e
        autoriza uma emissao irreversivel.

        `compare_digest` e nao `==`: comparar segredo com `==` vaza o prefixo correto
        pelo tempo de resposta, e a rota do outro lado da comparacao e a que emite
        documento fiscal.

        Um 401 sem detalhe, pelo mesmo motivo do webhook: quem mandou o token errado
        nao precisa saber se ele estava ausente, curto ou trocado.
        """
        esperado = settings.operador_api_token
        if not esperado or not token or not hmac.compare_digest(esperado, token):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "credencial de operador invalida")

    def _na_fila(
        pedido: Pedido,
        *,
        decisao: Aprovacao | None = None,
        numero_nota: int | None = None,
    ) -> PedidoNaFila:
        """O pedido como o operador o ve: dados da nota, e a composicao item a item.

        As composicoes vao como estao gravadas, sem reprojecao. E o que o RF-3.2
        pede — *"dados completos da nota, incluindo destinatario PJ e a composicao
        item a item"* — e e tambem o que garante que o que ele aprova e o que o
        emissor vai ler.

        **Um pedido decidido passa por aqui pelo mesmo caminho**, com a decisao
        anexada. Quem abre um pedido ja aprovado precisa ver a mesma composicao item
        a item que foi aprovada; montar um modelo enxuto so para o historico seria
        uma segunda projecao do mesmo dado, e o historico da nota fiscal e
        exatamente o lugar onde a projecao velha custa caro.
        """
        return PedidoNaFila(
            pedido_id=pedido.id,
            criado_em=pedido.criado_em,
            total=pedido.total,
            destinatario=DestinatarioDaNota(
                razao_social=pedido.empresa.razao_social,
                cnpj=formatar_cnpj(pedido.empresa.cnpj),
                inscricao_estadual=inscricao_do_destinatario(pedido),
                contato_nome=pedido.empresa.contato_nome,
                contato_email=pedido.empresa.contato_email,
                endereco=pedido.empresa.endereco,
            ),
            composicoes=pedido.composicoes,
            status=pedido.status.value,
            decisao=None if decisao is None else decisao.decisao.value,
            operador=None if decisao is None else decisao.operador,
            decidido_em=None if decisao is None else decisao.decidido_em,
            motivo=None if decisao is None else decisao.motivo,
            numero_nota=numero_nota,
        )

    @app.get("/operador/fila", response_model=FilaDoOperador)
    async def fila_do_operador(
        request: Request,
        limite: int = 50,
        x_operador_token: Annotated[str | None, Header()] = None,
    ) -> FilaDoOperador:
        """Os pedidos pagos esperando decisao, e os que ja foram decididos (RF-3.2, RF-4.2).

        A fila e a consulta pelo **status do pedido**, nao pelo grafo: um pedido cuja
        pausa nao chegou a abrir continua aparecendo aqui, e a aprovacao conduz o
        grafo do comeco. Fila que depende de um `ainvoke` ter dado certo e fila que
        perde pedido em silencio.

        **O historico sai da tabela de decisoes, nao do status do pedido.** Sao coisas
        diferentes: `nota_emitida` diz o que aconteceu com a nota, e `aprovacao_de_nf`
        diz quem decidiu e quando. Um pedido rejeitado nao vira nota nenhuma e
        precisa aparecer no historico do mesmo jeito — e um dia em que a emissao
        falhar depois de uma aprovacao valida, a aprovacao continua sendo um fato
        registrado.
        """
        _operador_autenticado(x_operador_token)
        pedidos_do_painel = request.app.state.pedidos
        fiscal = request.app.state.fiscal

        na_fila = await pendentes(pedidos_do_painel)
        recentes = await pedidos_do_painel.listar(limite=min(max(limite, 1), 200), offset=0)
        decisoes = await fiscal.decisoes_de([pedido.id for pedido in recentes])

        decididos = []
        for pedido in recentes:
            decisao = decisoes.get(pedido.id)
            if decisao is None:
                continue
            decididos.append(
                _na_fila(
                    pedido,
                    decisao=decisao,
                    numero_nota=numero_da_nota(await fiscal.nota_de(pedido.id)),
                )
            )

        return FilaDoOperador(
            pendentes=tuple(_na_fila(pedido) for pedido in na_fila),
            decididos=tuple(decididos),
        )

    async def _decidir_pela_fila(
        request: Request, pedido_id: str, decisao: Decisao, corpo: DecisaoDoOperador
    ) -> DecisaoRegistrada:
        """Grava a decisao e conduz o grafo. O corpo comum de aprovar e rejeitar.

        **A resposta e a decisao VIGENTE, que pode nao ser esta.** A primeira vence
        (chave primaria de `aprovacao_de_nf`), entao um segundo operador clicando em
        "aprovar" num pedido ja rejeitado recebe de volta a rejeicao — com quem,
        quando e por que — em vez de um 200 que o faria acreditar que aprovou.
        """
        pedido = await request.app.state.pedidos.por_id(pedido_id)
        if pedido is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "pedido nao encontrado")
        if pedido.status is StatusDoPedido.AGUARDANDO_PAGAMENTO:
            # O unico estado em que decidir seria errado — e o erro seria caro:
            # emitir nota de um pedido que ninguem pagou. A fila so existe depois da
            # confirmacao do pagamento (RF-3.1).
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "este pedido ainda nao foi pago; a nota so entra na fila depois da "
                "confirmacao do pagamento",
            )

        try:
            pedida = Aprovacao(
                pedido_id=pedido_id,
                decisao=decisao,
                operador=corpo.operador,
                motivo=corpo.motivo,
            )
        except ValidationError as sem_motivo:
            # A regra mora no modelo, nao aqui (RF-4.2). A rota so traduz a recusa
            # para o codigo HTTP que o cliente da S-07 vai tratar.
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "rejeicao exige motivo: ele e o que o cliente recebe no chat",
            ) from sem_motivo

        vigente = await decidir(request.app.state.emissao, pedida, fiscal=request.app.state.fiscal)
        emitida = await request.app.state.fiscal.nota_de(pedido_id)

        # Depois de decidir e emitir, nunca antes: o que vai para o chat do cliente
        # é o desfecho, e um evento otimista chegaria com o número da nota em branco.
        # `vigente` e não a decisão pedida — a primeira decisão vence, e um segundo
        # operador clicando em aprovar num pedido rejeitado não pode anunciar uma
        # aprovação que não aconteceu.
        await _publicar(
            request.app,
            NotaDecidida(
                em=agora(),
                pedido_id=pedido_id,
                session_id=await _sessao_do(request.app, pedido_id),
                decisao=vigente.decisao.value,
                numero_nota=emitida.nota.numero if emitida else None,
                motivo=vigente.motivo,
            ),
        )
        await _anunciar_o_pedido(request.app, pedido_id)

        return DecisaoRegistrada(
            pedido_id=pedido_id,
            decisao=vigente.decisao.value,
            operador=vigente.operador,
            decidido_em=vigente.decidido_em,
            motivo=vigente.motivo,
            numero_nota=emitida.nota.numero if emitida else None,
            chave_da_nota=emitida.nota.chave if emitida else None,
        )

    @app.post("/operador/pedidos/{pedido_id}/aprovar", response_model=DecisaoRegistrada)
    async def aprovar_a_nota(
        pedido_id: str,
        corpo: DecisaoDoOperador,
        request: Request,
        x_operador_token: Annotated[str | None, Header()] = None,
    ) -> DecisaoRegistrada:
        """Aprova e retoma o grafo, que entao emite (RF-3.3, REQ-3).

        Repare no que esta rota **nao** faz: ela nao emite. Ela grava a decisao e
        conduz o grafo; quem emite e `fiscal.emitir`, que rele a decisao do banco
        antes de agir. Parece um rodeio e e a garantia inteira — a autorizacao e o
        registro, nunca a chamada.
        """
        _operador_autenticado(x_operador_token)
        return await _decidir_pela_fila(request, pedido_id, Decisao.APROVADA, corpo)

    @app.post("/operador/pedidos/{pedido_id}/rejeitar", response_model=DecisaoRegistrada)
    async def rejeitar_a_nota(
        pedido_id: str,
        corpo: DecisaoDoOperador,
        request: Request,
        x_operador_token: Annotated[str | None, Header()] = None,
    ) -> DecisaoRegistrada:
        """Rejeita com motivo, e tira o pedido do caminho de emissao (RF-4.2).

        O motivo nao e burocracia: ele e o que o cliente le no chat quando pergunta
        pela nota, por `consultar_pedido`. Uma rejeicao sem motivo vira silencio para
        quem pagou, e e o que o `golden-011` existe para nao deixar acontecer.
        """
        _operador_autenticado(x_operador_token)
        return await _decidir_pela_fila(request, pedido_id, Decisao.REJEITADA, corpo)

    # ------------------------------------------------ o documento, para o cliente

    async def _nota_ou_404(request: Request, pedido_id: str) -> Any:
        """A nota emitida, ou 404.

        **Um 404 e nao um 409 para "ainda nao emitida".** De fora, "este pedido nao
        existe" e "a nota dele ainda nao saiu" tem que ser a mesma resposta: a URL e
        aberta, e distinguir os dois casos transformaria a rota num oraculo que diz
        quais ids de pedido existem.
        """
        emitida = await request.app.state.fiscal.nota_de(pedido_id)
        if emitida is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "nota nao encontrada")
        return emitida

    @app.get("/pedidos/{pedido_id}/nota.xml", response_class=Response)
    async def xml_da_nota(pedido_id: str, request: Request) -> Response:
        """O XML da NF-e, para o contador da empresa compradora (RF-3.6, REQ-6).

        **Aberta por link, e o link e o id opaco do pedido** — mesmo raciocinio do
        link de pagamento (S-04). Diferente da pagina do mock, este documento
        *carrega* dados do destinatario: e da natureza dele, e a alternativa seria
        autenticar o comprador, que e um sistema que este projeto ainda nao tem. O
        `uuid4` de `pedidos.novo_id` e o que sustenta a decisao, e ela esta escrita
        aqui em vez de escondida.
        """
        emitida = await _nota_ou_404(request, pedido_id)
        return Response(
            content=emitida.xml,
            media_type="application/xml",
            headers={
                "Content-Disposition": (f'inline; filename="nfe-{emitida.nota.numero:09d}.xml"')
            },
        )

    @app.get("/pedidos/{pedido_id}/nota.pdf", response_class=Response)
    async def danfe_da_nota(pedido_id: str, request: Request) -> Response:
        """A DANFE em PDF. `inline` para abrir no navegador, com nome ao salvar."""
        emitida = await _nota_ou_404(request, pedido_id)
        return Response(
            content=emitida.danfe,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (f'inline; filename="danfe-{emitida.nota.numero:09d}.pdf"')
            },
        )

    _rotas_do_mock(app)
    # O painel (S-07). Fica num modulo proprio porque sao sete rotas de leitura
    # e nenhuma delas muda nada aqui dentro; recebe o mesmo portao da fila, para
    # que exista UM lugar onde o token do operador e conferido.
    admin.montar(app, autenticado=_operador_autenticado, settings=settings)

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
            # **Caminho RELATIVO, e nunca um que comece em `/`.** Esta página é
            # servida por um link que veio de `PUBLIC_BASE_URL`, e essa base pode
            # ter um prefixo: atrás do nginx da S-08 a API vive sob `/api/`. Um
            # `action='/pagamento/...'` descarta esse prefixo e posta na raiz do
            # host, onde quem responde é o servidor de estáticos — que devolve
            # **405** a um POST, porque um arquivo não tem o que fazer com ele.
            #
            # Relativo resolve contra a URL desta página, então funciona com
            # prefixo, sem prefixo, em outra porta ou atrás de um túnel, sem ler
            # configuração nenhuma. Encontrado subindo o ambiente empacotado
            # (S-08); em desenvolvimento nunca apareceu, porque lá a API é a raiz
            # da própria origem e o caminho absoluto calhava de estar certo.
            f"<form method='post' action='{escape(pedido.id)}/confirmar'>"
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
        if aplicado:
            await _abrir_fila_da_nota(request.app, pedido_id)
        return WebhookProcessado(resultado="registrado" if aplicado else "duplicado")


async def _publicar(app: FastAPI, evento: Any) -> None:
    """Publica sem nunca levantar. O painel não pode custar uma venda."""
    try:
        await app.state.barramento.publicar(evento)
    except Exception:
        logger.exception("falha ao publicar %s no barramento do painel", type(evento).__name__)


async def _sessao_do(app: FastAPI, pedido_id: str) -> str | None:
    try:
        encontrada: str | None = await app.state.telemetria.sessao_do_pedido(pedido_id)
        return encontrada
    except Exception:
        logger.exception("falha ao achar a sessao do pedido %s", pedido_id)
        return None


async def _anunciar_o_pedido(app: FastAPI, pedido_id: str) -> None:
    """Diz ao painel — e ao chat do cliente — que este pedido mudou de estado."""
    pedido = await app.state.pedidos.por_id(pedido_id)
    if pedido is None:
        return
    await _publicar(
        app,
        PedidoAtualizado(
            em=agora(),
            pedido_id=pedido.id,
            session_id=await _sessao_do(app, pedido_id),
            status=pedido.status.value,
            total=pedido.total,
            razao_social=pedido.empresa.razao_social,
            url_pagamento=pedido.url_pagamento,
        ),
    )


async def _abrir_fila_da_nota(app: FastAPI, pedido_id: str) -> None:
    """Pagamento confirmado: o grafo fiscal entra e para no `interrupt` (REQ-1).

    **Falhar aqui não derruba o webhook, e isso não é tolerância a erro — é a
    consequência de a fila do operador ser derivada do banco.** O pedido já está em
    `aguardando_aprovacao_nf`, então ele aparece na fila de qualquer jeito, e a rota
    de aprovação conduz o grafo do começo quando a thread não existe
    (`fiscal.conduzir_ate_o_fim`). Devolver 5xx aqui faria o gateway reenviar um
    evento que já teve efeito, pelo motivo errado.

    O log é `exception` de propósito: o caminho normal é a thread abrir, e cair aqui
    significa que o checkpointer não respondeu — notícia, não ruído.
    """
    try:
        await abrir_fila_da_nota(app.state.emissao, pedido_id)
    except Exception:
        logger.exception(
            "não consegui abrir a pausa da nota para o pedido %s; ele continua na fila "
            "pelo status, e a aprovação conduz o grafo do começo",
            pedido_id,
        )

    # O sino do painel. Fora do `try` de propósito: a fila é derivada do status do
    # pedido, então ela existe mesmo quando a pausa não abriu — e o operador precisa
    # ser avisado justamente nesse caso, que é o mais difícil de perceber.
    await _anunciar_o_pedido(app, pedido_id)
    pedido = await app.state.pedidos.por_id(pedido_id)
    if pedido is not None:
        await _publicar(
            app,
            AprovacaoPendente(
                em=agora(),
                pedido_id=pedido.id,
                total=pedido.total,
                razao_social=pedido.empresa.razao_social,
            ),
        )


async def _pedido_ou_404(request: Request, pedido_id: str) -> Any:
    pedido = await request.app.state.pedidos.por_id(pedido_id)
    if pedido is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pedido não encontrado")
    return pedido


app = create_app()

__all__ = ["InMemoryConfigStore", "app", "create_app"]

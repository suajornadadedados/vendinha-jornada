"""The chat endpoint: streaming, and the session identity that survives it.

No risk marker here on purpose. These are feature tests — `docs/testes.md` §3 item 1
("toda feature nova nasce com teste unitário") — and the `risco` marker is reserved
for the tests that close a line of the matrix, so that `pytest tests -m risco` keeps
answering a useful question.

The graph is injected rather than built: the endpoint's job is to turn a stream of
tokens into server-sent events and to keep a session id straight, and neither of
those needs Postgres or a real model to be provable.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.app import create_app
from vendinha.catalogo import BuscaEmMemoria, CatalogoEmMemoria, carregar_seed
from vendinha.config_store import InMemoryConfigStore
from vendinha.graph import build_graph, session_config
from vendinha.providers import PROVIDERS, Provider
from vendinha.subagents import (
    PROMPT_RECOMENDACAO,
    RECOMENDACAO,
    Subagent,
    recomendacao,
    registrar,
)


def _sem_catalogo() -> Subagent:
    """O subagent da recomendação sem nenhuma tool.

    Este arquivo não mede recomendação — mede a fronteira HTTP. Um subagent sem tool
    mantém o grafo no formato de uma volta só, que é o que estas asserções
    descrevem, e deixa o laço de tools para quem o testa.
    """
    return registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, [])


CATALOGO_DO_SEED = Path(__file__).resolve().parents[2] / "data" / "catalogo"


def _catalogo_de_teste() -> CatalogoEmMemoria:
    """O catálogo que a subida confere (R-10), sem contêiner.

    `create_app` recusa subir com catálogo vazio, e é de propósito: sem `make
    seed` o agente responde "não encontrei nada" com toda a sinceridade, o que
    parece falha do modelo e é falha de setup. O teste percorre esse preflight de
    verdade em vez de contorná-lo — era essa a ressalva R-14.
    """
    return CatalogoEmMemoria(carregar_seed(CATALOGO_DO_SEED))


class ModeloQuePedeTool(BaseChatModel):
    """Um duplo de modelo cujas `tool_calls` sobrevivem ao streaming.

    O `GenericFakeChatModel` implementa `_stream` e monta os chunks so a partir do
    texto — as `tool_calls` somem no caminho, o `ToolNode` nunca roda, e um teste
    escrito sobre ele passa com e sem o filtro que deveria estar testando. Foi
    exatamente o que aconteceu: a primeira versao deste teste nao reprovava quando
    a correcao era removida.

    Implementando so `_generate`, o `astream` cai no caminho de uma volta so e o
    chunk chega inteiro, com as `tool_calls` dentro.
    """

    respostas: list[AIMessage]

    @property
    def _llm_type(self) -> str:
        return "modelo-que-pede-tool"

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        del tools, tool_choice, kwargs
        return self

    def _generate(
        self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=self.respostas.pop(0))])


@pytest.fixture
def checkpointer() -> InMemorySaver:
    return InMemorySaver()


@pytest.fixture
def graph(checkpointer: InMemorySaver) -> Any:
    answers = [AIMessage(content=t) for t in ("bom dia, tudo joia", "pois nao", "as ordens")]
    return build_graph(GenericFakeChatModel(messages=iter(answers)), checkpointer, _sem_catalogo())


@pytest.fixture
def client(graph: Any) -> Iterator[TestClient]:
    # The store is injected for the same reason the graph is: `ConfigStore` is a
    # protocol with a real in-memory implementation, so nothing internal is mocked
    # and no container is needed (docs/testes.md §4).
    with TestClient(
        create_app(graph=graph, store=InMemoryConfigStore(), catalogo=_catalogo_de_teste())
    ) as test_client:
        yield test_client


def _events(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse the SSE body into (event, data) pairs."""
    parsed: list[tuple[str, dict[str, Any]]] = []
    name = ""
    for line in body.splitlines():
        if line.startswith("event:"):
            name = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            parsed.append((name, json.loads(line.removeprefix("data:").strip())))
    return parsed


def test_chat_streams_the_answer_as_server_sent_events(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "oi, bom dia"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _events(response.text)
    kinds = [name for name, _ in events]
    assert kinds[0] == "session", "the client needs the id before any token"
    assert kinds[-1] == "done", "a stream with no explicit end leaves the client waiting"

    text = "".join(data["text"] for name, data in events if name == "token")
    assert text == "bom dia, tudo joia"


def test_a_request_without_a_session_id_gets_one_back(client: TestClient) -> None:
    events = _events(client.post("/chat", json={"message": "oi"}).text)
    session_id = events[0][1]["session_id"]

    assert session_id, "without an id the client cannot continue the conversation"
    assert len(session_id) >= 32, "session id too short to be a uuid"


def test_the_same_session_id_continues_the_same_conversation(
    client: TestClient, graph: Any
) -> None:
    first = _events(client.post("/chat", json={"message": "quero um presente"}).text)
    session_id = first[0][1]["session_id"]

    client.post("/chat", json={"message": "para minha mae", "session_id": session_id})

    state = graph.get_state(session_config(session_id))
    said = [m.content for m in state.values["messages"]]
    assert "quero um presente" in said, "the second turn opened a new conversation"
    assert "para minha mae" in said


def test_a_new_session_id_does_not_see_the_previous_conversation(
    client: TestClient, graph: Any
) -> None:
    first = _events(client.post("/chat", json={"message": "segredo"}).text)
    second = _events(client.post("/chat", json={"message": "outra pessoa"}).text)

    assert first[0][1]["session_id"] != second[0][1]["session_id"]

    state = graph.get_state(session_config(second[0][1]["session_id"]))
    assert "segredo" not in [m.content for m in state.values["messages"]]


def test_an_empty_message_is_refused_by_the_contract(client: TestClient) -> None:
    """Pydantic on the boundary, not an `if` inside the handler (CLAUDE.md)."""
    assert client.post("/chat", json={"message": "   "}).status_code == 422
    assert client.post("/chat", json={}).status_code == 422


def test_a_failure_mid_stream_becomes_an_event_and_leaks_nothing() -> None:
    """After the first byte the status line is already 200 — a 500 is no longer available.

    And the detail the customer sees must not describe our infrastructure: the
    exception text carries DSNs, model ids and limits, and `adversarial-006` fails
    a run that leaks configuration or tool names into an answer.
    """

    class BrokenStream:
        """An async iterator that fails on the first pull.

        Written as an explicit iterator rather than as a generator with an
        unreachable `yield` after the `raise`: that shape is the usual trick, and
        `warn_unreachable` is right to flag it.
        """

        def __aiter__(self) -> "BrokenStream":
            return self

        async def __anext__(self) -> Any:
            raise RuntimeError("connection to postgresql://vendinha:vendinha@127.0.0.1:5432 failed")

    class BrokenGraph:
        def astream(self, *_: Any, **__: Any) -> BrokenStream:
            return BrokenStream()

    with TestClient(
        create_app(graph=BrokenGraph(), store=InMemoryConfigStore(), catalogo=_catalogo_de_teste())
    ) as test_client:
        response = test_client.post("/chat", json={"message": "oi"})

    assert response.status_code == 200
    events = _events(response.text)
    kinds = [name for name, _ in events]
    assert kinds == ["session", "error", "done"], "the stream must end even when it breaks"

    detail = next(data["detail"] for name, data in events if name == "error")
    for leak in ("postgres", "127.0.0.1", "vendinha:", "RuntimeError", "5432"):
        assert leak not in detail, f"the customer-facing message leaked {leak!r}"


def test_health_says_the_service_is_up(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"


def test_the_model_list_is_warmed_before_the_first_request(
    graph: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cold, o primeiro pedido com `model` custava 4,0s contra um alvo de 3s.

    A primeira mensagem e a que alguem esta olhando, e era a unica que pagava a
    consulta aos fornecedores. O aquecimento no `lifespan` conserta isso — e este
    teste existe porque a terceira verificacao apontou que aquele trecho vivia num
    ramo do lifespan que nenhum teste percorria.
    """
    chamadas = [0]

    def listar(_: str) -> list[str]:
        chamadas[0] += 1
        return ["claude-haiku-4-5"]

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-" + "z" * 20)
    monkeypatch.setitem(PROVIDERS, "anthropic", Provider("anthropic", "ANTHROPIC_API_KEY", listar))

    with TestClient(
        create_app(graph=graph, store=InMemoryConfigStore(), catalogo=_catalogo_de_teste())
    ) as cliente:
        assert chamadas[0] == 1, "a lista nao foi aquecida no boot"
        cliente.get("/models")
        assert chamadas[0] == 1, "o boot aqueceu mas a requisicao consultou de novo"


@pytest.mark.risco("R4")
def test_the_stream_never_carries_a_tool_return_to_the_customer() -> None:
    """R4 — o retorno da tool é JSON, e ele NÃO é resposta do atendente.

    `stream_mode="messages"` emite todas as mensagens do grafo, `ToolMessage`
    inclusive. Sem filtro, o cliente recebia o payload inteiro do catálogo no meio
    da frase — ids, nomes de campo, estrutura interna — e a coisa foi vista assim,
    no navegador, antes de existir este teste.

    Não é só feio: `adversarial-004` e `adversarial-006` reprovam uma execução que
    revela nome de tool ou estrutura interna do agente, e um retorno de tool
    despejado no chat revela os dois de uma vez.
    """
    seed = carregar_seed(CATALOGO_DO_SEED)
    pedido = AIMessage(
        content="Deixa eu conferir.",
        tool_calls=[
            {
                "name": "consultar_preco",
                "args": {"produto_ids": ["queijo-canastra-meia-cura"]},
                "id": "chamada-1",
            }
        ],
    )

    graph = build_graph(
        ModeloQuePedeTool(respostas=[pedido, AIMessage(content="Sai por R$ 89,90.")]),
        InMemorySaver(),
        recomendacao(BuscaEmMemoria(seed), CatalogoEmMemoria(seed), 30.0),
    )

    with TestClient(
        create_app(graph=graph, store=InMemoryConfigStore(), catalogo=_catalogo_de_teste())
    ) as cliente:
        resposta = cliente.post("/chat", json={"message": "quanto custa o Canastra?"})

    dito = "".join(dados["text"] for nome, dados in _events(resposta.text) if nome == "token")

    assert "Deixa eu conferir." in dito, "o texto do atendente tem que continuar passando"
    assert "encontrados" not in dito, f"o retorno da tool vazou para o cliente: {dito!r}"
    assert "queijo-canastra-meia-cura" not in dito, "o id interno vazou para o cliente"
    assert "consultar_preco" not in dito, "o nome da tool vazou para o cliente"

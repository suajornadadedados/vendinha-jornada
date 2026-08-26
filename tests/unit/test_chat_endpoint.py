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
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.app import create_app
from vendinha.graph import build_graph, session_config


@pytest.fixture
def checkpointer() -> InMemorySaver:
    return InMemorySaver()


@pytest.fixture
def graph(checkpointer: InMemorySaver) -> Any:
    respostas = [AIMessage(content=t) for t in ("bom dia, tudo joia", "pois nao", "as ordens")]
    return build_graph(GenericFakeChatModel(messages=iter(respostas)), checkpointer)


@pytest.fixture
def client(graph: Any) -> Iterator[TestClient]:
    with TestClient(create_app(graph=graph)) as cliente:
        yield cliente


def _eventos(corpo: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse the SSE body into (event, data) pairs."""
    saida: list[tuple[str, dict[str, Any]]] = []
    nome = ""
    for linha in corpo.splitlines():
        if linha.startswith("event:"):
            nome = linha.removeprefix("event:").strip()
        elif linha.startswith("data:"):
            saida.append((nome, json.loads(linha.removeprefix("data:").strip())))
    return saida


def test_chat_streams_the_answer_as_server_sent_events(client: TestClient) -> None:
    resposta = client.post("/chat", json={"message": "oi, bom dia"})

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/event-stream")

    eventos = _eventos(resposta.text)
    tipos = [nome for nome, _ in eventos]
    assert tipos[0] == "session", "o cliente precisa do id antes de qualquer token"
    assert tipos[-1] == "done", "um stream sem fim explicita deixa o cliente esperando"

    texto = "".join(dado["text"] for nome, dado in eventos if nome == "token")
    assert texto == "bom dia, tudo joia"


def test_a_request_without_a_session_id_gets_one_back(client: TestClient) -> None:
    eventos = _eventos(client.post("/chat", json={"message": "oi"}).text)
    session_id = eventos[0][1]["session_id"]

    assert session_id, "sem id devolvido o cliente nao tem como continuar a conversa"
    assert len(session_id) >= 32, "id de sessao curto demais para ser um uuid"


def test_the_same_session_id_continues_the_same_conversation(
    client: TestClient, graph: Any
) -> None:
    primeira = _eventos(client.post("/chat", json={"message": "quero um presente"}).text)
    session_id = primeira[0][1]["session_id"]

    client.post("/chat", json={"message": "para minha mae", "session_id": session_id})

    estado = graph.get_state(session_config(session_id))
    ditos = [m.content for m in estado.values["messages"]]
    assert "quero um presente" in ditos, "o segundo turno abriu uma conversa nova"
    assert "para minha mae" in ditos


def test_a_new_session_id_does_not_see_the_previous_conversation(
    client: TestClient, graph: Any
) -> None:
    primeira = _eventos(client.post("/chat", json={"message": "segredo"}).text)
    segunda = _eventos(client.post("/chat", json={"message": "outra pessoa"}).text)

    assert primeira[0][1]["session_id"] != segunda[0][1]["session_id"]

    estado = graph.get_state(session_config(segunda[0][1]["session_id"]))
    assert "segredo" not in [m.content for m in estado.values["messages"]]


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

    class GrafoQueQuebra:
        async def astream(self, *_: Any, **__: Any) -> Any:
            raise RuntimeError("connection to postgresql://vendinha:vendinha@127.0.0.1:5432 failed")
            yield  # pragma: no cover - unreachable, keeps this an async generator

    with TestClient(create_app(graph=GrafoQueQuebra())) as cliente:
        resposta = cliente.post("/chat", json={"message": "oi"})

    assert resposta.status_code == 200
    eventos = _eventos(resposta.text)
    tipos = [nome for nome, _ in eventos]
    assert tipos == ["session", "error", "done"], "o stream precisa terminar mesmo quebrando"

    detalhe = next(dado["detail"] for nome, dado in eventos if nome == "error")
    for vazamento in ("postgres", "127.0.0.1", "vendinha:", "RuntimeError", "5432"):
        assert vazamento not in detalhe, f"a mensagem ao cliente vazou {vazamento!r}"


def test_health_says_the_service_is_up(client: TestClient) -> None:
    corpo = client.get("/health").json()
    assert corpo["status"] == "ok"

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
from vendinha.config_store import InMemoryConfigStore
from vendinha.graph import build_graph, session_config


@pytest.fixture
def checkpointer() -> InMemorySaver:
    return InMemorySaver()


@pytest.fixture
def graph(checkpointer: InMemorySaver) -> Any:
    answers = [AIMessage(content=t) for t in ("bom dia, tudo joia", "pois nao", "as ordens")]
    return build_graph(GenericFakeChatModel(messages=iter(answers)), checkpointer)


@pytest.fixture
def client(graph: Any) -> Iterator[TestClient]:
    # The store is injected for the same reason the graph is: `ConfigStore` is a
    # protocol with a real in-memory implementation, so nothing internal is mocked
    # and no container is needed (docs/testes.md §4).
    with TestClient(create_app(graph=graph, store=InMemoryConfigStore())) as test_client:
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

    class BrokenGraph:
        async def astream(self, *_: Any, **__: Any) -> Any:
            raise RuntimeError("connection to postgresql://vendinha:vendinha@127.0.0.1:5432 failed")
            yield  # pragma: no cover - unreachable, keeps this an async generator

    with TestClient(create_app(graph=BrokenGraph(), store=InMemoryConfigStore())) as test_client:
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

"""ADR-012 — the provider is configuration, and the credential is a secret with rules.

Three properties are being defended here, and only the first is about convenience:

1. the code never branches on the vendor, and the model list is *read from the
   provider* rather than remembered in a constant somewhere in this repository;
2. the credential never comes back out through the API — the strongest version of
   that claim lives in `tests/security/test_pii_redaction.py`, which also covers
   traces and logs;
3. the model a chat request names comes from the server's list, because free text
   there would let a client pick which vendor the server authenticates to.

The vendor seam is `Provider.list_models`: it is the adapter to a third party's
HTTP API, which is precisely where `docs/testes.md` §4 allows a test to stand
something in. Nothing internal is faked — the config store is a real in-memory
implementation of the same protocol Postgres implements.
"""

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.app import create_app
from vendinha.config import get_settings
from vendinha.config_store import InMemoryConfigStore
from vendinha.credentials import CredentialsCorrupted, CredentialsUnavailable, Vault
from vendinha.graph import build_graph
from vendinha.providers import PROVIDERS, Provider, effective_credentials
from vendinha.subagents import (
    PROMPT_RECOMENDACAO,
    RECOMENDACAO,
    Subagent,
    registrar,
)


def _sem_catalogo() -> Subagent:
    """O subagent da recomendação sem nenhuma tool.

    Este arquivo não mede recomendação — mede a configuração de provedor. Um subagent sem tool
    mantém o grafo no formato de uma volta só, que é o que estas asserções
    descrevem, e deixa o laço de tools para quem o testa.
    """
    return registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, [])


FAKE_KEY = "sk-ant-api03-" + "Z" * 40


@pytest.fixture(autouse=True)
def fresh_settings() -> Iterator[None]:
    """`get_settings` is cached for the process; a test that edits the environment
    has to invalidate it, or the next test inherits the edit."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def no_ambient_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """The developer's real `.env` must not decide what these tests observe."""
    for provider in PROVIDERS.values():
        monkeypatch.delenv(provider.env_var, raising=False)


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin an encryption key for the whole file, from the test and not from the machine.

    Four tests here write a credential, and `PUT /config` refuses that with 503 when
    `CONFIG_ENCRYPTION_KEY` is missing. Leaving it to the environment made them pass
    on the author's machine and fail everywhere else — including the CI job, which
    runs without a `.env` and is a required check.

    Empty string rather than a real absence when the test wants "not configured":
    `Settings` reads the repository `.env` as a second source, so deleting the
    variable from the process environment does not make it absent, it makes the file
    win. `test_the_config_response_says_whether_encryption_is_ready` overrides this
    fixture on purpose, and is the only test here that may.
    """
    monkeypatch.setenv("CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture
def offered_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in at the vendor seam: no network, and no catalogue written from memory."""
    monkeypatch.setitem(
        PROVIDERS,
        "anthropic",
        Provider("anthropic", "ANTHROPIC_API_KEY", lambda _: ["claude-haiku-4-5", "claude-opus-5"]),
    )


class _RelogioFalso:
    """Só o que `app.py` usa do módulo `time`, para o teste poder empurrar o relógio."""

    def __init__(self, inicio: float) -> None:
        self._agora = inicio

    def avancar(self, segundos: float) -> None:
        self._agora += segundos

    def monotonic(self) -> float:
        return self._agora


@pytest.fixture
def contador_de_chamadas(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Conta quantas vezes o fornecedor foi consultado de verdade."""
    chamadas = [0]

    def listar(_: str) -> list[str]:
        chamadas[0] += 1
        return ["claude-haiku-4-5", "claude-opus-5"]

    monkeypatch.setitem(PROVIDERS, "anthropic", Provider("anthropic", "ANTHROPIC_API_KEY", listar))
    return chamadas


@pytest.fixture
def store() -> InMemoryConfigStore:
    return InMemoryConfigStore()


@pytest.fixture
def client(store: InMemoryConfigStore) -> Iterator[TestClient]:
    graph = build_graph(
        GenericFakeChatModel(messages=iter([AIMessage(content="pois nao")])),
        InMemorySaver(),
        _sem_catalogo(),
    )
    with TestClient(create_app(graph=graph, store=store)) as test_client:
        yield test_client


# --------------------------------------------------------------------- the vault


def test_the_vault_round_trips_the_credential_map() -> None:
    vault = Vault(Fernet.generate_key().decode())
    assert vault.open(vault.seal({"anthropic": FAKE_KEY})) == {"anthropic": FAKE_KEY}


def test_an_empty_store_is_an_empty_map_not_an_error() -> None:
    assert Vault(Fernet.generate_key().decode()).open(None) == {}


def test_the_sealed_blob_does_not_contain_the_secret() -> None:
    """Belt and braces: the point of sealing is that the bytes are opaque."""
    sealed = Vault(Fernet.generate_key().decode()).seal({"anthropic": FAKE_KEY})
    assert FAKE_KEY.encode() not in sealed


def test_without_an_encryption_key_writing_is_refused_not_downgraded() -> None:
    """Storing it in the clear "just for now" is how a demo reaches production."""
    with pytest.raises(CredentialsUnavailable):
        Vault(None).seal({"anthropic": FAKE_KEY})


def test_a_rotated_key_says_so_instead_of_reporting_no_credentials() -> None:
    """Reporting an empty store would send the operator to re-enter keys already there."""
    sealed = Vault(Fernet.generate_key().decode()).seal({"anthropic": FAKE_KEY})
    with pytest.raises(CredentialsCorrupted):
        Vault(Fernet.generate_key().decode()).open(sealed)


def test_the_hint_shows_only_the_tail() -> None:
    hint = Vault.hint(FAKE_KEY)
    assert hint.endswith(FAKE_KEY[-4:])
    assert FAKE_KEY[:-4] not in hint


# ------------------------------------------------------------------- the endpoints


def test_reading_the_configuration_never_returns_the_key(
    client: TestClient, store: InMemoryConfigStore
) -> None:
    import asyncio

    asyncio.run(
        store.save(selected_model="anthropic:claude-haiku-4-5", credentials={"anthropic": FAKE_KEY})
    )

    response = client.get("/config")
    assert response.status_code == 200
    assert FAKE_KEY not in json.dumps(response.json())

    anthropic = next(p for p in response.json()["providers"] if p["provider"] == "anthropic")
    assert anthropic["configured"] is True
    assert anthropic["source"] == "banco"
    assert anthropic["hint"].endswith(FAKE_KEY[-4:])


def test_writing_a_credential_stores_it_and_never_echoes_it(client: TestClient) -> None:
    response = client.put("/config", json={"provider": "anthropic", "api_key": FAKE_KEY})

    assert response.status_code == 200, response.text
    assert FAKE_KEY not in response.text
    anthropic = next(p for p in response.json()["providers"] if p["provider"] == "anthropic")
    assert anthropic["configured"] is True and anthropic["source"] == "banco"


def test_a_stored_credential_wins_over_the_environment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The environment is the quickstart fallback, never an override (ADR-012).

    If it won, changing the key through the UI would silently do nothing on any
    machine that has one in `.env` — the worst kind of no-op.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-do-ambiente-" + "x" * 20)
    assert client.get("/config").json()["providers"][0]["source"] == "ambiente"

    client.put("/config", json={"provider": "anthropic", "api_key": FAKE_KEY})
    depois = next(
        p for p in client.get("/config").json()["providers"] if p["provider"] == "anthropic"
    )
    assert depois["source"] == "banco"
    assert depois["hint"].endswith(FAKE_KEY[-4:])


def test_the_stored_key_is_the_one_the_model_actually_gets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-012: o que está no banco vence o que está no ambiente — na chave, não na vitrine.

    Testado na função que decide, e não pela resposta do `/config`. O teste anterior
    afirmava sobre o campo `source`, que `read_config` calcula direto do store — então
    inverter a precedência de verdade deixava a suíte verde. O modo de falha é o pior
    possível: a UI diz `source: "banco"`, mostra a dica da chave nova, e o processo
    continua gastando na chave velha do `.env`.
    """
    do_ambiente = "sk-ant-ambiente-" + "x" * 20
    monkeypatch.setenv("ANTHROPIC_API_KEY", do_ambiente)

    assert effective_credentials({})["anthropic"] == do_ambiente, (
        "sem nada gravado, o ambiente vale"
    )
    assert effective_credentials({"anthropic": FAKE_KEY})["anthropic"] == FAKE_KEY

    # Provedor que só existe no ambiente continua disponível: o ambiente é fallback,
    # não é lista de exclusão.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-" + "y" * 20)
    resolvidas = effective_credentials({"anthropic": FAKE_KEY})
    assert resolvidas["anthropic"] == FAKE_KEY
    assert resolvidas["openai"].startswith("sk-openai-")


def test_an_unknown_provider_and_a_malformed_model_are_refused(client: TestClient) -> None:
    assert client.put("/config", json={"provider": "gemini", "api_key": "x"}).status_code == 422
    assert client.put("/config", json={"model": "claude-haiku-4-5"}).status_code == 422
    assert client.put("/config", json={"model": "inexistente:algo"}).status_code == 422
    assert client.put("/config", json={}).status_code == 422


@pytest.mark.usefixtures("offered_models")
def test_the_model_list_comes_from_the_provider(client: TestClient) -> None:
    """No catalogue of model ids lives in this repository — that is the point.

    A list written from memory is stale the week after, and nothing tells you. It is
    the same standard ADR-001 imposes on the agent, applied to our own source.
    """
    client.put("/config", json={"provider": "anthropic", "api_key": FAKE_KEY})

    body = client.get("/models").json()
    assert body["models"] == ["anthropic:claude-haiku-4-5", "anthropic:claude-opus-5"]
    assert body["selected"] == "anthropic:claude-haiku-4-5"


@pytest.mark.usefixtures("offered_models")
def test_a_provider_with_no_credential_offers_nothing(client: TestClient) -> None:
    assert client.get("/models").json()["models"] == []


@pytest.mark.usefixtures("offered_models")
def test_chat_refuses_a_model_outside_the_server_list(client: TestClient) -> None:
    """Free text here would let the client pick the vendor and the spend (ADR-012)."""
    client.put("/config", json={"provider": "anthropic", "api_key": FAKE_KEY})

    recusado = client.post("/chat", json={"message": "oi", "model": "openai:gpt-4o"})
    assert recusado.status_code == 422

    aceito = client.post("/chat", json={"message": "oi", "model": "anthropic:claude-opus-5"})
    assert aceito.status_code == 200


def test_configuration_cannot_be_written_outside_local(
    monkeypatch: pytest.MonkeyPatch, store: InMemoryConfigStore
) -> None:
    """There is no authentication yet, and this route stores a provider credential.

    Shipping it open to a public host with a plan to fix it later is how it never
    gets fixed. Reading stays allowed — it exposes nothing.
    """
    monkeypatch.setenv("APP_ENV", "prod")
    get_settings.cache_clear()

    graph = build_graph(GenericFakeChatModel(messages=iter([])), InMemorySaver(), _sem_catalogo())
    with TestClient(create_app(graph=graph, store=store)) as prod:
        assert prod.get("/config").json()["editable"] is False
        negado = prod.put("/config", json={"provider": "anthropic", "api_key": FAKE_KEY})
        assert negado.status_code == 403


@pytest.mark.parametrize("configured", [False, True])
def test_the_config_response_says_whether_encryption_is_ready(
    monkeypatch: pytest.MonkeyPatch, store: InMemoryConfigStore, configured: bool
) -> None:
    """An operator who cannot save needs to know why before they try.

    Both states are pinned from the environment rather than read from it: a test
    whose answer depends on whether the developer happens to have a key in `.env`
    passes on one machine and fails on the next, and the failure looks like a bug
    in the code.
    """
    # Empty string rather than `delenv`: `Settings` reads the repository `.env` as a
    # second source, so removing the variable from the process environment does not
    # make it absent — it makes the file win. An explicit empty value is the only
    # way to pin "not configured" regardless of the developer's machine.
    monkeypatch.setenv(
        "CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode() if configured else ""
    )
    get_settings.cache_clear()

    graph = build_graph(GenericFakeChatModel(messages=iter([])), InMemorySaver(), _sem_catalogo())
    with TestClient(create_app(graph=graph, store=store)) as test_client:
        body: dict[str, Any] = test_client.get("/config").json()
        assert body["encryption_ready"] is configured

        if not configured:
            # 503, not 500: the service is fine, the deployment is incomplete, and
            # the person reading it is the one who can fix it.
            refused = test_client.put(
                "/config", json={"provider": "anthropic", "api_key": FAKE_KEY}
            )
            assert refused.status_code == 503
            assert "CONFIG_ENCRYPTION_KEY" in refused.text


def test_the_model_list_is_not_fetched_again_on_every_request(
    client: TestClient, contador_de_chamadas: list[int]
) -> None:
    """O cache entrou para consertar uma metrica; sem teste ele sai do mesmo jeito.

    Sem ele, todo `POST /chat` que traz `model` — que e toda mensagem que a UI da
    S-07 vai mandar — consulta os fornecedores por HTTP antes de responder. Medido:
    p95 do primeiro token de 1,0 s para 3,3 s, alem de duas chamadas a fornecedor por
    turno de conversa, que e superficie de rate limit e de custo dentro do R6.
    """
    client.put("/config", json={"provider": "anthropic", "api_key": FAKE_KEY})
    antes = contador_de_chamadas[0]

    for _ in range(3):
        client.get("/models")

    assert contador_de_chamadas[0] == antes + 1, "cada requisicao esta consultando o fornecedor"


def test_writing_configuration_invalidates_the_model_cache(
    client: TestClient, contador_de_chamadas: list[int]
) -> None:
    """Cache que nao invalida esconde a credencial que o operador acabou de gravar."""
    client.get("/models")
    antes = contador_de_chamadas[0]

    client.put("/config", json={"provider": "anthropic", "api_key": FAKE_KEY})
    client.get("/models")

    assert contador_de_chamadas[0] > antes, "o PUT /config nao invalidou a lista"


def test_the_model_cache_expires(
    client: TestClient, contador_de_chamadas: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """TTL infinito esconde uma chave posta direto no ambiente ate alguem reiniciar.

    O `PUT /config` invalida o cache, mas nem toda credencial chega por ali: o
    ambiente e o caminho do quickstart (ADR-012). Sem expiracao, quem exporta
    `OPENAI_API_KEY` e recarrega a pagina continua sem ver os modelos, e nada no
    sistema explica por que.
    """
    client.put("/config", json={"provider": "anthropic", "api_key": FAKE_KEY})
    client.get("/models")
    antes = contador_de_chamadas[0]
    assert antes > 0, "sem credencial nenhum fornecedor e consultado, e o teste nao mede nada"

    # O relogio avanca uma hora; o TTL NAO e tocado. A versao anterior deste teste
    # trocava `MODELS_CACHE_SECONDS` por zero, e por isso nao enxergava o valor da
    # constante: um TTL de 1e12 segundos passava. Uma hora e um numero fixo de
    # proposito — qualquer TTL que sobreviva a ela ja nao e um TTL, e um restart.
    relogio = _RelogioFalso(inicio=time.monotonic())
    monkeypatch.setattr("vendinha.app.time", relogio)
    relogio.avancar(3600)
    client.get("/models")

    assert contador_de_chamadas[0] > antes, "a lista nunca expira: so um restart a atualiza"

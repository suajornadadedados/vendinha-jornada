"""R1, R6 — a subida recusa um catálogo que não está pronto, e diz qual comando resolve.

Duas ressalvas da verificação independente da S-02 fecham aqui, e elas são a
mesma história contada de dois ângulos.

**R-10 — o setup esquecido só aparecia na primeira mensagem do cliente.** Quem
não rodava `make db-setup` recebia erro de tabela inexistente no meio de um
atendimento. Com o catálogo no banco (S-03) isso ficou pior: sem `make seed` a
tabela existe e está vazia, a busca não devolve nada, e o agente responde *"não
encontrei nada disso"* com toda a sinceridade. **Parece falha do modelo e é falha
de setup** — a pior classe de falha para diagnosticar, porque manda a pessoa
depurar o prompt.

**R-14 — o ramo de produção do `lifespan` não era alcançado por nenhum teste.** A
consequência estava escrita na própria ressalva: *"qualquer coisa que entrar ali
nasce sem defesa"*. A conferência que este arquivo testa é justamente uma coisa
nova entrando ali. Por isso `create_app` passou a receber o `Catalogo` como porta:
o teste percorre o preflight de verdade, em vez de contorná-lo.

E o R-5, de tabela: `LOG_LEVEL` estava no `.env.example` marcado `(S-02)` e nenhum
código o lia.
"""

import logging
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.app import CatalogoIndisponivel, create_app
from vendinha.catalogo import Catalogo, CatalogoEmMemoria, Produto, carregar_seed
from vendinha.config import get_settings
from vendinha.config_store import InMemoryConfigStore
from vendinha.graph import build_graph
from vendinha.observability import install_log_redaction, unserved_probes_are_silenced
from vendinha.subagents import PROMPT_RECOMENDACAO, RECOMENDACAO, registrar

pytestmark = pytest.mark.requires_backend

CATALOGO_DO_SEED = Path(__file__).resolve().parents[2] / "data" / "catalogo"


class CatalogoQueNaoResponde:
    """A tabela `produto` que não existe — o sintoma de `make db-setup` esquecido."""

    async def por_ids(self, ids: Sequence[str]) -> dict[str, Produto]:
        del ids
        raise RuntimeError('relation "produto" does not exist')

    async def quantos(self) -> int:
        raise RuntimeError('relation "produto" does not exist')


def _app(catalogo: Catalogo) -> FastAPI:
    graph = build_graph(
        GenericFakeChatModel(messages=iter([AIMessage(content="pois nao")])),
        InMemorySaver(),
        registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, []),
    )
    return create_app(graph=graph, store=InMemoryConfigStore(), catalogo=catalogo)


@pytest.mark.risco("R1")
def test_the_application_refuses_to_start_with_an_empty_catalogue() -> None:
    """R1 — subir sem catálogo produz um agente que nega a loja inteira, educadamente.

    A alternativa — subir e avisar no log — é a que ninguém lê. Falhar aqui é
    ruidoso de propósito: a mensagem nomeia o comando que resolve.
    """
    with pytest.raises(CatalogoIndisponivel, match="make seed"):
        with TestClient(_app(CatalogoEmMemoria([]))):
            pass  # pragma: no cover - a subida não deve chegar aqui


@pytest.mark.risco("R1")
def test_the_application_refuses_to_start_when_the_catalogue_table_is_missing() -> None:
    """R1, R-10 — o erro de tabela inexistente aparece no boot, não no atendimento.

    Era literalmente o texto da ressalva: *"quem esquecer `make db-setup` recebe
    erro de tabela inexistente na primeira mensagem, não no boot"*.
    """
    with pytest.raises(CatalogoIndisponivel, match="make db-setup"):
        with TestClient(_app(CatalogoQueNaoResponde())):
            pass  # pragma: no cover - a subida não deve chegar aqui


@pytest.mark.risco("R1")
def test_the_application_starts_when_the_catalogue_is_seeded() -> None:
    """R1 — a outra metade: o preflight precisa deixar passar o estado correto.

    Um preflight que recusa tudo é removido na primeira sexta-feira.
    """
    with TestClient(_app(CatalogoEmMemoria(carregar_seed(CATALOGO_DO_SEED)))) as cliente:
        assert cliente.get("/health").json() == {"status": "ok"}


@pytest.mark.risco("R1")
def test_the_boot_check_reads_the_catalogue_port_and_not_a_hardcoded_database() -> None:
    """R1, R-14 — o preflight é percorrido pelo teste, e não contornado por ele.

    É o ponto inteiro da ressalva R-14. Se `create_app` continuasse construindo o
    `PostgresCatalogo` por dentro, este arquivo teria que ou subir um contêiner ou
    desligar a conferência — e "desligar para testar" é como um preflight vira
    decoração.
    """
    contadas: list[int] = []

    class CatalogoQueConta(CatalogoEmMemoria):
        async def quantos(self) -> int:
            contadas.append(1)
            return await super().quantos()

    with TestClient(_app(CatalogoQueConta(carregar_seed(CATALOGO_DO_SEED)))):
        pass

    assert contadas, "a subida não consultou o catálogo injetado"


# ------------------------------------------------------------------- LOG_LEVEL


@pytest.fixture
def logging_limpo() -> Iterator[None]:
    """Devolve o logger raiz como estava — nível global é estado de processo."""
    raiz = logging.getLogger()
    nivel, handlers = raiz.level, list(raiz.handlers)
    try:
        yield
    finally:
        raiz.setLevel(nivel)
        raiz.handlers[:] = handlers
        get_settings.cache_clear()


@pytest.mark.risco("R6")
@pytest.mark.usefixtures("logging_limpo")
def test_log_level_from_the_environment_is_actually_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R6, R-5 — a variável estava documentada e nenhum código a lia.

    Uma variável de ambiente documentada que não faz nada é pior do que uma
    variável ausente: quem a define acredita ter mudado alguma coisa, e depura o
    problema errado por meia hora.
    """
    logging.getLogger().setLevel(logging.INFO)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    get_settings.cache_clear()

    install_log_redaction()

    assert logging.getLogger().level == logging.DEBUG


@pytest.mark.risco("R6")
@pytest.mark.usefixtures("logging_limpo")
def test_a_nonsense_log_level_leaves_the_current_one_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R6 — um valor errado não derruba a subida nem apaga o logging.

    `LOG_LEVEL=verbose` é o erro de digitação óbvio. Levantar aqui mataria o
    processo por uma linha de configuração cosmética; zerar o nível deixaria a
    aplicação muda. Manter o que estava é a única das três que não surpreende.
    """
    logging.getLogger().setLevel(logging.WARNING)
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    get_settings.cache_clear()

    install_log_redaction()

    assert logging.getLogger().level == logging.WARNING


# ------------------------------------------------------- filtro do log de acesso


@pytest.fixture
def acesso_sem_filtro() -> Iterator[logging.Logger]:
    """`uvicorn.access` sem nenhum filtro, devolvido como estava.

    O logger é global ao processo, e quem o suja quebra o vizinho — inclusive o
    próprio assert de partida deste teste, que precisa começar cru para significar
    alguma coisa.
    """
    acesso = logging.getLogger("uvicorn.access")
    antes = list(acesso.filters)
    acesso.filters = []
    try:
        yield acesso
    finally:
        acesso.filters = antes


@pytest.mark.usefixtures("acesso_sem_filtro")
def test_the_application_silences_the_unserved_probes_when_it_starts() -> None:
    """Testar a função que filtra não é testar que alguém a chama.

    A lição é a da S-02 — `redaction_is_installed`, rodada 2 —, e o commit que trouxe
    este filtro a citou no docstring e implementou mesmo assim só a metade de baixo:
    havia teste de `silence_unserved_probes()` → logger, e nenhum de aplicação →
    função. Apagar a chamada do `lifespan` deixava os 1029 testes verdes (verificação
    independente da S-07, rodada 2, NC-4).
    """
    assert not unserved_probes_are_silenced(), "a fixture deveria ter deixado o logger cru"

    with TestClient(_app(CatalogoEmMemoria(carregar_seed(CATALOGO_DO_SEED)))):
        assert unserved_probes_are_silenced(), "a aplicação subiu sem ligar o filtro de acesso"

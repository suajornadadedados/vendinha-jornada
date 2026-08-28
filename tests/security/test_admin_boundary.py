"""O painel lista CNPJ, endereço e a conversa inteira. Ele não pode ficar aberto.

Mesma classe da fila do operador (R3, `test_operator_queue.py`), e o mesmo portão —
mas com uma diferença que justifica um arquivo próprio: a fila tinha três rotas e
o painel tem sete, e vai ganhar mais. **Os testes são parametrizados sobre a lista
de rotas do próprio app**, e não sobre uma lista escrita à mão: uma rota `/admin/*`
nova que esquecesse a verificação entra nesta parametrização sozinha e reprova, em
vez de nascer aberta e ninguém notar.

O segundo teste é sobre a outra porta que a S-07 abriu: `GET /eventos/sessao/{id}`
não tem token nenhum, de propósito — o segredo é o id opaco da conversa, como já
acontece com `nota.xml`. O que ele **não** pode fazer é entregar a conversa de
outra pessoa a quem tem um id qualquer.
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.app import create_app
from vendinha.catalogo import CatalogoEmMemoria, carregar_seed
from vendinha.config import get_settings
from vendinha.config_store import InMemoryConfigStore
from vendinha.eventos import BarramentoEmMemoria, agora
from vendinha.fiscal import FiscalEmMemoria
from vendinha.graph import build_graph
from vendinha.nota import MockNFAdapter
from vendinha.pedidos import PedidosEmMemoria
from vendinha.schemas import AprovacaoPendente, EventoDoPainel, MensagemRegistrada
from vendinha.subagents import PROMPT_RECOMENDACAO, RECOMENDACAO, registrar
from vendinha.telemetria import TelemetriaEmMemoria

pytestmark = pytest.mark.requires_backend

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGO = REPO_ROOT / "data" / "catalogo"
TOKEN = "token-do-operador-para-o-teste"  # noqa: S105
AUTORIZADO = {"X-Operador-Token": TOKEN}

MINHA = "sessao-de-quem-esta-olhando"
ALHEIA = "sessao-de-outro-cliente"


def fala(evento: EventoDoPainel) -> MensagemRegistrada:
    """Estreita o evento para a mensagem — e falha se vier de outro tipo.

    Existe porque a união é discriminada e o mypy recusa `.texto` num evento que
    pode não ter. Estreitar aqui não é cerimônia de tipo: transforma "chegou algo
    com o texto errado" e "chegou o evento errado" em duas falhas distintas.
    """
    assert isinstance(evento, MensagemRegistrada), f"esperava mensagem, veio {evento.tipo}"
    return evento


def _app(telemetria: TelemetriaEmMemoria, barramento: BarramentoEmMemoria) -> FastAPI:
    saver = InMemorySaver()
    return create_app(
        graph=build_graph(
            GenericFakeChatModel(messages=iter([AIMessage(content="oi")])),
            saver,
            registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, []),
        ),
        store=InMemoryConfigStore(),
        catalogo=CatalogoEmMemoria(carregar_seed(CATALOGO)),
        pedidos=PedidosEmMemoria(),
        fiscal=FiscalEmMemoria(),
        emissor=MockNFAdapter(),
        checkpointer=saver,
        telemetria=telemetria,
        barramento=barramento,
    )


@pytest.fixture
def com_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "operador_api_token", TOKEN)


@pytest.fixture
def sem_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nenhum token configurado, explicitamente.

    Sem esta fixture o teste da ausência dependeria de o `.env` da máquina não ter
    a variável, e passaria por acidente em quem nunca configurou a fila.
    """
    monkeypatch.setattr(get_settings(), "operador_api_token", None)


@pytest.fixture
def telemetria() -> TelemetriaEmMemoria:
    return TelemetriaEmMemoria()


@pytest.fixture
def barramento() -> BarramentoEmMemoria:
    return BarramentoEmMemoria()


@pytest.fixture
def client(telemetria: TelemetriaEmMemoria, barramento: BarramentoEmMemoria) -> Any:
    with TestClient(_app(telemetria, barramento)) as test_client:
        yield test_client


def rotas_do_painel() -> list[str]:
    """Toda rota `/admin/*` que o app registra, com um valor para cada parâmetro.

    Derivada do app e não escrita à mão: é o que faz uma rota nova entrar no teste
    sem ninguém se lembrar de a acrescentar.
    """
    app = _app(TelemetriaEmMemoria(), BarramentoEmMemoria())
    caminhos = []
    for rota in app.routes:
        caminho = getattr(rota, "path", "")
        if not caminho.startswith("/admin"):
            continue
        caminhos.append(
            caminho.replace("{session_id}", "qualquer").replace("{pedido_id}", "qualquer")
        )
    return sorted(set(caminhos))


@pytest.mark.risco("R5")
@pytest.mark.usefixtures("com_token")
@pytest.mark.parametrize("caminho", rotas_do_painel())
def test_nenhuma_rota_do_painel_responde_sem_o_token(client: TestClient, caminho: str) -> None:
    """O painel expõe CNPJ, endereço e a conversa — a porta é a mesma da fila."""
    assert client.get(caminho).status_code == 401


@pytest.mark.risco("R5")
@pytest.mark.usefixtures("com_token")
@pytest.mark.parametrize("caminho", rotas_do_painel())
def test_nenhuma_rota_do_painel_aceita_o_token_errado(client: TestClient, caminho: str) -> None:
    resposta = client.get(caminho, headers={"X-Operador-Token": TOKEN + "x"})
    assert resposta.status_code == 401


@pytest.mark.risco("R5")
@pytest.mark.usefixtures("sem_token")
@pytest.mark.parametrize("caminho", rotas_do_painel())
def test_sem_token_configurado_o_painel_fecha_inteiro(client: TestClient, caminho: str) -> None:
    """Fail-closed: esquecer a variável de ambiente não abre o painel.

    O oposto — "sem token, aceita tudo" — transformaria um `.env` incompleto num
    painel público com a conversa e o CNPJ de todo mundo dentro.
    """
    assert client.get(caminho, headers=AUTORIZADO).status_code == 401


@pytest.mark.risco("R5")
@pytest.mark.usefixtures("com_token")
def test_o_painel_responde_com_o_token_certo(client: TestClient) -> None:
    """A contraprova dos três acima: eles falhariam juntos se a rota não existisse."""
    assert client.get("/admin/conversas", headers=AUTORIZADO).status_code == 200
    assert client.get("/admin/metricas", headers=AUTORIZADO).status_code == 200


@pytest.mark.risco("R5")
async def test_o_stream_de_uma_sessao_nao_entrega_a_conversa_de_outra(
    barramento: BarramentoEmMemoria,
) -> None:
    """`/eventos/sessao/{id}` é aberto, e o id opaco é o segredo — como `nota.xml`.

    O que ele não pode é vazar. Este teste exercita o barramento pelo mesmo caminho
    que a rota usa, porque o filtro mora ali: assinar por sessão e receber só o que
    carrega aquele `session_id`.

    As três publicações cobrem as três formas de vazar: a conversa alheia, um
    evento sem sessão nenhuma, e — a contraprova — a conversa certa, que precisa
    passar.
    """
    async with barramento.assinar(sessao=MINHA) as fluxo:
        await barramento.publicar(
            MensagemRegistrada(
                em=agora(), session_id=ALHEIA, papel="cliente", texto="meu CNPJ e o pedido"
            )
        )
        await barramento.publicar(
            AprovacaoPendente(
                em=agora(), pedido_id="p1", total=Decimal("9500.00"), razao_social="ACME LTDA"
            )
        )
        await barramento.publicar(
            MensagemRegistrada(
                em=agora(), session_id=MINHA, papel="atendente", texto="sua nota saiu"
            )
        )

        primeiro = fala(await asyncio.wait_for(anext(fluxo), timeout=1))
        assert primeiro.session_id == MINHA
        assert primeiro.texto == "sua nota saiu"


@pytest.mark.risco("R5")
@pytest.mark.usefixtures("com_token")
def test_a_tela_de_prompts_nao_oferece_edicao(client: TestClient) -> None:
    """`editavel` é `False` no contrato, em todo ambiente (ADR-015).

    Não é um booleano calculado a partir de `APP_ENV`: prompt editável em runtime
    contornaria o portão de evals do ADR-014 em QUALQUER ambiente, inclusive local,
    porque é do local que sai o PR.
    """
    corpo = client.get("/admin/prompts", headers=AUTORIZADO).json()
    assert corpo["editavel"] is False
    assert {p["subagent"] for p in corpo["prompts"]} == {"recomendacao", "checkout"}


@pytest.mark.risco("R5")
def test_o_painel_nao_expoe_nenhuma_rota_de_escrita() -> None:
    """Toda rota `/admin/*` é GET. Um PATCH aqui seria o CRUD que o PRD recusou.

    Afirmado sobre os métodos que o app registrou, não sobre o código-fonte: é a
    diferença entre verificar a intenção e verificar o que ficou de pé.
    """
    app = _app(TelemetriaEmMemoria(), BarramentoEmMemoria())
    escritas = [
        (caminho, sorted(metodos))
        for caminho, metodos in (
            (getattr(rota, "path", ""), set(getattr(rota, "methods", None) or ()))
            for rota in app.routes
        )
        if caminho.startswith("/admin") and metodos - {"GET", "HEAD", "OPTIONS"}
    ]
    assert escritas == []

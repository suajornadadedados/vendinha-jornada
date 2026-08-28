"""O painel só pode exibir o que é verdade — e dizer quando não sabe.

A S-07 não fecha risco nenhum da matriz (`riscos_cobertos: []`), e isso é
deliberado: toda invariante já está fechada abaixo da UI. O que estes testes
protegem é a outra coisa que o painel pode fazer de errado, e que nenhum risco
cobre — **mentir**. Um total incompleto exibido como total, um custo zero onde não
há medida, uma taxa de conversão de 0% num dia sem conversa.

Os valores esperados estão escritos à mão. Nenhum é recalculado chamando a função
sob teste: teste que refaz a mesma conta passa por construção e nunca discorda dela
(`docs/testes.md` §4).

    anthropic:claude-haiku-4-5   US$ 1,00 / 1M entrada   US$ 5,00 / 1M saída
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from vendinha.eventos import CAPACIDADE, BarramentoEmMemoria, agora
from vendinha.fiscal import FiscalEmMemoria
from vendinha.metricas import apurar_metricas, percentil, razao
from vendinha.pedidos import PedidosEmMemoria
from vendinha.precos import Preco, TabelaDePrecos
from vendinha.schemas import (
    AprovacaoPendente,
    AtrasoNoStream,
    EventoDoPainel,
    MensagemRegistrada,
)
from vendinha.telemetria import TelemetriaEmMemoria, Turno, UsoDeModelo, VereditoRegistrado

pytestmark = pytest.mark.requires_backend

HAIKU = "anthropic:claude-haiku-4-5"
DATADO = "anthropic:claude-haiku-4-5-20251001"

TABELA = TabelaDePrecos(
    atualizado_em=datetime(2026, 8, 28, tzinfo=UTC).date(),
    moeda="USD",
    fonte="teste",
    modelos={HAIKU: Preco(entrada=Decimal("1.00"), saida=Decimal("5.00"))},
)
COM_CAMBIO = TABELA.model_copy(update={"usd_brl": Decimal("5.00")})


def uso(
    entrada: int, saida: int, *, turnos: int = 1, sem_uso: int = 0, modelo: str = HAIKU
) -> tuple[UsoDeModelo, ...]:
    return (
        UsoDeModelo(
            modelo=modelo,
            tokens_entrada=entrada,
            tokens_saida=saida,
            turnos=turnos,
            turnos_sem_uso=sem_uso,
        ),
    )


def fala(evento: EventoDoPainel) -> MensagemRegistrada:
    """Estreita o evento para a mensagem — e falha se vier de outro tipo.

    Existe porque a união é discriminada e o mypy recusa `.texto` num evento que
    pode não ter. Estreitar aqui não é cerimônia de tipo: transforma "chegou algo
    com o texto errado" e "chegou o evento errado" em duas falhas distintas.
    """
    assert isinstance(evento, MensagemRegistrada), f"esperava mensagem, veio {evento.tipo}"
    return evento


def mensagem(session_id: str, texto: str = "oi") -> MensagemRegistrada:
    return MensagemRegistrada(em=agora(), session_id=session_id, papel="cliente", texto=texto)


# ------------------------------------------------------------------ o custo


def test_o_custo_e_a_conta_do_backend() -> None:
    """64.000 de entrada e 1.200 de saída custam US$ 0,07 — e a conta é aqui.

    64000 x 1,00 / 1M = 0,064
     1200 x 5,00 / 1M = 0,006
    """
    assert TABELA.custo(uso(64_000, 1_200)).usd == Decimal("0.070000")


def test_um_snapshot_datado_herda_o_preco_da_familia() -> None:
    """`LLM_MODEL` aponta para um snapshot datado por decisão do ADR-014.

    Sem o casamento por prefixo, pinar o modelo — que é o que torna a régua de
    evals reprodutível — apagaria o custo de toda conversa de produção.
    """
    assert TABELA.custo(uso(1_000_000, 0, modelo=DATADO)).usd == Decimal("1.000000")


def test_consumo_desconhecido_nao_custa_zero() -> None:
    """O provedor não informou o consumo: o custo é `None`, e não US$ 0,00.

    Zero é uma afirmação — *"esta conversa foi de graça"* — e falsa. O caso é real:
    nem todo provedor devolve `usage_metadata` em streaming, e este teste existe
    porque um smoke test da S-07 pegou exatamente isto chegando à tela como
    `US$ 0,000000`, por um `0 x preço` num modelo que TEM preço.
    """
    custo = TABELA.custo(uso(0, 0, sem_uso=1))
    assert custo.usd is None
    assert custo.completo is False
    assert custo.turnos_sem_uso == 1


def test_modelo_sem_preco_nao_custa_zero() -> None:
    custo = TABELA.custo(uso(1_000, 100, modelo="openai:gpt-4.1"))
    assert custo.usd is None
    assert custo.modelos_sem_preco == ("openai:gpt-4.1",)


def test_um_parcial_conhecido_continua_sendo_parcial() -> None:
    """Dois modelos, um com preço: soma o que sabe e declara o que não sabe.

    Zerar o total por causa da metade desconhecida seria a mentira oposta, e igual
    de ruim: o operador precisa do parcial **sabendo** que é parcial.
    """
    custo = TABELA.custo(uso(64_000, 1_200) + uso(500, 50, modelo="openai:gpt-4.1"))
    assert custo.usd == Decimal("0.070000")
    assert custo.completo is False
    assert custo.modelos_sem_preco == ("openai:gpt-4.1",)


def test_sem_cotacao_o_valor_em_reais_nao_existe() -> None:
    """Sem `usd_brl`, `brl` é `None` — nunca convertido por uma taxa inventada."""
    assert TABELA.custo(uso(64_000, 1_200)).brl is None
    assert COM_CAMBIO.custo(uso(64_000, 1_200)).brl == Decimal("0.35")


# -------------------------------------------------------------- o barramento


async def test_o_barramento_entrega_a_todos_os_assinantes() -> None:
    barramento = BarramentoEmMemoria()
    async with barramento.assinar() as um, barramento.assinar() as outro:
        await barramento.publicar(mensagem("s1"))
        assert fala(await anext(um)).texto == "oi"
        assert fala(await anext(outro)).texto == "oi"


async def test_um_assinante_de_sessao_nao_ve_a_conversa_alheia() -> None:
    """A regra é de inclusão explícita, e o teste a exercita pelos dois lados."""
    barramento = BarramentoEmMemoria()
    async with barramento.assinar(sessao="s1") as fluxo:
        await barramento.publicar(mensagem("s2", "conversa de outro cliente"))
        await barramento.publicar(mensagem("s1", "a minha"))
        assert fala(await anext(fluxo)).texto == "a minha"


async def test_um_evento_sem_sessao_nao_vaza_para_o_cliente() -> None:
    """`aprovacao_pendente` não carrega sessão — logo não vai para assinante nenhum.

    É o caso que uma lista de eventos proibidos erraria no dia em que nascesse o
    sétimo evento. Aqui ele fica de fora por construção.
    """
    barramento = BarramentoEmMemoria()
    async with barramento.assinar(sessao="s1") as fluxo:
        await barramento.publicar(
            AprovacaoPendente(em=agora(), pedido_id="p1", total=Decimal("100"), razao_social="ACME")
        )
        await barramento.publicar(mensagem("s1", "a minha"))
        assert fala(await anext(fluxo)).texto == "a minha"


async def test_a_fila_cheia_descarta_o_antigo_e_avisa() -> None:
    """Publicar nunca espera: um painel lento não pode segurar a resposta de um cliente.

    O preço é perder evento, e o assinante é avisado ANTES do próximo — para a tela
    poder dizer que está furada em vez de aplicar a atualização por cima de um
    estado incompleto.
    """
    barramento = BarramentoEmMemoria()
    async with barramento.assinar() as fluxo:
        for indice in range(CAPACIDADE + 5):
            await asyncio.wait_for(barramento.publicar(mensagem("s1", f"#{indice}")), timeout=1)

        aviso = await anext(fluxo)
        assert isinstance(aviso, AtrasoNoStream)
        assert aviso.perdidos == 5
        # O mais antigo é o descartado: o primeiro que sobra é o #5.
        assert fala(await anext(fluxo)).texto == "#5"


async def test_sair_do_contexto_descadastra_o_assinante() -> None:
    """Aba fechada é assinante fora da lista — senão o barramento vaza memória."""
    barramento = BarramentoEmMemoria()
    async with barramento.assinar():
        assert barramento.assinantes == 1
    assert barramento.assinantes == 0


# ------------------------------------------------------------------ os KPIs


def test_uma_divisao_sem_denominador_e_ausencia_e_nao_zero() -> None:
    assert razao(0, 0) is None
    assert razao(3, 7) == Decimal("0.4286")


def test_o_percentil_devolve_uma_espera_que_aconteceu() -> None:
    """Vizinho mais próximo, não interpolação: o p95 do RNF-4 é sobre espera real."""
    assert percentil((), 0.95) is None
    assert percentil((100, 200, 300, 400), 0.50) == 200
    assert percentil((100, 200, 300, 400), 0.95) == 400


async def test_os_kpis_de_uma_janela_vazia_sao_ausencia_e_nao_zero() -> None:
    """Um dia sem conversa não teve 0% de conversão: não teve conversão nenhuma."""
    metricas = await apurar_metricas(
        janela="24h",
        telemetria=TelemetriaEmMemoria(),
        pedidos=PedidosEmMemoria(),
        fiscal=FiscalEmMemoria(),
        precos=TABELA,
    )
    assert metricas.conversas == 0
    assert metricas.taxa_de_conversao is None
    assert metricas.ticket_medio is None
    assert metricas.taxa_de_aprovacao is None
    assert metricas.primeiro_token_p95_ms is None
    assert metricas.custo.usd is None


async def test_uma_recusa_com_dois_motivos_conta_nos_dois() -> None:
    """Escolher um motivo para o gráfico esconderia metade do trabalho do código.

    Uma composição que estourou o orçamento **e** ficou sem bebida quente foi
    recusada pelas duas coisas — e é essa distinção que `golden-014` exige que
    continue legível fora do texto.
    """
    telemetria = TelemetriaEmMemoria()
    await telemetria.abrir_sessao("s1", canal="widget")
    await telemetria.registrar_veredito(
        VereditoRegistrado(
            session_id="s1",
            aprovada=False,
            tipo_de_evento="cafe_da_manha",
            pessoas=40,
            total=Decimal("1920.00"),
            valor_por_pessoa=Decimal("48.00"),
            motivos=("orcamento", "slot"),
            avaliado_em=agora(),
        )
    )
    metricas = await apurar_metricas(
        janela="24h",
        telemetria=telemetria,
        pedidos=PedidosEmMemoria(),
        fiscal=FiscalEmMemoria(),
        precos=TABELA,
    )
    assert {r.motivo: r.recusas for r in metricas.recusas_do_validador} == {
        "orcamento": 1,
        "slot": 1,
    }


async def test_uma_composicao_aprovada_nao_entra_no_grafico_de_recusas() -> None:
    telemetria = TelemetriaEmMemoria()
    await telemetria.abrir_sessao("s1", canal="widget")
    await telemetria.registrar_veredito(
        VereditoRegistrado(
            session_id="s1",
            aprovada=True,
            tipo_de_evento="cafe_da_manha",
            pessoas=40,
            total=Decimal("1200.00"),
            valor_por_pessoa=Decimal("30.00"),
            avaliado_em=agora(),
        )
    )
    assert await telemetria.recusas_desde(agora() - timedelta(hours=1)) == ()


async def test_um_turno_sem_consumo_deixa_a_conversa_incompleta() -> None:
    """O `None` da medida sobe intacto até o custo da conversa no painel."""
    telemetria = TelemetriaEmMemoria()
    await telemetria.abrir_sessao("s1", canal="widget")
    await telemetria.registrar_turno(
        Turno(
            session_id="s1",
            modelo=HAIKU,
            tokens_entrada=None,
            tokens_saida=None,
            primeiro_token_ms=900,
            duracao_ms=2000,
            iniciado_em=agora(),
        )
    )
    sessao = await telemetria.sessao("s1")
    assert sessao is not None
    assert sessao.uso[0].turnos_sem_uso == 1
    assert TABELA.custo(sessao.uso).usd is None

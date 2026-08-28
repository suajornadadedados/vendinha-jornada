"""Os KPIs do painel, somados aqui — nunca no navegador.

Este módulo é a resposta a uma pergunta que o ADR-015 deixou em aberto: se a UI só
exibe, quem soma? Soma aqui, em `Decimal`, a partir das portas. O frontend recebe
`taxa_de_conversao: "0.4286"` e escreve `42,9%`; ele não divide.

**As ausências são tipadas, e é o ponto do módulo.** Divisão por zero não vira
`0` — vira `None`, e a tela escreve um traço. Uma taxa de conversão de 0% num dia
sem conversa nenhuma é uma afirmação falsa sobre um dia que não aconteceu, e é
exatamente a classe de mentira que este projeto persegue no `precos.py` e no
`telemetria.py`.

**O percentil é calculado num lugar só.** `latencias_desde` devolve a amostra
ordenada em vez do número pronto: `percentile_cont` do Postgres daria o p95 direto,
mas a implementação em memória precisaria da mesma fórmula, e duas fórmulas para a
mesma métrica é como as duas divergem sem ninguém ver.

**A janela é o limite da consulta.** `criados_desde` e `sessoes_desde` não paginam
de propósito: paginar uma agregação daria um KPI sobre a primeira página, que é o
número errado com cara de certo. O que os limita é a janela — e é por isso que ela
é obrigatória.
"""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from vendinha.fiscal import Decisao, Fiscal, StatusDaNota, status_da_nota
from vendinha.pedidos import Pedidos
from vendinha.precos import TabelaDePrecos
from vendinha.schemas import CustoApurado, Metricas, RecusaDoValidador, UsoPorModelo
from vendinha.telemetria import Telemetria, UsoDeModelo

Janela = Literal["24h", "7d", "30d"]

JANELAS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

QUATRO_CASAS = Decimal("0.0001")
DUAS_CASAS = Decimal("0.01")


def desde_de(janela: str) -> datetime:
    """Início da janela. Desconhecida cai em 24h, que é o menor escopo."""
    return datetime.now(UTC) - JANELAS.get(janela, JANELAS["24h"])


def razao(numerador: int | Decimal, denominador: int | Decimal) -> Decimal | None:
    """Uma divisão que devolve `None` em vez de zero quando não há o que dividir."""
    if not denominador:
        return None
    return (Decimal(numerador) / Decimal(denominador)).quantize(
        QUATRO_CASAS, rounding=ROUND_HALF_UP
    )


def percentil(amostra: tuple[int, ...], p: float) -> int | None:
    """Percentil por posição sobre uma amostra **já ordenada**.

    Método do vizinho mais próximo, e não interpolação: o valor devolvido é uma
    latência que de fato aconteceu. Um p95 interpolado é um milissegundo que
    ninguém esperou, e a régua do RNF-4 é sobre espera real.
    """
    if not amostra:
        return None
    indice = min(len(amostra) - 1, max(0, round(p * (len(amostra) - 1))))
    return amostra[indice]


def apurar(uso: tuple[UsoDeModelo, ...], precos: TabelaDePrecos) -> CustoApurado:
    """O `Custo` do `precos.py` no formato que o contrato HTTP expõe."""
    custo = precos.custo(uso)
    return CustoApurado(
        usd=custo.usd,
        brl=custo.brl,
        completo=custo.completo,
        modelos_sem_preco=custo.modelos_sem_preco,
        turnos_sem_uso=custo.turnos_sem_uso,
    )


def _por_modelo(uso: tuple[UsoDeModelo, ...]) -> tuple[UsoPorModelo, ...]:
    return tuple(
        UsoPorModelo(
            modelo=linha.modelo,
            tokens_entrada=linha.tokens_entrada,
            tokens_saida=linha.tokens_saida,
            turnos=linha.turnos,
        )
        for linha in uso
    )


async def apurar_metricas(
    *,
    janela: str,
    telemetria: Telemetria,
    pedidos: Pedidos,
    fiscal: Fiscal,
    precos: TabelaDePrecos,
) -> Metricas:
    """Uma janela, cinco leituras, nenhuma escrita."""
    desde = desde_de(janela)

    sessoes = await telemetria.sessoes_desde(desde)
    uso = await telemetria.uso_desde(desde)
    latencias = await telemetria.latencias_desde(desde)
    recusas = await telemetria.recusas_desde(desde)
    criados = await pedidos.criados_desde(desde)
    decisoes = await fiscal.decisoes_desde(desde)
    pendentes = await pedidos.aguardando_aprovacao_de_nf()

    turnos = sum(sessao.turnos for sessao in sessoes)
    com_pedido = sum(1 for sessao in sessoes if sessao.pedido_id is not None)
    # Atendimento é da primeira à última mensagem. Sessões de um turno só entram
    # com duração perto de zero, e devem entrar: uma conversa que morreu na
    # primeira resposta é um atendimento curto, não um atendimento ausente.
    duracoes = [
        int((sessao.ultima_atividade - sessao.iniciada_em).total_seconds() * 1000)
        for sessao in sessoes
    ]

    receita = sum((pedido.total for pedido in criados), Decimal(0))
    custo = apurar(uso, precos)
    # Só compara moeda com moeda. Sem cotação, `brl` é None e o percentual não
    # existe — em vez de dividir dólar por real e chamar o resultado de margem.
    sobre_ticket = None if custo.brl is None else razao(custo.brl, receita)

    aprovadas = sum(1 for decisao in decisoes if decisao.decisao is Decisao.APROVADA)

    return Metricas(
        janela=janela,
        desde=desde,
        conversas=len(sessoes),
        conversas_com_pedido=com_pedido,
        taxa_de_conversao=razao(com_pedido, len(sessoes)),
        turnos=turnos,
        turnos_por_conversa=razao(turnos, len(sessoes)),
        atendimento_medio_ms=(sum(duracoes) // len(duracoes)) if duracoes else None,
        erros_de_stream=sum(sessao.erros for sessao in sessoes),
        uso=_por_modelo(uso),
        custo=custo,
        primeiro_token_p50_ms=percentil(latencias, 0.50),
        primeiro_token_p95_ms=percentil(latencias, 0.95),
        pedidos=len(criados),
        receita=receita,
        ticket_medio=(
            (receita / len(criados)).quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)
            if criados
            else None
        ),
        custo_sobre_ticket=sobre_ticket,
        fila_pendentes=len(pendentes),
        decisoes=len(decisoes),
        aprovadas=aprovadas,
        taxa_de_aprovacao=razao(aprovadas, len(decisoes)),
        recusas_do_validador=tuple(
            RecusaDoValidador(motivo=recusa.motivo, recusas=recusa.recusas) for recusa in recusas
        ),
    )


def status_fiscal(status: str) -> str:
    """O status da nota derivado do status do pedido — nunca uma segunda coluna."""
    from vendinha.pedidos import StatusDoPedido

    try:
        return status_da_nota(StatusDoPedido(status)).value
    except ValueError:
        return StatusDaNota.NAO_APLICAVEL.value

"""O read model do painel: quem conversou, quando, com que modelo e a que custo.

Esta é a primeira tabela deste repositório que existe **só para ser lida por uma
tela**. Vale dizer o que ela deliberadamente não faz, porque é onde um read model
apodrece.

**As mensagens não estão aqui.** Elas já vivem no checkpointer, indexadas pelo
`thread_id`, que é o mesmo `session_id` que o cliente segura e o mesmo que o
Langfuse recebe — uma string só, e é assim desde a S-02. Copiá-las para cá criaria
a segunda cópia que fica velha: o painel mostraria uma conversa e o agente
continuaria a partir de outra. A RNF-6 (pointer-not-payload) governa o estado do
grafo e governa isto pela mesma razão. O detalhe da conversa sai de
`graph.aget_state(session_config(session_id))`.

**Então por que existe uma tabela `sessao`?** Porque o checkpointer é schema da
LangGraph, não nosso: listar conversas por `SELECT DISTINCT thread_id` nas tabelas
dela acopla o painel a uma migração de terceiro, e mistura as threads de conversa
com as de emissão de nota, que usam o mesmo checkpointer com o prefixo `nf:`
(`fiscal.thread_da_nota`). E porque há dois fatos que o checkpointer não tem: por
qual canal a pessoa chegou, e qual pedido a conversa gerou.

**Token desconhecido é `None`, nunca zero.** Nem todo provedor devolve
`usage_metadata` em streaming, e um zero nessa coluna vira R$ 0,00 na tela de
custo — que é uma afirmação, e uma afirmação falsa. O ADR-015 fixou a regra para o
preço; ela começa aqui, na medida. Quem agrega conta separadamente quantos turnos
não souberam dizer.

**Dinheiro não mora neste módulo.** Aqui há token e milissegundo. O preço é de
`precos.py`, e a conta é feita sobre o `UsoDeModelo` que estas consultas devolvem —
uma tabela de leitura que já trouxesse reais seria uma segunda fonte de verdade
sobre o câmbio do dia em que a linha foi gravada.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

import psycopg
from pydantic import BaseModel, Field


class UsoDeModelo(BaseModel):
    """Quanto um modelo consumiu numa fatia de tempo ou de conversa.

    Separado por modelo e não somado: uma sessão pode ter trocado de modelo no meio
    (a rota `/chat` aceita `model` por requisição), e somar tokens de dois preços
    diferentes num número só é como se perde a conta do custo.
    """

    modelo: str
    tokens_entrada: int
    tokens_saida: int
    turnos: int
    turnos_sem_uso: int = Field(
        default=0,
        description=(
            "Turnos em que o provedor não informou consumo. Quem exibe custo precisa "
            "dizer que o número está incompleto, em vez de apresentá-lo como total."
        ),
    )


class Turno(BaseModel):
    """Uma ida ao modelo, do ponto de vista de quem paga a conta e mede a espera."""

    session_id: str
    modelo: str
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    primeiro_token_ms: int | None = Field(
        default=None,
        description=(
            "Espera até o primeiro token visível ao cliente. É o número do RNF-4 "
            "(p95 ≤ 3s). `None` quando o turno falhou antes de qualquer token."
        ),
    )
    duracao_ms: int
    iniciado_em: datetime
    erro: bool = False


class ResumoDaSessao(BaseModel):
    """Uma conversa como a lista do painel precisa vê-la, sem abrir o detalhe."""

    session_id: str
    canal: str
    iniciada_em: datetime
    ultima_atividade: datetime
    turnos: int
    erros: int
    uso: tuple[UsoDeModelo, ...] = ()
    pedido_id: str | None = None


class VereditoRegistrado(BaseModel):
    """Uma passagem da composição pelo validador, guardada para a tela ver depois.

    Isto **não** é uma segunda fonte de verdade sobre nada: nenhum estado do produto
    é derivado desta tabela. É um registro de decisões já tomadas — o mesmo tipo de
    fato que `evento_de_pagamento` guarda. Sem ele, o gráfico de recusas por motivo
    só existiria enquanto a aba estivesse aberta, porque o veredito hoje só passa
    pelo barramento.

    `motivos` guarda o campo tipado (`orcamento`, `slot`, `restricao`, ...) e não a
    frase: `golden-014` exige que uma recusa por slot seja distinguível de uma por
    preço sem que ninguém interprete texto, e um gráfico agrupado por frase seria
    exatamente essa interpretação.
    """

    session_id: str
    aprovada: bool
    tipo_de_evento: str
    pessoas: int
    total: Decimal
    valor_por_pessoa: Decimal
    motivos: tuple[str, ...] = ()
    avaliado_em: datetime


class RecusaPorMotivo(BaseModel):
    """Quantas recusas cada motivo produziu numa janela."""

    motivo: str
    recusas: int


class Telemetria(Protocol):
    """A porta. Duas implementações, como todas as outras deste repositório."""

    async def abrir_sessao(self, session_id: str, *, canal: str) -> None: ...

    async def registrar_turno(self, turno: Turno) -> None: ...

    async def registrar_veredito(self, veredito: VereditoRegistrado) -> None: ...

    async def vereditos(self, session_id: str) -> tuple[VereditoRegistrado, ...]: ...

    async def recusas_desde(self, desde: datetime) -> tuple[RecusaPorMotivo, ...]: ...

    async def vincular_pedido(self, session_id: str, pedido_id: str) -> None: ...

    async def sessoes(self, *, limite: int = 50, offset: int = 0) -> tuple[ResumoDaSessao, ...]: ...

    async def sessao(self, session_id: str) -> ResumoDaSessao | None: ...

    async def turnos(self, session_id: str) -> tuple[Turno, ...]: ...

    async def uso_desde(self, desde: datetime) -> tuple[UsoDeModelo, ...]: ...

    async def latencias_desde(self, desde: datetime) -> tuple[int, ...]: ...


SCHEMA: tuple[str, ...] = (
    """
CREATE TABLE IF NOT EXISTS sessao (
    session_id       text PRIMARY KEY,
    canal            text NOT NULL,
    iniciada_em      timestamptz NOT NULL DEFAULT now(),
    ultima_atividade timestamptz NOT NULL DEFAULT now(),
    pedido_id        text REFERENCES pedido(id) ON DELETE SET NULL
)
""",
    # Sem FK para `sessao`: a linha do turno é gravada no fim de uma resposta que já
    # foi entregue ao cliente, e recusá-la porque a sessão sumiu perderia a medida
    # de um atendimento que aconteceu. O `session_id` é o mesmo do checkpointer de
    # qualquer forma — a integridade que importa está lá.
    """
CREATE TABLE IF NOT EXISTS turno (
    id                bigserial PRIMARY KEY,
    session_id        text NOT NULL,
    modelo            text NOT NULL,
    tokens_entrada    integer,
    tokens_saida      integer,
    primeiro_token_ms integer,
    duracao_ms        integer NOT NULL,
    iniciado_em       timestamptz NOT NULL,
    erro              boolean NOT NULL DEFAULT false
)
""",
    """
CREATE INDEX IF NOT EXISTS turno_por_sessao ON turno (session_id, iniciado_em)
""",
    # A janela temporal do painel (24h, 7d, 30d) varre por data. Sem este índice a
    # tela de métricas faz seq scan de toda a história a cada troca de seletor.
    """
CREATE INDEX IF NOT EXISTS turno_por_data ON turno (iniciado_em)
""",
    # Sem FK, pela mesma razão de `turno`: o veredito é o registro de uma avaliação
    # que aconteceu, e perdê-lo porque a sessão sumiu perderia o dado do gráfico.
    """
CREATE TABLE IF NOT EXISTS veredito_de_composicao (
    id               bigserial PRIMARY KEY,
    session_id       text NOT NULL,
    aprovada         boolean NOT NULL,
    tipo_de_evento   text NOT NULL,
    pessoas          integer NOT NULL,
    total            numeric(12,2) NOT NULL,
    valor_por_pessoa numeric(10,2) NOT NULL,
    motivos          text[] NOT NULL DEFAULT '{}',
    avaliado_em      timestamptz NOT NULL
)
""",
    """
CREATE INDEX IF NOT EXISTS veredito_por_sessao
    ON veredito_de_composicao (session_id, avaliado_em)
""",
    """
CREATE INDEX IF NOT EXISTS veredito_por_data ON veredito_de_composicao (avaliado_em)
""",
)


def _uso(linhas: Sequence[tuple[Any, ...]]) -> tuple[UsoDeModelo, ...]:
    """Monta o uso por modelo a partir de linhas `(modelo, entrada, saida, turnos, sem_uso)`."""
    return tuple(
        UsoDeModelo(
            modelo=str(linha[0]),
            tokens_entrada=int(linha[1] or 0),
            tokens_saida=int(linha[2] or 0),
            turnos=int(linha[3]),
            turnos_sem_uso=int(linha[4]),
        )
        for linha in linhas
    )


# `SUM` ignora NULL, então o total sai certo; o que se perderia é saber que ele está
# incompleto. `COUNT(*) FILTER (WHERE tokens_entrada IS NULL)` é o que devolve isso.
_AGREGADO = (
    "SELECT modelo, SUM(tokens_entrada), SUM(tokens_saida), COUNT(*),"
    " COUNT(*) FILTER (WHERE tokens_entrada IS NULL) FROM turno"
)


class PostgresTelemetria:
    """A porta no Postgres."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def setup(self) -> None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            for statement in SCHEMA:
                await conn.execute(statement.encode())

    async def abrir_sessao(self, session_id: str, *, canal: str) -> None:
        """Idempotente: chamada em todo turno, cria na primeira e toca a data nas outras.

        `ON CONFLICT` em vez de um `SELECT` antes do `INSERT` pela mesma razão de
        `registrar_pagamento`: duas requisições da mesma sessão chegando juntas é
        normal, e a corrida entre elas não pode virar um 500 no meio de uma resposta.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            await conn.execute(
                "INSERT INTO sessao (session_id, canal) VALUES (%s, %s)"
                " ON CONFLICT (session_id) DO UPDATE SET ultima_atividade = now()",
                (session_id, canal),
            )

    async def registrar_turno(self, turno: Turno) -> None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            await conn.execute(
                "INSERT INTO turno (session_id, modelo, tokens_entrada, tokens_saida,"
                " primeiro_token_ms, duracao_ms, iniciado_em, erro)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    turno.session_id,
                    turno.modelo,
                    turno.tokens_entrada,
                    turno.tokens_saida,
                    turno.primeiro_token_ms,
                    turno.duracao_ms,
                    turno.iniciado_em,
                    turno.erro,
                ),
            )

    async def vincular_pedido(self, session_id: str, pedido_id: str) -> None:
        """Liga a conversa ao pedido que ela gerou. Silencioso se a sessão não existe.

        Não levanta: quem chama é o caminho do pedido, e um pedido criado por um
        runner de eval — que não abre sessão — não pode falhar por causa da tela.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            await conn.execute(
                "UPDATE sessao SET pedido_id = %s, ultima_atividade = now() WHERE session_id = %s",
                (pedido_id, session_id),
            )

    async def sessoes(self, *, limite: int = 50, offset: int = 0) -> tuple[ResumoDaSessao, ...]:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            cabecalhos = await (
                await conn.execute(
                    "SELECT session_id, canal, iniciada_em, ultima_atividade, pedido_id"
                    " FROM sessao ORDER BY ultima_atividade DESC LIMIT %s OFFSET %s",
                    (limite, offset),
                )
            ).fetchall()
            if not cabecalhos:
                return ()
            ids = [linha[0] for linha in cabecalhos]
            # Uma consulta para todas as sessões da página, e não uma por linha: a
            # lista do painel recarrega a cada evento, e N+1 aqui é N+1 por evento.
            agregados = await (
                await conn.execute(
                    f"{_AGREGADO} WHERE session_id = ANY(%s) GROUP BY session_id, modelo",
                    (ids,),
                )
            ).fetchall()
            erros = await (
                await conn.execute(
                    "SELECT session_id, COUNT(*) FILTER (WHERE erro), COUNT(*) FROM turno"
                    " WHERE session_id = ANY(%s) GROUP BY session_id",
                    (ids,),
                )
            ).fetchall()

        return tuple(_monta_resumo(linha, agregados, erros) for linha in cabecalhos)

    async def sessao(self, session_id: str) -> ResumoDaSessao | None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            cabecalho = await (
                await conn.execute(
                    "SELECT session_id, canal, iniciada_em, ultima_atividade, pedido_id"
                    " FROM sessao WHERE session_id = %s",
                    (session_id,),
                )
            ).fetchone()
            if cabecalho is None:
                return None
            agregados = await (
                await conn.execute(
                    f"{_AGREGADO} WHERE session_id = %s GROUP BY session_id, modelo",
                    (session_id,),
                )
            ).fetchall()
            erros = await (
                await conn.execute(
                    "SELECT session_id, COUNT(*) FILTER (WHERE erro), COUNT(*) FROM turno"
                    " WHERE session_id = %s GROUP BY session_id",
                    (session_id,),
                )
            ).fetchall()
        return _monta_resumo(cabecalho, agregados, erros)

    async def turnos(self, session_id: str) -> tuple[Turno, ...]:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linhas = await (
                await conn.execute(
                    "SELECT session_id, modelo, tokens_entrada, tokens_saida,"
                    " primeiro_token_ms, duracao_ms, iniciado_em, erro FROM turno"
                    " WHERE session_id = %s ORDER BY iniciado_em",
                    (session_id,),
                )
            ).fetchall()
        return tuple(
            Turno(
                session_id=str(linha[0]),
                modelo=str(linha[1]),
                tokens_entrada=None if linha[2] is None else int(linha[2]),
                tokens_saida=None if linha[3] is None else int(linha[3]),
                primeiro_token_ms=None if linha[4] is None else int(linha[4]),
                duracao_ms=int(linha[5]),
                iniciado_em=linha[6],
                erro=bool(linha[7]),
            )
            for linha in linhas
        )

    async def uso_desde(self, desde: datetime) -> tuple[UsoDeModelo, ...]:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linhas = await (
                await conn.execute(
                    f"{_AGREGADO} WHERE iniciado_em >= %s GROUP BY modelo",
                    (desde,),
                )
            ).fetchall()
        return _uso(linhas)

    async def registrar_veredito(self, veredito: VereditoRegistrado) -> None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            await conn.execute(
                "INSERT INTO veredito_de_composicao (session_id, aprovada, tipo_de_evento,"
                " pessoas, total, valor_por_pessoa, motivos, avaliado_em)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    veredito.session_id,
                    veredito.aprovada,
                    veredito.tipo_de_evento,
                    veredito.pessoas,
                    veredito.total,
                    veredito.valor_por_pessoa,
                    list(veredito.motivos),
                    veredito.avaliado_em,
                ),
            )

    async def vereditos(self, session_id: str) -> tuple[VereditoRegistrado, ...]:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linhas = await (
                await conn.execute(
                    "SELECT session_id, aprovada, tipo_de_evento, pessoas, total,"
                    " valor_por_pessoa, motivos, avaliado_em FROM veredito_de_composicao"
                    " WHERE session_id = %s ORDER BY avaliado_em",
                    (session_id,),
                )
            ).fetchall()
        return tuple(_veredito(linha) for linha in linhas)

    async def recusas_desde(self, desde: datetime) -> tuple[RecusaPorMotivo, ...]:
        """Agrupa por motivo, e um veredito com dois motivos conta nos dois.

        `unnest` e não "o primeiro motivo": uma composição que estourou o orçamento
        **e** ficou sem bebida quente foi recusada pelas duas coisas, e escolher uma
        para o gráfico esconderia metade do trabalho que o código fez.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linhas = await (
                await conn.execute(
                    "SELECT motivo, COUNT(*) FROM veredito_de_composicao,"
                    " unnest(motivos) AS motivo"
                    " WHERE avaliado_em >= %s AND NOT aprovada GROUP BY motivo"
                    " ORDER BY COUNT(*) DESC, motivo",
                    (desde,),
                )
            ).fetchall()
        return tuple(
            RecusaPorMotivo(motivo=str(linha[0]), recusas=int(linha[1])) for linha in linhas
        )

    async def latencias_desde(self, desde: datetime) -> tuple[int, ...]:
        """Os tempos até o primeiro token, ordenados — o percentil é de quem agrega.

        Devolver a amostra e não o p95 é deliberado: `percentile_cont` no Postgres
        daria o número direto, mas o mesmo cálculo teria de existir de novo para a
        implementação em memória, e duas fórmulas para a mesma métrica é como as
        duas divergem. Aqui sai o dado; o percentil mora num lugar só.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linhas = await (
                await conn.execute(
                    "SELECT primeiro_token_ms FROM turno WHERE iniciado_em >= %s"
                    " AND primeiro_token_ms IS NOT NULL ORDER BY primeiro_token_ms",
                    (desde,),
                )
            ).fetchall()
        return tuple(int(linha[0]) for linha in linhas)


def _veredito(linha: tuple[Any, ...]) -> VereditoRegistrado:
    return VereditoRegistrado(
        session_id=str(linha[0]),
        aprovada=bool(linha[1]),
        tipo_de_evento=str(linha[2]),
        pessoas=int(linha[3]),
        total=linha[4],
        valor_por_pessoa=linha[5],
        motivos=tuple(linha[6] or ()),
        avaliado_em=linha[7],
    )


def _monta_resumo(
    cabecalho: tuple[Any, ...],
    agregados: Sequence[tuple[Any, ...]],
    erros: Sequence[tuple[Any, ...]],
) -> ResumoDaSessao:
    """Junta em memória o que três consultas trouxeram, para não haver N+1 na lista.

    `agregados` e `erros` vêm agrupados por `session_id`, então cada resumo filtra a
    sua fatia. É O(n·m) sobre uma página de 50 — barato — e evita a consulta por
    linha, que numa tela que recarrega a cada evento seria N+1 por evento.
    """
    session_id = str(cabecalho[0])
    meus = [linha[1:] for linha in agregados if str(linha[0]) == session_id]
    contagem = next((linha for linha in erros if str(linha[0]) == session_id), None)
    return ResumoDaSessao(
        session_id=session_id,
        canal=str(cabecalho[1]),
        iniciada_em=cabecalho[2],
        ultima_atividade=cabecalho[3],
        turnos=int(contagem[2]) if contagem else 0,
        erros=int(contagem[1]) if contagem else 0,
        uso=_uso(meus),
        pedido_id=None if cabecalho[4] is None else str(cabecalho[4]),
    )


class TelemetriaEmMemoria:
    """A mesma porta, sem contêiner — a implementação das duas suítes de teste.

    `abertas` e `registrados` são públicos porque a asserção que interessa costuma
    ser sobre ausência: *nenhum turno foi gravado para esta sessão*.
    """

    def __init__(self) -> None:
        self.abertas: dict[str, ResumoDaSessao] = {}
        self.registrados: list[Turno] = []
        self.avaliados: list[VereditoRegistrado] = []

    async def abrir_sessao(self, session_id: str, *, canal: str) -> None:
        agora = datetime.now(UTC)
        existente = self.abertas.get(session_id)
        if existente is None:
            self.abertas[session_id] = ResumoDaSessao(
                session_id=session_id,
                canal=canal,
                iniciada_em=agora,
                ultima_atividade=agora,
                turnos=0,
                erros=0,
            )
            return
        self.abertas[session_id] = existente.model_copy(update={"ultima_atividade": agora})

    async def registrar_turno(self, turno: Turno) -> None:
        self.registrados.append(turno)

    async def registrar_veredito(self, veredito: VereditoRegistrado) -> None:
        self.avaliados.append(veredito)

    async def vereditos(self, session_id: str) -> tuple[VereditoRegistrado, ...]:
        return tuple(
            sorted(
                (v for v in self.avaliados if v.session_id == session_id),
                key=lambda v: v.avaliado_em,
            )
        )

    async def recusas_desde(self, desde: datetime) -> tuple[RecusaPorMotivo, ...]:
        contagem: dict[str, int] = {}
        for veredito in self.avaliados:
            if veredito.aprovada or veredito.avaliado_em < desde:
                continue
            for motivo in veredito.motivos:
                contagem[motivo] = contagem.get(motivo, 0) + 1
        return tuple(
            RecusaPorMotivo(motivo=motivo, recusas=quantas)
            for motivo, quantas in sorted(contagem.items(), key=lambda par: (-par[1], par[0]))
        )

    async def vincular_pedido(self, session_id: str, pedido_id: str) -> None:
        existente = self.abertas.get(session_id)
        if existente is None:
            return
        self.abertas[session_id] = existente.model_copy(update={"pedido_id": pedido_id})

    async def sessoes(self, *, limite: int = 50, offset: int = 0) -> tuple[ResumoDaSessao, ...]:
        ordenadas = sorted(
            self.abertas.values(), key=lambda sessao: sessao.ultima_atividade, reverse=True
        )
        return tuple(self._com_uso(sessao) for sessao in ordenadas[offset : offset + limite])

    async def sessao(self, session_id: str) -> ResumoDaSessao | None:
        encontrada = self.abertas.get(session_id)
        return None if encontrada is None else self._com_uso(encontrada)

    async def turnos(self, session_id: str) -> tuple[Turno, ...]:
        return tuple(
            sorted(
                (turno for turno in self.registrados if turno.session_id == session_id),
                key=lambda turno: turno.iniciado_em,
            )
        )

    async def uso_desde(self, desde: datetime) -> tuple[UsoDeModelo, ...]:
        return _somar([turno for turno in self.registrados if turno.iniciado_em >= desde])

    async def latencias_desde(self, desde: datetime) -> tuple[int, ...]:
        return tuple(
            sorted(
                turno.primeiro_token_ms
                for turno in self.registrados
                if turno.iniciado_em >= desde and turno.primeiro_token_ms is not None
            )
        )

    def _com_uso(self, sessao: ResumoDaSessao) -> ResumoDaSessao:
        meus = [turno for turno in self.registrados if turno.session_id == sessao.session_id]
        return sessao.model_copy(
            update={
                "turnos": len(meus),
                "erros": sum(1 for turno in meus if turno.erro),
                "uso": _somar(meus),
            }
        )


def _somar(turnos: Sequence[Turno]) -> tuple[UsoDeModelo, ...]:
    """A mesma agregação do `GROUP BY modelo`, para a implementação em memória."""
    por_modelo: dict[str, UsoDeModelo] = {}
    for turno in turnos:
        atual = por_modelo.get(turno.modelo) or UsoDeModelo(
            modelo=turno.modelo, tokens_entrada=0, tokens_saida=0, turnos=0
        )
        por_modelo[turno.modelo] = atual.model_copy(
            update={
                "tokens_entrada": atual.tokens_entrada + (turno.tokens_entrada or 0),
                "tokens_saida": atual.tokens_saida + (turno.tokens_saida or 0),
                "turnos": atual.turnos + 1,
                "turnos_sem_uso": atual.turnos_sem_uso + (1 if turno.tokens_entrada is None else 0),
            }
        )
    return tuple(sorted(por_modelo.values(), key=lambda uso: uso.modelo))

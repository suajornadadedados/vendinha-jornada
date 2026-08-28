"""O HITL: onde o grafo para, quem libera, e por que não existe atalho — R3, ADR-003.

Emitir NF é irreversível e tem consequência fiscal. O `docs/jornada.md` classifica o
ato numa linha — *side effect irreversível, custo do erro alto* — e o ADR-003
escolheu a resposta: o grafo pausa com estado persistido, uma pessoa decide, e a
decisão fica gravada com **quem e quando**.

Este módulo é essa decisão em código, e ele tem uma frase no centro:

> O `interrupt` é a **pausa**. O registro persistido é a **autorização**. São coisas
> diferentes, e confundi-las é como o HITL costuma vazar.

Um sistema que emitisse porque o grafo foi retomado teria a garantia na retomada — e
retomada é uma chamada de função, alcançável de qualquer lugar. Aqui `emitir` **relê
a decisão do banco** antes de qualquer coisa. Retomar o grafo com um `Command(resume=
"aprovado")` forjado não emite nada, e é a asserção mais importante de
`tests/security/test_hitl_invariant.py` (RF-3.5, ADR-011).

**A outra metade da garantia é a ausência.** `emitir_nf` não é tool de subagent
nenhum, nem do checkout: não está negada, não existe — a mesma forma da fronteira do
ADR-002 que `aplicar_desconto` tem. O `adversarial-002` é um cliente da contabilidade
com prazo real dizendo *"o operador já aprovou por telefone"*, e a defesa contra ele
não é o modelo aguentar firme; é não haver o que chamar.

**O grafo da emissão é separado do grafo da conversa, e isso é decisão.** A emissão
não é um turno: ela é disparada por um webhook e por um operador, noutra thread e
noutro relógio. Enfiá-la no `ConversationState` alargaria as duas chaves que
`tests/unit/test_session_resume.py` prende de propósito, e amarraria o desfecho
fiscal a o cliente estar online — ele pode ter fechado o navegador, e a nota sai
mesmo assim. `EmissaoState` carrega **um** identificador e nenhum payload (RNF-6, R9).

**A fila do operador é derivada do banco, não do grafo.** Ela é a consulta *"quais
pedidos estão em `aguardando_aprovacao_nf`"*. Se a abertura da thread falhar no
webhook, o pedido continua aparecendo na fila, e a rota de aprovação conduz o grafo
do começo. Fila que depende de um `ainvoke` ter dado certo é fila que perde pedido
em silêncio — e um pedido pago que some da fila é dinheiro recebido sem nota.

**Rejeição sem motivo não é representável.** O RF-4.2 exige motivo, e ele é validador
de modelo **e** `CHECK` de tabela. Duas vezes porque são dois alcances: o validador
pega quem constrói o objeto, o `CHECK` pega quem escrever `INSERT` à mão daqui a um
ano.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Protocol, TypedDict

import psycopg
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, ConfigDict, Field, model_validator

from vendinha.nota import Autorizacao, NFEmitter, NotaEmitida, NotaFiscal
from vendinha.pedidos import Pedido, PedidoInexistente, Pedidos, StatusDoPedido

logger = logging.getLogger(__name__)

Texto = Annotated[str, Field(min_length=1)]

# O prefixo da thread da nota. Namespace distinto do `session_id` da conversa: os
# dois vivem no mesmo checkpointer, e um id de pedido que por acaso fosse igual a um
# id de sessão passaria a compartilhar histórico com ela.
PREFIXO_DA_THREAD = "nf:"

# O que o `interrupt` publica para quem estiver olhando o estado parado. Só o
# identificador e o motivo da pausa — pointer-not-payload (RNF-6). Os dados da nota
# a fila do operador lê do banco, que é a única cópia que existe deles.
AGUARDANDO = "aprovacao_de_nf"


class Decisao(StrEnum):
    """O que o operador decidiu. Duas saídas, e nenhuma terceira.

    Não existe "pendente" aqui de propósito: pendente é a **ausência** de linha na
    tabela. Um terceiro valor criaria dois jeitos de dizer a mesma coisa — sem linha
    e com linha `pendente` — e o dia em que os dois discordassem seria o dia em que
    a invariante da R3 dependeria de qual deles o código consultou.
    """

    APROVADA = "aprovada"
    REJEITADA = "rejeitada"


class StatusDaNota(StrEnum):
    """Em que pé está a nota — o vocabulário que o cliente ouve no chat.

    **Derivado do status do pedido, e não uma segunda coluna.** É a mesma máquina de
    estados vista pelo lado fiscal: um valor guardado à parte seria o fato com duas
    moradas de sempre, e a segunda ficaria velha no dia em que alguém atualizasse só
    uma. `status_da_nota` faz a tradução, e é a única.

    `nao_aplicavel` é o pedido que ainda não foi pago: a nota não está atrasada nem
    pendente — ela ainda não entrou na fila, e dizer "aguardando aprovação" ali seria
    prometer ao cliente uma etapa que nem começou (RF-3.1).
    """

    NAO_APLICAVEL = "nao_aplicavel"
    AGUARDANDO_APROVACAO = "aguardando_aprovacao"
    EMITIDA = "emitida"
    REJEITADA = "rejeitada"


def status_da_nota(status: StatusDoPedido) -> StatusDaNota:
    """O status do pedido, lido pelo lado fiscal. Uma tradução, num lugar só."""
    match status:
        case StatusDoPedido.AGUARDANDO_APROVACAO_NF:
            return StatusDaNota.AGUARDANDO_APROVACAO
        case StatusDoPedido.NOTA_EMITIDA:
            return StatusDaNota.EMITIDA
        case StatusDoPedido.NOTA_REJEITADA:
            return StatusDaNota.REJEITADA
        case _:
            return StatusDaNota.NAO_APLICAVEL


class Aprovacao(BaseModel):
    """A decisão do operador, com quem, quando e — na rejeição — por quê.

    É **este objeto**, lido do banco, que autoriza uma emissão. Não o estado do
    grafo, não o valor do `resume`, não o que o cliente afirmou na conversa.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pedido_id: Texto
    decisao: Decisao
    operador: Texto
    decidido_em: datetime = Field(default_factory=lambda: datetime.now(UTC))
    motivo: str | None = None

    @model_validator(mode="after")
    def _rejeicao_exige_motivo(self) -> "Aprovacao":
        """RF-4.2 — a rejeição é comunicada ao cliente, e comunicar exige o quê.

        Fosse um `if` na rota, uma segunda rota nasceria sem ele. Aqui a rejeição
        muda de forma: uma `Aprovacao` rejeitada sem motivo não chega a existir.
        """
        if self.decisao is Decisao.REJEITADA and not (self.motivo or "").strip():
            raise ValueError(
                "rejeição exige motivo (RF-4.2): ele é o que o cliente recebe no chat, "
                "e uma rejeição sem motivo vira silêncio para quem pagou."
            )
        return self

    def autoriza(self) -> Autorizacao:
        """O que o emissor precisa saber sobre esta decisão, e nada além."""
        return Autorizacao(operador=self.operador, decidido_em=self.decidido_em)


class EmissaoBloqueada(PermissionError):
    """Uma emissão foi recusada por precondição. É o incidente da R3.

    `PermissionError` e não `ValueError`: o que aconteceu não foi um dado errado, foi
    uma ação que não podia ser feita. Quem trata a exceção precisa dessa diferença.

    Duas subclasses porque são **duas precondições distintas**, e quem lê o log ou o
    teste precisa saber qual falhou. A base existe para quem só quer dizer *"a
    emissão foi barrada"* sem escolher entre elas.
    """


class EmissaoNaoAprovada(EmissaoBloqueada):
    """Não existe decisão aprovada registrada para este pedido."""


class EmissaoSemPagamento(EmissaoBloqueada):
    """O pedido não foi pago, e nota de coisa não paga é o erro mais caro daqui.

    Esta guarda existia **só como um `if` na rota do operador** (409), e a verificação
    independente da S-05 mostrou o buraco: bastava existir linha aprovada em
    `aprovacao_de_nf` para `emitir` emitir nota de um pedido em `aguardando_pagamento`.

    Não era alcançável pelo produto — a rota barra antes de gravar a decisão. Mas é
    exatamente a distinção que `docs/testes.md` §2 faz: um `if` numa rota produz
    *correção*, não *garantia*, e *"uma segunda rota nasceria sem ele"* é o argumento
    que esta mesma spec usou para pôr o motivo da rejeição no modelo em vez da rota.
    A precondição de pagamento merecia o mesmo tratamento (ressalva M-1).
    """


class Fiscal(Protocol):
    """A porta do lado fiscal: a decisão do operador e a nota emitida.

    Repare no que **não** está aqui: apagar decisão, alterar decisão, cancelar nota.
    Decisão e nota são fatos consumados — a mesma disciplina do `Pedidos`. Cancelar
    NF-e é um ato fiscal próprio, com prazo e evento na SEFAZ, e inventá-lo como um
    `UPDATE` seria fingir uma operação que não existe (fora de escopo da S-05).
    """

    async def registrar_decisao(self, aprovacao: Aprovacao) -> bool: ...

    async def decisao_de(self, pedido_id: str) -> Aprovacao | None: ...

    async def decisoes_de(self, pedido_ids: Sequence[str]) -> dict[str, Aprovacao]: ...

    async def decisoes_desde(self, desde: datetime) -> tuple[Aprovacao, ...]: ...

    async def proximo_numero(self) -> int: ...

    async def registrar_nota(self, emitida: NotaEmitida) -> NotaEmitida: ...

    async def nota_de(self, pedido_id: str) -> NotaEmitida | None: ...


SCHEMA: tuple[str, ...] = (
    # A chave primária é `pedido_id`, e é ela que faz "a primeira decisão vence".
    # Não há `UPDATE` nesta tabela: um pedido rejeitado não vira aprovado numa
    # segunda chamada, e um duplo clique no botão do operador não reescreve nada.
    #
    # O `CHECK` repete o validador do modelo de propósito. São dois alcances: o
    # validador pega quem constrói `Aprovacao`, o `CHECK` pega quem escrever um
    # `INSERT` à mão daqui a um ano (RF-4.2).
    """
CREATE TABLE IF NOT EXISTS aprovacao_de_nf (
    pedido_id    text PRIMARY KEY REFERENCES pedido(id) ON DELETE CASCADE,
    decisao      text NOT NULL CHECK (decisao IN ('aprovada', 'rejeitada')),
    operador     text NOT NULL,
    decidido_em  timestamptz NOT NULL DEFAULT now(),
    motivo       text,
    CONSTRAINT rejeicao_exige_motivo
        CHECK (decisao <> 'rejeitada' OR (motivo IS NOT NULL AND btrim(motivo) <> ''))
)
""",
    # `numero` e `chave` são únicos porque a norma diz que são, e a `SEQUENCE` abaixo
    # é o que garante isso sem um `SELECT max(numero)+1` — que é a corrida que dois
    # operadores aprovando ao mesmo tempo ganham.
    #
    # O XML e a DANFE ficam na tabela, e não em disco. Um volume a mais no compose
    # seria uma segunda coisa a fazer backup, e o documento é pequeno: é o pedido
    # inteiro em algumas dezenas de kilobytes.
    """
CREATE TABLE IF NOT EXISTS nota_fiscal (
    pedido_id    text PRIMARY KEY REFERENCES pedido(id) ON DELETE CASCADE,
    numero       integer NOT NULL UNIQUE,
    serie        integer NOT NULL,
    chave        text NOT NULL UNIQUE,
    emitida_em   timestamptz NOT NULL,
    emissor      text NOT NULL,
    aprovada_por text NOT NULL,
    total        numeric(12,2) NOT NULL CHECK (total > 0),
    xml          text NOT NULL,
    danfe        bytea NOT NULL
)
""",
    "CREATE SEQUENCE IF NOT EXISTS numero_da_nota START 1",
)


class PostgresFiscal:
    """A decisão e a nota no Postgres. Uma transação por operação."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    async def setup(self) -> None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            for statement in SCHEMA:
                await conn.execute(statement.encode())

    async def registrar_decisao(self, aprovacao: Aprovacao) -> bool:
        """True se ESTA decisão passou a valer; False se já havia uma.

        `ON CONFLICT DO NOTHING` e não `DO UPDATE`: a primeira decisão vence, e o
        chamador descobre pelo retorno que a dele não foi a que valeu. Um `UPDATE`
        deixaria um pedido rejeitado virar aprovado sem nenhum registro de que
        houve duas decisões.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            async with conn.cursor() as cur:
                existe = await (
                    await cur.execute("SELECT 1 FROM pedido WHERE id = %s", (aprovacao.pedido_id,))
                ).fetchone()
                if existe is None:
                    raise PedidoInexistente(aprovacao.pedido_id)

                inserido = await cur.execute(
                    "INSERT INTO aprovacao_de_nf"
                    " (pedido_id, decisao, operador, decidido_em, motivo)"
                    " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (pedido_id) DO NOTHING",
                    (
                        aprovacao.pedido_id,
                        aprovacao.decisao.value,
                        aprovacao.operador,
                        aprovacao.decidido_em,
                        aprovacao.motivo,
                    ),
                )
                # `rowcount` é lido DENTRO do `async with conn.cursor()`. Fora dele o
                # cursor já foi fechado e o valor vira -1 — o que fazia esta função
                # devolver `False` na primeira gravação, discordando de
                # `FiscalEmMemoria`. Achado na verificação manual contra o Postgres,
                # e não por teste: as duas camadas rodam contra a implementação em
                # memória (`docs/testes.md` §1), então divergência entre as duas só
                # aparece com o banco na frente.
                gravou = inserido.rowcount == 1
            await conn.commit()
        return gravou

    async def decisao_de(self, pedido_id: str) -> Aprovacao | None:
        encontradas = await self.decisoes_de((pedido_id,))
        return encontradas.get(pedido_id)

    async def decisoes_de(self, pedido_ids: Sequence[str]) -> dict[str, Aprovacao]:
        """As decisões de um conjunto de pedidos, numa consulta só.

        Em lote, e não uma por pedido, porque a fila do operador precisa saber de
        todas de uma vez — e escopado aos ids pedidos, e não "todas as decisões",
        para a consulta crescer com a fila e não com o histórico.
        """
        if not pedido_ids:
            return {}
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linhas = await (
                await conn.execute(
                    "SELECT pedido_id, decisao, operador, decidido_em, motivo"
                    " FROM aprovacao_de_nf WHERE pedido_id = ANY(%s)",
                    (list(pedido_ids),),
                )
            ).fetchall()
        return {
            linha[0]: Aprovacao(
                pedido_id=linha[0],
                decisao=Decisao(linha[1]),
                operador=linha[2],
                decidido_em=linha[3],
                motivo=linha[4],
            )
            for linha in linhas
        }

    async def decisoes_desde(self, desde: datetime) -> tuple[Aprovacao, ...]:
        """As decisões de uma janela, para a taxa de aprovação do painel.

        Por `decidido_em` e não pela data do pedido: a métrica é sobre o trabalho do
        operador, e um pedido de terça decidido na quinta é trabalho de quinta.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linhas = await (
                await conn.execute(
                    "SELECT pedido_id, decisao, operador, decidido_em, motivo"
                    " FROM aprovacao_de_nf WHERE decidido_em >= %s ORDER BY decidido_em",
                    (desde,),
                )
            ).fetchall()
        return tuple(
            Aprovacao(
                pedido_id=str(linha[0]),
                decisao=Decisao(linha[1]),
                operador=str(linha[2]),
                decidido_em=linha[3],
                motivo=linha[4],
            )
            for linha in linhas
        )

    async def proximo_numero(self) -> int:
        """`nextval` — e é por isso que a numeração é do banco e não do adapter.

        Dois operadores aprovando ao mesmo tempo pegam números diferentes sem
        ninguém coordenar nada. `SELECT max(numero) + 1` é a mesma linha de código
        com uma corrida dentro.
        """
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linha = await (await conn.execute("SELECT nextval('numero_da_nota')")).fetchone()
        if linha is None:
            # `nextval` sempre devolve uma linha. Chegar aqui significa que a
            # sequência não existe, e a causa é uma só: `make db-setup` não rodou
            # depois da S-05. A mensagem diz isso, em vez de deixar um `TypeError`
            # na frente de quem esqueceu um comando.
            raise RuntimeError(
                "a sequência `numero_da_nota` não respondeu; ela é criada por `make db-setup`"
            )
        return int(linha[0])

    async def registrar_nota(self, emitida: NotaEmitida) -> NotaEmitida:
        """Grava a nota. A chave primária é o que recusa uma segunda emissão."""
        nota = emitida.nota
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO nota_fiscal (pedido_id, numero, serie, chave, emitida_em,"
                    " emissor, aprovada_por, total, xml, danfe)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (pedido_id) DO NOTHING",
                    (
                        nota.pedido_id,
                        nota.numero,
                        nota.serie,
                        nota.chave,
                        nota.emitida_em,
                        nota.emissor,
                        nota.aprovada_por,
                        nota.total,
                        emitida.xml,
                        emitida.danfe,
                    ),
                )
            await conn.commit()
        # Relê: se o `ON CONFLICT` recusou, quem vale é a nota que já estava lá, e
        # devolver a que acabamos de montar faria o chamador anunciar ao cliente um
        # número de nota que não é o dele.
        gravada = await self.nota_de(nota.pedido_id)
        return gravada if gravada is not None else emitida

    async def nota_de(self, pedido_id: str) -> NotaEmitida | None:
        async with await psycopg.AsyncConnection.connect(self._dsn, autocommit=True) as conn:
            linha = await (
                await conn.execute(
                    "SELECT pedido_id, numero, serie, chave, emitida_em, emissor,"
                    " aprovada_por, total, xml, danfe FROM nota_fiscal WHERE pedido_id = %s",
                    (pedido_id,),
                )
            ).fetchone()
        if linha is None:
            return None
        return NotaEmitida(
            nota=NotaFiscal(
                pedido_id=linha[0],
                numero=int(linha[1]),
                serie=int(linha[2]),
                chave=linha[3],
                emitida_em=linha[4],
                emissor=linha[5],
                aprovada_por=linha[6],
                total=Decimal(linha[7]),
            ),
            xml=linha[8],
            danfe=bytes(linha[9]),
        )


class FiscalEmMemoria:
    """A mesma porta, sem contêiner — e implementação de primeira classe, não stub.

    É o que permite `tests/security/test_hitl_invariant.py` afirmar *"nenhuma nota
    foi emitida"* sem subir Postgres, que é o que `docs/testes.md` §1 exige das duas
    camadas. As invariantes que no Postgres são constraint são reproduzidas aqui à
    mão, e é por isso que os testes rodam contra as duas: uma delas divergindo é um
    bug que o teste tem que ver.
    """

    def __init__(self) -> None:
        self.decisoes: dict[str, Aprovacao] = {}
        self.notas: dict[str, NotaEmitida] = {}
        self._ultimo_numero = 0

    async def registrar_decisao(self, aprovacao: Aprovacao) -> bool:
        if aprovacao.pedido_id in self.decisoes:
            return False
        self.decisoes[aprovacao.pedido_id] = aprovacao
        return True

    async def decisao_de(self, pedido_id: str) -> Aprovacao | None:
        return self.decisoes.get(pedido_id)

    async def decisoes_de(self, pedido_ids: Sequence[str]) -> dict[str, Aprovacao]:
        return {
            pedido_id: self.decisoes[pedido_id]
            for pedido_id in pedido_ids
            if pedido_id in self.decisoes
        }

    async def decisoes_desde(self, desde: datetime) -> tuple[Aprovacao, ...]:
        return tuple(
            sorted(
                (a for a in self.decisoes.values() if a.decidido_em >= desde),
                key=lambda aprovacao: aprovacao.decidido_em,
            )
        )

    async def proximo_numero(self) -> int:
        self._ultimo_numero += 1
        return self._ultimo_numero

    async def registrar_nota(self, emitida: NotaEmitida) -> NotaEmitida:
        return self.notas.setdefault(emitida.nota.pedido_id, emitida)

    async def nota_de(self, pedido_id: str) -> NotaEmitida | None:
        return self.notas.get(pedido_id)


async def emitir(
    pedido_id: str,
    *,
    pedidos: Pedidos,
    fiscal: Fiscal,
    emissor: NFEmitter,
) -> NotaEmitida:
    """A **única** porta de emissão deste repositório — e a invariante da R3.

    **Duas precondições, as duas lidas do banco.** A decisão tem que existir e ser
    aprovação (`EmissaoNaoAprovada`), e o pedido tem que estar pago
    (`EmissaoSemPagamento`). Não há parâmetro que contorne nenhuma das duas, não há
    flag, e o estado do grafo não entra na conta — de propósito, porque estado de
    grafo é escrito por quem retoma o grafo.

    A segunda entrou depois da verificação independente (M-1): ela vivia só como um
    `if` na rota do operador, e `if` de rota é correção, não garantia.

    **A tentativa recusada vira log de aviso.** É o "o incidente é registrado" do
    BDD da spec: uma emissão barrada não é ruído, é alguém ou alguma coisa tendo
    chegado até aqui sem aprovação, e isso é a notícia.

    **Idempotente.** Chamada duas vezes, devolve a mesma nota — a chave primária de
    `nota_fiscal` recusa a segunda gravação, e o número da sequência que sobrou sem
    uso é o preço barato de não ter duas notas para um pedido. A atualização do
    status acontece nos dois caminhos: um processo que morresse entre gravar a nota
    e mudar o status deixaria o pedido mentindo, e a segunda chamada conserta.
    """
    decisao = await fiscal.decisao_de(pedido_id)
    if decisao is None or decisao.decisao is not Decisao.APROVADA:
        logger.warning(
            "emissão de NF barrada: o pedido %s não tem aprovação registrada (decisão atual: %s)",
            pedido_id,
            decisao.decisao.value if decisao else "nenhuma",
        )
        raise EmissaoNaoAprovada(
            f"o pedido {pedido_id} não tem aprovação registrada; a emissão depende de "
            f"decisão do operador na fila (ADR-003, RF-3.5)"
        )

    pedido = await pedidos.por_id(pedido_id)
    if pedido is None:
        raise PedidoInexistente(pedido_id)

    # **Segunda precondição, e ela é lida do pedido — não da rota.** Aprovar é
    # necessário e não é suficiente: nota de pedido não pago é o erro mais caro que
    # esta função poderia cometer, e antes da ressalva M-1 a única coisa que o
    # impedia era um `if` em `_decidir_pela_fila`. A leitura do pedido subiu para
    # cá por causa disso — ela ficava depois do atalho de idempotência.
    if pedido.status is StatusDoPedido.AGUARDANDO_PAGAMENTO:
        logger.warning(
            "emissão de NF barrada: o pedido %s não foi pago (status: %s)",
            pedido_id,
            pedido.status.value,
        )
        raise EmissaoSemPagamento(
            f"o pedido {pedido_id} ainda não foi pago; a nota só entra na fila depois "
            f"da confirmação do pagamento (RF-3.1)"
        )

    ja_emitida = await fiscal.nota_de(pedido_id)
    if ja_emitida is not None:
        await pedidos.registrar_emissao(pedido_id)
        return ja_emitida

    numero = await fiscal.proximo_numero()
    emitida = await fiscal.registrar_nota(await emissor.emitir(pedido, numero, decisao.autoriza()))
    await pedidos.registrar_emissao(pedido_id)
    logger.info(
        "NF %s emitida para o pedido %s, aprovada por %s",
        emitida.nota.numero,
        pedido_id,
        decisao.operador,
    )
    return emitida


# ------------------------------------------------------------------- o grafo


class EmissaoState(TypedDict):
    """Uma chave. Pointer-not-payload, como o `ConversationState` (RNF-6, R9).

    O pedido, a empresa, os itens e a nota **não** entram aqui. O checkpointer
    guardaria uma cópia deles que ninguém migra e ninguém invalida, e no dia em que
    a cópia divergisse do banco a nota sairia com a versão errada de um documento
    fiscal. `tests/unit/test_session_resume.py` prende este conjunto.
    """

    pedido_id: str


def thread_da_nota(pedido_id: str) -> dict[str, Any]:
    """A thread do checkpointer para a emissão deste pedido.

    Prefixada: a conversa e a emissão vivem no mesmo checkpointer, e um id de pedido
    que por acaso coincidisse com um id de sessão passaria a compartilhar histórico
    com ela — duas máquinas de estado no mesmo fio.
    """
    return {"configurable": {"thread_id": f"{PREFIXO_DA_THREAD}{pedido_id}"}}


def build_emissao_graph(
    pedidos: Pedidos,
    fiscal: Fiscal,
    emissor: NFEmitter,
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[EmissaoState, Any, Any, Any]:
    """O grafo fiscal: pausa, decisão, e um dos dois desfechos.

    ```
    START → aguardar_aprovacao ──⏸── (o que o banco diz) ─┬─→ emitir   → END
                                                          └─→ rejeitada → END
    ```

    **Não há modelo de linguagem em lugar nenhum deste grafo.** Ele existe para
    pausar e para persistir a pausa, que é o que o ADR-003 pediu; o LangGraph está
    aqui pelo `interrupt` e pelo checkpointer, não por IA.

    **A aresta condicional relê o banco.** Ela poderia ler o valor do `resume`, que
    chegaria de graça — e aí a autorização seria o argumento de quem retomou. É
    exatamente o buraco que a R3 existe para não ter.
    """
    builder: StateGraph[EmissaoState, Any, Any, Any] = StateGraph(EmissaoState)

    async def aguardar_aprovacao(state: EmissaoState) -> dict[str, Any]:
        """Para aqui, com o estado no checkpointer, até alguém retomar.

        O que o `interrupt` publica é o identificador e o motivo da pausa. Os dados
        da nota a fila lê do banco: publicá-los aqui criaria a segunda cópia que o
        `EmissaoState` recusa ter.
        """
        interrupt({"aguardando": AGUARDANDO, "pedido_id": state["pedido_id"]})
        return {}

    async def emitir_a_nota(state: EmissaoState) -> dict[str, Any]:
        await emitir(state["pedido_id"], pedidos=pedidos, fiscal=fiscal, emissor=emissor)
        return {}

    async def registrar_rejeicao(state: EmissaoState) -> dict[str, Any]:
        """A rejeição também é um desfecho, e ele é gravado.

        O `golden-011` reprova o agente que reapresenta o pedido para aprovação
        sozinho. O que impede isso não é o prompt: é o pedido sair de
        `aguardando_aprovacao_nf`, então ele não está mais na fila para ser
        aprovado.
        """
        await pedidos.registrar_rejeicao(state["pedido_id"])
        return {}

    async def o_que_o_banco_diz(state: EmissaoState) -> str:
        decisao = await fiscal.decisao_de(state["pedido_id"])
        if decisao is not None and decisao.decisao is Decisao.APROVADA:
            return "emitir"
        # Sem decisão nenhuma cai aqui também, e de propósito: retomar um grafo sem
        # ter registrado nada não pode emitir. O caminho não é um erro — é a
        # rejeição por omissão, e `registrar_rejeicao` só mexe no pedido que ainda
        # estava aguardando.
        return "rejeitada"

    builder.add_node("aguardar_aprovacao", aguardar_aprovacao)
    builder.add_node("emitir", emitir_a_nota)
    builder.add_node("rejeitada", registrar_rejeicao)

    builder.add_edge(START, "aguardar_aprovacao")
    builder.add_conditional_edges(
        "aguardar_aprovacao", o_que_o_banco_diz, {"emitir": "emitir", "rejeitada": "rejeitada"}
    )
    builder.add_edge("emitir", END)
    builder.add_edge("rejeitada", END)
    return builder.compile(checkpointer=checkpointer)


async def abrir_fila_da_nota(graph: Any, pedido_id: str) -> None:
    """Põe o pedido na pausa: o grafo entra, bate no `interrupt` e persiste (REQ-1).

    Chamado pelo webhook, depois de o pagamento ter efeito. Reentrante porque
    webhook reenviado é comportamento normal de gateway: se a thread já existe, não
    faz nada.
    """
    config = thread_da_nota(pedido_id)
    if (await graph.aget_state(config)).values:
        return
    await graph.ainvoke({"pedido_id": pedido_id}, config=config)


async def conduzir_ate_o_fim(graph: Any, pedido_id: str) -> None:
    """Leva a thread da nota até o fim, de onde quer que ela esteja.

    Três estados possíveis, e um caminho para cada um:

    * **não existe** — a abertura no webhook falhou, ou este pedido é anterior à
      S-05. Roda do START, o que a leva ao `interrupt`, e segue.
    * **parada no `interrupt`** — o caso normal. Retoma.
    * **concluída** — não faz nada.

    Recuperar a thread que não existe é o que faz a fila do operador ser derivada do
    **banco** e não do grafo: um pedido pago nunca fica sem caminho até a nota
    porque um `ainvoke` falhou uma vez.

    O valor do `resume` é deliberadamente inútil — a aresta condicional relê a
    decisão do banco. Ele existe porque o `interrupt` precisa de algo para devolver,
    e nomeá-lo `DECIDIDO` em vez de `"aprovado"` é para ninguém confundir sinal de
    retomada com autorização.
    """
    config = thread_da_nota(pedido_id)
    estado = await graph.aget_state(config)
    if not estado.values:
        await graph.ainvoke({"pedido_id": pedido_id}, config=config)
        estado = await graph.aget_state(config)
    if estado.next:
        await graph.ainvoke(Command(resume=DECIDIDO), config=config)


# Ver `conduzir_ate_o_fim`: sinal de retomada, nunca autorização.
DECIDIDO = "decidido"


async def decidir(
    graph: Any,
    aprovacao: Aprovacao,
    *,
    fiscal: Fiscal,
) -> Aprovacao:
    """Registra a decisão e conduz o grafo. **Nesta ordem, sempre.**

    Gravar antes de retomar é o que faz um processo que morra no meio ser
    recuperável: o registro existe, a nota não saiu, e a próxima chamada conduz o
    grafo a partir dele. A ordem inversa deixaria uma janela — grafo retomado, nada
    gravado — em que a emissão aconteceria sem trilha de auditoria, que é
    exatamente o que o ADR-003 proíbe.

    Devolve a decisão **vigente**, que pode não ser a que acabou de chegar: a
    primeira vence. Quem chamou descobre isso comparando, e é assim que a rota
    responde honestamente a um segundo operador clicando em "aprovar" num pedido já
    rejeitado.

    Conduzir mesmo quando a decisão não foi registrada agora é deliberado: é o que
    conserta o caso em que a gravação passou e a retomada falhou.
    """
    await fiscal.registrar_decisao(aprovacao)
    # A que valia antes, ou a que acabou de ser gravada. O `or` cobre o caso em que
    # a releitura não encontra nada — que não deveria acontecer, e cuja resposta
    # honesta é a decisão que este chamador pediu, não uma exceção que apagaria o
    # registro da vista de quem clicou.
    vigente = await fiscal.decisao_de(aprovacao.pedido_id) or aprovacao
    await conduzir_ate_o_fim(graph, aprovacao.pedido_id)
    return vigente


async def pendentes(pedidos: Pedidos) -> tuple[Pedido, ...]:
    """A fila: os pedidos pagos que ainda esperam uma decisão (REQ-2).

    É uma consulta ao **status do pedido**, e não ao grafo nem à tabela de decisões.
    O pedido sai da fila quando o desfecho é gravado — `nota_emitida` ou
    `nota_rejeitada` —, e é o mesmo movimento que tira o `golden-011` do caminho de
    emissão depois de uma rejeição.
    """
    return await pedidos.aguardando_aprovacao_de_nf()


__all__ = [
    "AGUARDANDO",
    "DECIDIDO",
    "PREFIXO_DA_THREAD",
    "SCHEMA",
    "Aprovacao",
    "Decisao",
    "EmissaoBloqueada",
    "EmissaoNaoAprovada",
    "EmissaoSemPagamento",
    "EmissaoState",
    "Fiscal",
    "FiscalEmMemoria",
    "PostgresFiscal",
    "StatusDaNota",
    "abrir_fila_da_nota",
    "build_emissao_graph",
    "conduzir_ate_o_fim",
    "decidir",
    "emitir",
    "pendentes",
    "status_da_nota",
    "thread_da_nota",
]
